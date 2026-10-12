"""Generate and validate the Wallune static API.

This repository is a static content backend. The script produces GitHub Raw
JSON and image references, with no server or external runtime dependency.
"""

from datetime import datetime, timezone
import argparse
import hashlib
import os
import json
import re
import shutil
import struct
import sys
import tempfile
import urllib.parse
import uuid
from pathlib import Path


def get_clean_title(filename):
    name, _ = os.path.splitext(filename)
    return name.replace("_", " ").replace("-", " ").title()

# ---------------------------------------------------------------------------
# Hardened static generator implementation.
# ---------------------------------------------------------------------------
IMAGE_DIR = "images"
API_DIR = "api/v1"
GITHUB_USERNAME = "OmarShawkey13"
GITHUB_REPO_NAME = "Wallune"
BRANCH = "main"
VALID_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ITEMS_PER_PAGE = 20
ID_METADATA_FILENAME = "wallpaper_ids.json"
CONFIG_FILENAME = "config.json"
METADATA_SCHEMA_VERSION = 2
MIGRATION_FALLBACK_UPDATED_AT = "2000-01-01T00:00:00Z"
_PAGE_RE = re.compile(r"page_(\d+)\.json$")
_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$")


def utc_iso(timestamp=None):
    value = datetime.now(timezone.utc) if timestamp is None else datetime.fromtimestamp(timestamp, timezone.utc)
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _valid_uuid(value):
    return isinstance(value, str) and bool(_UUID_RE.fullmatch(value))


def _normalize(path):
    return path.replace("\\", "/").lstrip("./")


def _url(category, filename):
    base = (
        "https://raw.githubusercontent.com/"
        + urllib.parse.quote(GITHUB_USERNAME, safe="") + "/"
        + urllib.parse.quote(GITHUB_REPO_NAME, safe="") + "/"
        + urllib.parse.quote(BRANCH, safe="") + "/"
        + urllib.parse.quote(IMAGE_DIR, safe="")
    )
    return base + "/" + urllib.parse.quote(category, safe="") + "/" + urllib.parse.quote(filename, safe="")


def _category_id(name):
    """Return a deterministic UUID for a category name."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "wallune:category:" + name))


def _url_relative(value):
    try:
        parsed = urllib.parse.urlsplit(value)
    except ValueError:
        return None
    if parsed.scheme != "https" or parsed.netloc != "raw.githubusercontent.com":
        return None
    parts = [urllib.parse.unquote(part) for part in parsed.path.split("/") if part]
    try:
        index = parts.index(IMAGE_DIR)
    except ValueError:
        return None
    relative = _normalize("/".join(parts[index:]))
    if relative == IMAGE_DIR or ".." in Path(relative).parts:
        return None
    return relative


def _sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _iter_images():
    root = Path(IMAGE_DIR)
    if not root.is_dir():
        return
    for category in sorted((item for item in root.iterdir() if item.is_dir()), key=lambda item: item.name):
        for path in sorted(category.iterdir(), key=lambda item: item.name):
            if path.is_file() and path.suffix.lower() in VALID_EXTENSIONS:
                yield category.name, path.name, str(path)


def _reject_duplicate_images(items):
    by_hash = {}
    for item in items:
        by_hash.setdefault(item["content_hash"], []).append(item["relative"])
    duplicates = [paths for paths in by_hash.values() if len(paths) > 1]
    if duplicates:
        details = "; ".join(", ".join(paths) for paths in duplicates)
        raise ValueError("Duplicate image bytes found; remove one copy: " + details)


def _metadata_path(api_dir=None):
    return str(Path(api_dir or API_DIR) / ID_METADATA_FILENAME)


def _config_path(api_dir=None):
    return str(Path(api_dir or API_DIR) / CONFIG_FILENAME)


def _validate_metadata(records, allow_missing_updated_at=False):
    if not isinstance(records, list):
        raise ValueError("UUID metadata must contain a wallpapers list")
    seen = set()
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise ValueError(f"UUID metadata record {index} is not an object")
        required = {"id", "content_hash", "aliases", "retired"}
        missing = sorted(required - set(record))
        if missing:
            raise ValueError(
                f"UUID metadata record {index} is missing required fields: {', '.join(missing)}"
            )
        record_id = record["id"]
        if not _valid_uuid(record_id) or record_id in seen:
            raise ValueError("UUID metadata contains an invalid or duplicate ID")
        content_hash = record["content_hash"]
        if not isinstance(content_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", content_hash):
            raise ValueError(f"UUID metadata record {record_id} contains an invalid content hash")
        aliases = record["aliases"]
        if not isinstance(aliases, list) or any(not isinstance(alias, str) or not alias for alias in aliases):
            raise ValueError(f"UUID metadata record {record_id} contains invalid aliases")
        normalized_aliases = [_normalize(alias) for alias in aliases]
        if len(normalized_aliases) != len(set(normalized_aliases)):
            raise ValueError(f"UUID metadata record {record_id} contains duplicate aliases")
        if record["retired"] not in (True, False) or not isinstance(record["retired"], bool):
            raise ValueError(f"UUID metadata record {record_id} contains an invalid retired flag")
        if "updated_at" not in record:
            if not allow_missing_updated_at:
                raise ValueError(
                    f"UUID metadata record {record_id} is missing updated_at; run one normal generation to migrate it"
                )
        elif not isinstance(record["updated_at"], str):
            raise ValueError(f"UUID metadata record {record_id} contains an invalid updated_at")
        else:
            _parse_utc(record["updated_at"])
        seen.add(record_id)


def _load_metadata(api_dir=None):
    path = _metadata_path(api_dir)
    if not os.path.isfile(path):
        return []
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read identity metadata {path}: {exc}") from exc
    if not isinstance(payload, dict) or "wallpapers" not in payload:
        raise ValueError("Invalid wallpaper_ids.json format: expected an object with wallpapers")
    schema_version = payload.get("schema_version", 1)
    if not _is_int(schema_version) or schema_version not in (1, METADATA_SCHEMA_VERSION):
        raise ValueError(f"Unsupported wallpaper_ids.json schema_version: {schema_version!r}")
    records = payload["wallpapers"]
    if not isinstance(records, list):
        raise ValueError("Invalid wallpaper_ids.json format: wallpapers must be a list")
    normalized = []
    for record in records:
        if not isinstance(record, dict):
            normalized.append(record)
            continue
        # Keep the original key set so a malformed record reports the
        # missing field instead of being converted into an unrelated type
        # error (for example, ``content_hash=None``).
        value = {key: record[key] for key in record if key in {
            "id", "content_hash", "aliases", "retired", "updated_at"
        }}
        normalized.append(value)
    _validate_metadata(normalized, allow_missing_updated_at=True)
    return normalized


def _legacy_pages(api_dir=None):
    result = []
    directory = Path(api_dir or API_DIR) / "wallpapers"
    if directory.is_dir():
        paths = sorted(
            (path for path in directory.iterdir() if _PAGE_RE.fullmatch(path.name)),
            key=lambda path: int(_PAGE_RE.fullmatch(path.name).group(1)),
        )
        for path in paths:
            try:
                with open(path, encoding="utf-8") as handle:
                    payload = json.load(handle)
            except (OSError, json.JSONDecodeError) as exc:
                raise ValueError(f"Could not read legacy page {path}: {exc}") from exc
            if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
                raise ValueError(f"Legacy page {path} has invalid data")
            result.extend(payload["data"])
    legacy = Path("wallpapers.json")
    if legacy.is_file():
        try:
            with open(legacy, encoding="utf-8") as handle:
                payload = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Could not read legacy wallpapers.json: {exc}") from exc
        if isinstance(payload, dict):
            values = payload.get("wallpapers")
        else:
            values = payload
        if not isinstance(values, list):
            raise ValueError("Legacy wallpapers.json must contain a list")
        result.extend(values)
    return result


def _deterministic_migration_timestamp(content_hash):
    """Fallback for legacy records without a valid timestamp."""
    # A fixed UTC value keeps migration reproducible and avoids treating file
    # mtime as identity data. The hash argument is retained for call-site
    # clarity and future migration strategies.
    return MIGRATION_FALLBACK_UPDATED_AT


def _legacy_timestamp_by_id(api_dir=None):
    timestamps = {}
    for item in _legacy_pages(api_dir):
        if not isinstance(item, dict):
            continue
        record_id = item.get("id")
        if not _valid_uuid(record_id):
            continue
        value = item.get("updated_at")
        if value is None:
            continue
        try:
            _parse_utc(value)
        except ValueError:
            continue
        previous = timestamps.get(record_id)
        if previous is not None and previous != value:
            raise ValueError(f"Legacy pages contain conflicting updated_at values for UUID {record_id}")
        timestamps[record_id] = value
    return timestamps


def _migrate_legacy_records():
    records = []
    by_id = {}
    for item in _legacy_pages():
        if not isinstance(item, dict):
            continue
        record_id, value = item.get("id"), item.get("image_url")
        if not _valid_uuid(record_id) or not isinstance(value, str):
            continue
        relative = _url_relative(value)
        if not relative:
            continue
        path = Path(relative.replace("/", os.sep))
        if not path.is_file() and relative.startswith(IMAGE_DIR + "/"):
            path = Path(IMAGE_DIR) / Path(relative).relative_to(IMAGE_DIR)
        if not path.is_file():
            continue
        digest = _sha256(str(path))
        timestamp = item.get("updated_at")
        try:
            _parse_utc(timestamp)
        except (TypeError, ValueError):
            timestamp = _deterministic_migration_timestamp(digest)
        record = by_id.get(record_id)
        if record is None:
            record = {
                "id": record_id,
                "content_hash": digest,
                "aliases": [],
                "retired": False,
                "updated_at": timestamp,
            }
            records.append(record)
            by_id[record_id] = record
        elif record["content_hash"] != digest:
            raise ValueError(
                f"Legacy pages contain conflicting image bytes for UUID {record_id}; "
                "repair the legacy catalog before migration"
            )
        if relative not in record["aliases"]:
            record["aliases"].append(relative)
    _validate_metadata(records)
    return records


def _load_identity_records():
    metadata_path = Path(_metadata_path())
    if not metadata_path.is_file():
        return _migrate_legacy_records()

    records = _load_metadata()
    if not records:
        legacy_ids = [
            item.get("id")
            for item in _legacy_pages()
            if isinstance(item, dict) and _valid_uuid(item.get("id"))
        ]
        if legacy_ids:
            raise ValueError(
                "Identity metadata is empty while legacy catalog records exist; "
                "refusing to reset wallpaper IDs"
            )
    if any("updated_at" not in record for record in records):
        timestamps = _legacy_timestamp_by_id()
        for record in records:
            record.setdefault(
                "updated_at",
                timestamps.get(
                    record["id"],
                    _deterministic_migration_timestamp(record["content_hash"]),
                ),
            )
    _validate_metadata(records)
    return records


def _assign_ids(items, previous):
    metadata = [{
        "id": record["id"],
        "content_hash": record["content_hash"],
        "aliases": list(record.get("aliases", [])),
        "retired": bool(record.get("retired", False)),
        "updated_at": record.get("updated_at", _deterministic_migration_timestamp(record["content_hash"])),
        "_was_active": not bool(record.get("retired", False)),
    } for record in previous]
    by_hash = {}
    for record in metadata:
        by_hash.setdefault(record["content_hash"], []).append(record)
        record["retired"] = True
    for values in by_hash.values():
        values.sort(key=lambda record: record["id"])
    assigned = set()
    public = []
    for item in items:
        candidates = [
            record for record in by_hash.get(item["content_hash"], [])
            if record["id"] not in assigned and record["_was_active"]
        ]
        exact = [record for record in candidates if item["relative"] in record["aliases"]]
        record = (exact or candidates or [None])[0]
        if record is None:
            record = {
                "id": str(uuid.uuid4()),
                "content_hash": item["content_hash"],
                "aliases": [],
                "retired": False,
                "updated_at": item["updated_at"],
                "_was_active": True,
            }
            metadata.append(record)
            by_hash.setdefault(item["content_hash"], []).append(record)
        record["retired"] = False
        if not record.get("updated_at"):
            record["updated_at"] = item["updated_at"]
        record["aliases"] = sorted(set(record["aliases"]) | {item["relative"]})
        assigned.add(record["id"])
        public.append({
            "id": record["id"],
            "title": item["title"],
            "category": item["category"],
            "image_url": item["image_url"],
            "size": item["size"],
            "updated_at": record["updated_at"],
            "width": item["width"],
            "height": item["height"],
        })
    current_paths = {item["relative"] for item in items}
    for record in metadata:
        if record["id"] not in assigned:
            record["aliases"] = [
                alias for alias in record["aliases"] if alias not in current_paths
            ]
        record.pop("_was_active", None)
    metadata.sort(key=lambda record: (record["content_hash"], record["id"]))
    _validate_metadata(metadata)
    if len({item["id"] for item in public}) != len(public):
        raise ValueError("Duplicate wallpaper IDs were assigned")
    return public, metadata


def get_image_size(fname):
    try:
        with open(fname, "rb") as handle:
            header = handle.read(32)
            if len(header) < 24:
                return None
            if header.startswith(b"\x89PNG\r\n\x1a\n"):
                return struct.unpack(">II", header[16:24])
            if header.startswith((b"GIF87a", b"GIF89a")):
                return struct.unpack("<HH", header[6:10])
            if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
                chunk = header[12:16]
                if chunk == b"VP8 ":
                    handle.seek(26)
                    data = handle.read(4)
                    if len(data) == 4:
                        width, height = struct.unpack("<HH", data)
                        return width & 0x3FFF, height & 0x3FFF
                elif chunk == b"VP8L":
                    handle.seek(21)
                    data = handle.read(4)
                    if len(data) == 4:
                        b1, b2, b3, b4 = data
                        return 1 + (((b2 & 0x3F) << 8) | b1), 1 + (((b4 & 0x0F) << 10) | (b3 << 2) | ((b2 & 0xC0) >> 6))
                elif chunk == b"VP8X":
                    handle.seek(24)
                    data = handle.read(6)
                    if len(data) == 6:
                        b1, b2, b3, b4, b5, b6 = data
                        return 1 + (b1 | b2 << 8 | b3 << 16), 1 + (b4 | b5 << 8 | b6 << 16)
            if header.startswith(b"\xff\xd8"):
                handle.seek(2)
                sof = set(range(0xC0, 0xC4)) | set(range(0xC5, 0xC8)) | set(range(0xC9, 0xCC)) | set(range(0xCD, 0xD0))
                while True:
                    byte = handle.read(1)
                    while byte and byte != b"\xff":
                        byte = handle.read(1)
                    if not byte:
                        return None
                    marker = handle.read(1)
                    while marker == b"\xff":
                        marker = handle.read(1)
                    if not marker:
                        return None
                    marker = marker[0]
                    if marker in (0xD8, 0xD9):
                        continue
                    length_data = handle.read(2)
                    if len(length_data) != 2:
                        return None
                    length = struct.unpack(">H", length_data)[0]
                    if length < 2:
                        return None
                    if marker in sof:
                        data = handle.read(5)
                        if len(data) != 5:
                            return None
                        _, height, width = struct.unpack(">BHH", data)
                        return width, height
                    handle.seek(length - 2, os.SEEK_CUR)
    except (OSError, struct.error, ValueError):
        return None
    return None

def _search_index(wallpapers):
    fields = ("id", "title", "category", "image_url", "size", "updated_at", "width", "height")
    return [{field: item[field] for field in fields} for item in wallpapers]


def _pages(wallpapers):
    total = len(wallpapers)
    count = (total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    result = []
    for page in range(1, count + 1):
        data = list(wallpapers[(page - 1) * ITEMS_PER_PAGE:page * ITEMS_PER_PAGE])
        result.append({
            "page": page,
            "total_pages": count,
            "total_items": total,
            "items_per_page": ITEMS_PER_PAGE,
            "has_next": page < count,
            "has_prev": page > 1,
            "data": data,
        })
    return result


def _catalog_hash(wallpapers, categories):
    semantic = [{key: value for key, value in item.items() if key != "updated_at"} for item in wallpapers]
    raw = json.dumps(
        {
            "wallpapers": semantic,
            "categories": categories,
            "items_per_page": ITEMS_PER_PAGE,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _content_version(current_hash):
    path = _config_path()
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as handle:
                previous = json.load(handle)
            old = previous.get("content_version")
            if previous.get("catalog_hash") == current_hash and isinstance(old, int) and old > 0:
                return old
            if isinstance(old, int) and old > 0:
                return old + 1
        except (OSError, ValueError):
            pass
    return 1


def _generated_output_files(root):
    root = Path(root)
    files = [
        path for path in (
            root / "categories.json",
            root / "search_index.json",
            root / ID_METADATA_FILENAME,
            root / CONFIG_FILENAME,
            root / "models.dart",
        )
        if path.is_file()
    ]
    pages = root / "wallpapers"
    if pages.is_dir():
        files.extend(path for path in pages.iterdir() if path.is_file() and _PAGE_RE.fullmatch(path.name))
    return files


def _replace_staged_output(stage_dir):
    """Replace generated files with rollback; the directory swap is not atomic."""
    api_root = Path(API_DIR)
    api_root.parent.mkdir(parents=True, exist_ok=True)
    api_root.mkdir(parents=True, exist_ok=True)
    (api_root / "wallpapers").mkdir(parents=True, exist_ok=True)
    stage_dir = Path(stage_dir)
    stage_files = [
        path for path in stage_dir.rglob("*") if path.is_file()
    ]
    existing_files = _generated_output_files(api_root)
    backup_dir = Path(tempfile.mkdtemp(prefix=f".{api_root.name}.backup-", dir=str(api_root.parent)))
    backup_map = {}
    touched = set()
    try:
        for path in existing_files:
            relative = path.relative_to(api_root)
            backup_path = backup_dir / relative
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, backup_path)
            backup_map[path] = backup_path
            touched.add(path)
        for path in stage_files:
            relative = path.relative_to(stage_dir)
            target = api_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(path, target)
            touched.add(target)
        stage_names = {
            api_root / path.relative_to(stage_dir)
            for path in stage_files
        }
        for path in existing_files:
            if path not in stage_names and path.exists():
                path.unlink()
        validate_generated_api(api_root)
    except Exception:
        for path in touched:
            if path.exists() and path not in backup_map:
                try:
                    path.unlink()
                except OSError:
                    pass
        for path, backup_path in backup_map.items():
            if backup_path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(backup_path, path)
        raise
    finally:
        shutil.rmtree(backup_dir, ignore_errors=True)


def _parse_utc(value):
    if not isinstance(value, str) or not value.endswith("Z"):
        raise ValueError("Timestamp is not UTC with Z suffix")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ValueError("Invalid ISO timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError("Timestamp is not UTC")
    return parsed


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _validate_public_record(item, context):
    if not isinstance(item, dict):
        raise ValueError(f"{context} must be an object")
    fields = ("id", "title", "category", "image_url", "size", "updated_at", "width", "height")
    missing = [field for field in fields if field not in item]
    if missing:
        raise ValueError(f"{context} is missing fields: {', '.join(missing)}")
    for field in ("id", "title", "category", "image_url", "updated_at"):
        if not isinstance(item[field], str) or not item[field]:
            raise ValueError(f"{context}.{field} must be a non-empty string")
    if not _valid_uuid(item["id"]):
        raise ValueError(f"{context}.id is not a UUID")
    for field in ("size", "width", "height"):
        if not _is_int(item[field]) or item[field] <= 0:
            raise ValueError(f"{context}.{field} must be a positive integer")
    _parse_utc(item["updated_at"])


def _validate_catalog(wallpapers, categories, search, pages, config, local_images):
    if not isinstance(wallpapers, list):
        raise ValueError("Wallpaper data must be a list")
    if not isinstance(categories, list):
        raise ValueError("categories.json must contain an array")
    if not isinstance(search, list):
        raise ValueError("search_index.json must contain an array")
    if not isinstance(pages, list):
        raise ValueError("Wallpaper pages must be a list")
    total = len(wallpapers)
    page_count = (total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    if len(pages) != page_count:
        raise ValueError("Wallpaper page count does not match total_items")
    ids = []
    urls = []
    local = {_normalize(item["relative"]): item for item in local_images}
    seen_paths = []
    fields = ("id", "title", "category", "image_url", "size", "updated_at", "width", "height")
    for index, item in enumerate(wallpapers):
        _validate_public_record(item, f"wallpapers[{index}]")
        ids.append(item["id"])
        urls.append(item["image_url"])
        relative = _url_relative(item["image_url"])
        if not relative or relative not in local:
            raise ValueError("Wallpaper URL does not map to a local image")
        parts = relative.split("/")
        if len(parts) != 3 or parts[0] != IMAGE_DIR:
            raise ValueError("Wallpaper URL path is invalid")
        if item["image_url"] != _url(parts[1], parts[2]):
            raise ValueError("Wallpaper URL does not use canonical Wallune identity")
        seen_paths.append(relative)
    if len(set(ids)) != len(ids):
        raise ValueError("Wallpaper IDs are missing, invalid, or duplicated")
    if len(set(urls)) != len(urls):
        raise ValueError("Wallpaper URLs are duplicated")
    expected_paths = set(local)
    if len(seen_paths) != len(expected_paths) or set(seen_paths) != expected_paths:
        raise ValueError("Local images and generated records are not a one-to-one mapping")

    category_ids = []
    category_names = []
    for index, category in enumerate(categories):
        if not isinstance(category, dict):
            raise ValueError(f"categories[{index}] must be an object")
        required = ("id", "name", "count", "cover")
        if any(field not in category for field in required):
            raise ValueError(f"categories[{index}] is missing a required field")
        if not _valid_uuid(category["id"]) or not isinstance(category["name"], str) or not category["name"]:
            raise ValueError(f"categories[{index}] has invalid id or name")
        if not _is_int(category["count"]) or category["count"] < 0:
            raise ValueError(f"categories[{index}].count must be a non-negative integer")
        if not isinstance(category["cover"], str) or not category["cover"]:
            raise ValueError(f"categories[{index}].cover must be a non-empty string")
        category_ids.append(category["id"])
        category_names.append(category["name"])
    if len(set(category_ids)) != len(category_ids):
        raise ValueError("Category IDs are duplicated")
    if len(set(category_names)) != len(category_names):
        raise ValueError("Category names are duplicated")
    names = set(category_names)
    wallpaper_names = {item["category"] for item in wallpapers}
    if names != wallpaper_names:
        raise ValueError("Category names do not match wallpaper records")
    for category in categories:
        matching = [item for item in wallpapers if item["category"] == category["name"]]
        if (
            category["id"] != _category_id(category["name"])
            or category["count"] != len(matching)
            or category["cover"] not in {item["image_url"] for item in matching}
        ):
            raise ValueError("Category count or cover is invalid")
        if _url_relative(category["cover"]) not in expected_paths:
            raise ValueError("Category cover does not map to a local image")

    search_ids = []
    for index, result in enumerate(search):
        _validate_public_record(result, f"search_index[{index}]")
        search_ids.append(result["id"])
    if len(search_ids) != len(set(search_ids)):
        raise ValueError("Search index contains duplicate IDs")
    if set(search_ids) != set(ids):
        raise ValueError("Search index is incomplete or contains extra records")
    by_id = {item["id"]: item for item in wallpapers}
    for result in search:
        if any(result[field] != by_id[result["id"]][field] for field in fields):
            raise ValueError("Search index metadata differs from canonical data")

    for index, page in enumerate(pages, 1):
        if not isinstance(page, dict):
            raise ValueError(f"page {index} must be an object")
        for field in ("page", "total_pages", "total_items", "items_per_page"):
            if not _is_int(page.get(field)):
                raise ValueError(f"page {index}.{field} must be an integer")
        if not isinstance(page.get("has_next"), bool) or not isinstance(page.get("has_prev"), bool):
            raise ValueError(f"page {index} navigation flags must be boolean")
        if not isinstance(page.get("data"), list):
            raise ValueError(f"page {index}.data must be an array")
        expected_length = ITEMS_PER_PAGE if index < page_count else total - ITEMS_PER_PAGE * (page_count - 1)
        if (
            page["page"] != index
            or page["total_pages"] != page_count
            or page["total_items"] != total
            or page["items_per_page"] != ITEMS_PER_PAGE
            or len(page["data"]) != expected_length
            or page["has_next"] != (index < page_count)
            or page["has_prev"] != (index > 1)
        ):
            raise ValueError("Pagination metadata is invalid")
        for item_index, item in enumerate(page["data"]):
            _validate_public_record(item, f"page {index}.data[{item_index}]")

    if not isinstance(config, dict):
        raise ValueError("config.json must contain an object")
    if not _is_int(config.get("api_version")) or config.get("api_version") != 1:
        raise ValueError("config.json api_version is invalid")
    if not _is_int(config.get("content_version")) or config["content_version"] <= 0:
        raise ValueError("config.json content_version is invalid")
    if (
        config.get("total_items") != total
        or config.get("total_pages") != page_count
        or config.get("items_per_page") != ITEMS_PER_PAGE
    ):
        raise ValueError("config.json totals are invalid")
    if not isinstance(config.get("catalog_hash"), str) or not re.fullmatch(r"[0-9a-f]{64}", config["catalog_hash"]):
        raise ValueError("config.json catalog_hash is invalid")
    if config["catalog_hash"] != _catalog_hash(wallpapers, categories):
        raise ValueError("config.json catalog_hash does not match the catalog")
    _parse_utc(config.get("generated_at"))


def _write_json(path, payload, compact=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, separators=(",", ":") if compact else None, indent=None if compact else 2)
        handle.write("\n")


def _write_models(api_dir=None):
    dart = """// AUTO-GENERATED CODE - DO NOT MODIFY BY HAND
// Wallune static API models.

class Wallpaper {
  final String id;
  final String title;
  final String category;
  final String imageUrl;
  final int size;
  final String updatedAt;
  final int width;
  final int height;

  Wallpaper({
    required this.id,
    required this.title,
    required this.category,
    required this.imageUrl,
    required this.size,
    required this.updatedAt,
    required this.width,
    required this.height,
  });

  factory Wallpaper.fromJson(Map<String, dynamic> json) => Wallpaper(
    id: json['id'] as String? ?? '',
    title: json['title'] as String? ?? '',
    category: json['category'] as String? ?? '',
    imageUrl: json['image_url'] as String? ?? '',
    size: (json['size'] as num?)?.toInt() ?? 0,
    updatedAt: json['updated_at'] as String? ?? '',
    width: (json['width'] as num?)?.toInt() ?? 0,
    height: (json['height'] as num?)?.toInt() ?? 0,
  );

  Map<String, dynamic> toJson() => {
    'id': id, 'title': title, 'category': category, 'image_url': imageUrl,
    'size': size, 'updated_at': updatedAt, 'width': width, 'height': height,
  };
}

class PaginatedResponse {
  final int page;
  final int totalPages;
  final int totalItems;
  final int itemsPerPage;
  final bool hasNext;
  final bool hasPrev;
  final List<Wallpaper> data;

  PaginatedResponse({
    required this.page,
    required this.totalPages,
    required this.totalItems,
    required this.itemsPerPage,
    required this.hasNext,
    required this.hasPrev,
    required this.data,
  });

  factory PaginatedResponse.fromJson(Map<String, dynamic> json) => PaginatedResponse(
    page: (json['page'] as num?)?.toInt() ?? 0,
    totalPages: (json['total_pages'] as num?)?.toInt() ?? 0,
    totalItems: (json['total_items'] as num?)?.toInt() ?? 0,
    itemsPerPage: (json['items_per_page'] as num?)?.toInt() ?? 20,
    hasNext: json['has_next'] as bool? ?? false,
    hasPrev: json['has_prev'] as bool? ?? false,
    data: ((json['data'] as List?) ?? const [])
        .map((item) => Wallpaper.fromJson(item as Map<String, dynamic>))
        .toList(),
  );
}

class Category {
  final String id;
  final String name;
  final int count;
  final String cover;

  Category({required this.id, required this.name, required this.count, required this.cover});

  factory Category.fromJson(Map<String, dynamic> json) => Category(
    id: json['id'] as String? ?? '',
    name: json['name'] as String? ?? '',
    count: (json['count'] as num?)?.toInt() ?? 0,
    cover: json['cover'] as String? ?? '',
  );
}

class ApiConfig {
  final int apiVersion;
  final int contentVersion;
  final int totalItems;
  final int totalPages;
  final int itemsPerPage;
  final String generatedAt;
  final String catalogHash;

  ApiConfig({
    required this.apiVersion,
    required this.contentVersion,
    required this.totalItems,
    required this.totalPages,
    required this.itemsPerPage,
    required this.generatedAt,
    required this.catalogHash,
  });

  factory ApiConfig.fromJson(Map<String, dynamic> json) => ApiConfig(
    apiVersion: (json['api_version'] as num?)?.toInt() ?? 1,
    contentVersion: (json['content_version'] as num?)?.toInt() ?? 0,
    totalItems: (json['total_items'] as num?)?.toInt() ?? 0,
    totalPages: (json['total_pages'] as num?)?.toInt() ?? 0,
    itemsPerPage: (json['items_per_page'] as num?)?.toInt() ?? 20,
    generatedAt: json['generated_at'] as String? ?? '',
    catalogHash: json['catalog_hash'] as String? ?? '',
  );
}
"""
    output_dir = api_dir or API_DIR
    os.makedirs(output_dir, exist_ok=True)
    with open(os.path.join(output_dir, "models.dart"), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(dart)


def validate_generated_api(api_dir=None):
    api_root = Path(api_dir or API_DIR)
    try:
        with open(api_root / "categories.json", encoding="utf-8") as handle:
            categories = json.load(handle)
        with open(api_root / "search_index.json", encoding="utf-8") as handle:
            search = json.load(handle)
        with open(api_root / CONFIG_FILENAME, encoding="utf-8") as handle:
            config = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read generated API under {api_root}: {exc}") from exc
    directory = api_root / "wallpapers"
    if not directory.is_dir():
        raise ValueError(f"Generated API is missing {directory}")
    matching_paths = sorted(
        (path for path in directory.iterdir() if path.is_file() and _PAGE_RE.fullmatch(path.name)),
        key=lambda path: int(_PAGE_RE.fullmatch(path.name).group(1)),
    )
    page_count_hint = config.get("total_pages") if isinstance(config, dict) else None
    if not _is_int(page_count_hint) or page_count_hint < 0:
        raise ValueError("config.json total_pages must be a non-negative integer")
    expected_names = [f"page_{index}.json" for index in range(1, page_count_hint + 1)]
    actual_names = [path.name for path in matching_paths]
    if actual_names != expected_names:
        raise ValueError(
            "Wallpaper page filenames must be exactly "
            + (", ".join(expected_names) if expected_names else "none")
            + f"; found {', '.join(actual_names) if actual_names else 'none'}"
        )
    pages = []
    for expected_number, path in enumerate(matching_paths, 1):
        try:
            with open(path, encoding="utf-8") as handle:
                page = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError(f"Could not read generated page {path}: {exc}") from exc
        if not isinstance(page, dict) or page.get("page") != expected_number:
            raise ValueError(f"Page filename {path.name} does not match its JSON page number")
        pages.append(page)
    wallpapers = [item for page in pages for item in page.get("data", [])]
    local_images = [
        {"relative": f"{IMAGE_DIR}/{category}/{filename}", "path": path}
        for category, filename, path in _iter_images()
    ]
    _validate_catalog(wallpapers, categories, search, pages, config, local_images)
    metadata = _load_metadata(api_root)
    _validate_metadata(metadata)
    metadata_by_id = {record["id"]: record for record in metadata}
    active_metadata_ids = {record["id"] for record in metadata if not record["retired"]}
    public_ids = {item["id"] for item in wallpapers}
    if public_ids != active_metadata_ids:
        raise ValueError("Public wallpaper IDs must exactly match active UUID metadata IDs")
    local_by_relative = {_normalize(item["relative"]): item for item in local_images}
    active_aliases = {}
    for record in metadata:
        for alias in record["aliases"]:
            normalized = _normalize(alias)
            if normalized in local_by_relative and not record["retired"]:
                previous = active_aliases.get(normalized)
                if previous is not None and previous != record["id"]:
                    raise ValueError(f"Current image path has multiple active identity aliases: {normalized}")
                active_aliases[normalized] = record["id"]
    for item in wallpapers:
        relative = _url_relative(item["image_url"])
        record = metadata_by_id.get(item["id"])
        if record is None:
            raise ValueError(f"Generated wallpaper ID is missing from identity metadata: {item['id']}")
        if record["retired"]:
            raise ValueError(f"Public wallpaper points to retired identity: {item['id']}")
        if relative not in record["aliases"]:
            raise ValueError(f"Current image path is missing from identity aliases: {relative}")
        local = local_by_relative[relative]
        actual_path = local["path"]
        actual_size = os.path.getsize(actual_path)
        actual_dimensions = get_image_size(actual_path)
        actual_hash = _sha256(actual_path)
        if item["size"] != actual_size:
            raise ValueError(f"Wallpaper size does not match the image: {relative}")
        if not actual_dimensions or (item["width"], item["height"]) != actual_dimensions:
            raise ValueError(f"Wallpaper dimensions do not match the image: {relative}")
        if record["content_hash"] != actual_hash:
            raise ValueError(f"Identity content hash does not match the image: {relative}")
        if item["updated_at"] != record["updated_at"]:
            raise ValueError(f"Wallpaper updated_at does not match identity metadata: {relative}")
        if active_aliases.get(relative) != item["id"]:
            raise ValueError(f"Current image path is not owned by its public identity: {relative}")
    return {
        "total_items": len(wallpapers),
        "total_pages": len(pages),
        "categories": len(categories),
        "search_items": len(search),
    }


def process_images():
    if not os.path.isdir(IMAGE_DIR):
        raise FileNotFoundError("Directory 'images' not found")
    previous = _load_identity_records()
    items = []
    for category, filename, path in _iter_images():
        dimensions = get_image_size(path)
        if not dimensions or dimensions[0] <= 0 or dimensions[1] <= 0:
            raise ValueError("Could not read positive image dimensions: " + path)
        items.append({
            "category": category,
            "filename": filename,
            "relative": f"{IMAGE_DIR}/{category}/{filename}",
            "title": get_clean_title(filename),
            "image_url": _url(category, filename),
            "size": os.path.getsize(path),
            "updated_at": utc_iso(),
            "width": dimensions[0],
            "height": dimensions[1],
            "content_hash": _sha256(path),
        })
    _reject_duplicate_images(items)
    wallpapers, metadata = _assign_ids(items, previous)
    wallpapers.sort(key=lambda item: (item["category"], item["title"], item["image_url"]))
    grouped = {}
    for item in wallpapers:
        grouped.setdefault(item["category"], []).append(item)
    categories = [
        {"id": _category_id(name), "name": name, "count": len(values), "cover": values[0]["image_url"]}
        for name, values in sorted(grouped.items())
    ]
    search = _search_index(wallpapers)
    pages = _pages(wallpapers)
    current_hash = _catalog_hash(wallpapers, categories)
    config = {
        "api_version": 1,
        "content_version": _content_version(current_hash),
        "total_items": len(wallpapers),
        "total_pages": len(pages),
        "items_per_page": ITEMS_PER_PAGE,
        "generated_at": utc_iso(),
        "catalog_hash": current_hash,
    }
    local_images = [{"relative": item["relative"], "path": item["relative"]} for item in items]
    _validate_catalog(wallpapers, categories, search, pages, config, local_images)
    _validate_metadata(metadata)
    api_root = Path(API_DIR)
    api_root.parent.mkdir(parents=True, exist_ok=True)
    stage_dir = Path(tempfile.mkdtemp(prefix=f".{api_root.name}.staging-", dir=str(api_root.parent)))
    try:
        (stage_dir / "wallpapers").mkdir(parents=True, exist_ok=True)
        for page in pages:
            _write_json(stage_dir / "wallpapers" / f"page_{page['page']}.json", page)
        _write_json(stage_dir / "categories.json", categories)
        _write_json(stage_dir / "search_index.json", search, compact=True)
        _write_json(
            stage_dir / ID_METADATA_FILENAME,
            {"schema_version": METADATA_SCHEMA_VERSION, "wallpapers": metadata},
        )
        _write_json(stage_dir / CONFIG_FILENAME, config)
        _write_models(stage_dir)
        validate_generated_api(stage_dir)
        _replace_staged_output(stage_dir)
    finally:
        shutil.rmtree(stage_dir, ignore_errors=True)
    summary = validate_generated_api()
    print("Wallune static API generated and validated: " + str(summary))
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate or validate the Wallune static API")
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="validate the existing generated API without modifying any files",
    )
    args = parser.parse_args(argv)
    try:
        if args.validate_only:
            summary = validate_generated_api()
            print("Wallune static API validation passed: " + str(summary))
        else:
            process_images()
    except Exception as exc:
        print(f"Wallune static API {'validation' if args.validate_only else 'generation'} failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
