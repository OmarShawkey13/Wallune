"""Generate and validate the Wallune static API.

This repository is a static content backend. The script produces GitHub Raw
JSON and image references, with no server process. Generation uses Pillow to
create the lightweight WebP thumbnails served beside the catalog files.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import urllib.parse
import uuid

# Generator settings.
IMAGE_DIR = "images"
API_DIR = "api/v1"
API_VERSION = 1
GITHUB_USERNAME = os.getenv("WALLUNE_GH_USER", "OmarShawkey13")
GITHUB_REPO_NAME = os.getenv("WALLUNE_GH_REPO", "Wallune")
BRANCH = os.getenv("WALLUNE_GH_BRANCH", "main")
VALID_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ITEMS_PER_PAGE = 20
THUMBNAIL_MAX_SIZE = (480, 854)
THUMBNAIL_QUALITY = 80
THUMBNAIL_VERSION = 1
SEARCH_SCHEMA_VERSION = 2
WALLPAPER_ID_VERSION = 2
THUMBNAIL_SUBDIR = "thumbnails"
CONFIG_FILENAME = "config.json"
MAX_WORKERS = min(32, (os.cpu_count() or 1) + 4)

_PAGE_RE = re.compile(r"page_(\d+)\.json$")
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$"
)


def get_clean_title(filename):
    name, _ = os.path.splitext(filename)
    return name.replace("_", " ").replace("-", " ").title()


def utc_iso(timestamp=None):
    value = (
        datetime.now(timezone.utc)
        if timestamp is None
        else datetime.fromtimestamp(timestamp, timezone.utc)
    )
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _valid_uuid(value):
    return isinstance(value, str) and bool(_UUID_RE.fullmatch(value))


def _normalize(path):
    return str(path).replace("\\", "/").lstrip("./")


def _encoded_path(*parts):
    return "/".join(urllib.parse.quote(str(part), safe="") for part in parts)


def _raw_url(relative):
    base = (
        "https://raw.githubusercontent.com/"
        + _encoded_path(GITHUB_USERNAME, GITHUB_REPO_NAME, BRANCH)
        + "/"
    )
    return base + _encoded_path(*_normalize(relative).split("/"))


def _url(category, filename):
    return _raw_url(f"{IMAGE_DIR}/{category}/{filename}")


def _thumbnail_relative(category, record_id):
    return f"{THUMBNAIL_SUBDIR}/{category}/{record_id}.webp"


def _search_image_path(item):
    filename = urllib.parse.unquote(
        urllib.parse.urlsplit(item["image_url"]).path.rsplit("/", 1)[-1]
    )
    return "../../" + _encoded_path(IMAGE_DIR, item["category"], filename)


def _search_thumbnail_path(item):
    return _encoded_path(THUMBNAIL_SUBDIR, item["category"], f"{item['id']}.webp")


def _thumbnail_url(category, record_id, api_dir=None):
    return _raw_url(f"{_normalize(api_dir or API_DIR)}/{_thumbnail_relative(category, record_id)}")


def _category_id(name):
    """Return a deterministic UUID for a category name."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"wallune:category:{name}"))


def _wallpaper_id(content_hash):
    """Return a deterministic UUID for an image content hash."""
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"wallune:wallpaper:{content_hash}"))


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
    for category in sorted((item for item in root.iterdir() if item.is_dir()), key=lambda x: x.name):
        for path in sorted(category.iterdir(), key=lambda x: x.name):
            if path.is_file() and path.suffix.lower() in VALID_EXTENSIONS:
                yield category.name, path.name, str(path)


def _reject_duplicate_images(items):
    by_hash = {}
    for item in items:
        by_hash.setdefault(item["content_hash"], []).append(item["relative"])
    duplicates = [paths for paths in by_hash.values() if len(paths) > 1]
    if duplicates:
        details = "; ".join(", ".join(paths) for paths in duplicates)
        raise ValueError(f"Duplicate image bytes found; remove one copy: {details}")


def _config_path(api_dir=None):
    return Path(api_dir or API_DIR) / CONFIG_FILENAME


def _read_json_safe(path):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None


def _load_previous_records(api_dir=None):
    pages_dir = Path(api_dir or API_DIR) / "wallpapers"
    if not pages_dir.is_dir():
        return []

    records = []
    paths = sorted(
        (path for path in pages_dir.iterdir() if _PAGE_RE.fullmatch(path.name)),
        key=lambda path: int(_PAGE_RE.fullmatch(path.name).group(1)),
    )
    for path in paths:
        page = _read_json_safe(path)
        if isinstance(page, dict) and isinstance(page.get("data"), list):
            records.extend(item for item in page["data"] if isinstance(item, dict))
    return records


def _render_thumbnail_bytes(source):
    """Render WebP thumbnail bytes in memory using canonical settings."""
    Image, ImageOps = _pillow()
    with Image.open(source) as original:
        image = ImageOps.exif_transpose(original)
        image.thumbnail(THUMBNAIL_MAX_SIZE, Image.Resampling.LANCZOS)
        mode = "RGBA" if ("A" in image.getbands() or "transparency" in image.info) else "RGB"
        image = image.convert(mode)
        buffer = io.BytesIO()
        image.save(buffer, format="WEBP", quality=THUMBNAIL_QUALITY, method=6)
        return buffer.getvalue()


def _assign_ids(items, previous, api_dir=None):
    previous_by_id = {}
    for record in previous:
        record_id = record.get("id")
        if not _valid_uuid(record_id):
            continue
        previous_by_id.setdefault(record_id, record)

    public = []
    for item in items:
        record_id = _wallpaper_id(item["content_hash"])
        previous_record = previous_by_id.get(record_id)

        updated_at = item["updated_at"]
        if previous_record:
            try:
                _parse_utc(previous_record.get("updated_at"))
                updated_at = previous_record["updated_at"]
            except ValueError:
                pass

        public.append({
            "id": record_id,
            "title": item["title"],
            "category": item["category"],
            "image_url": item["image_url"],
            "thumbnail_url": _thumbnail_url(item["category"], record_id, api_dir),
            "size": item["size"],
            "updated_at": updated_at,
            "width": item["width"],
            "height": item["height"],
        })
    return public


def _pillow():
    try:
        from PIL import Image, ImageOps
    except ImportError as exc:
        raise RuntimeError(
            "Image processing requires Pillow; install it with 'python -m pip install -r requirements.txt'"
        ) from exc
    return Image, ImageOps


def get_image_size(fname):
    try:
        Image, _ = _pillow()
        with Image.open(fname) as image:
            width, height = image.size
        return (width, height) if width > 0 and height > 0 else None
    except (OSError, ValueError):
        return None


def _thumbnail_is_valid(path):
    try:
        Image, _ = _pillow()
        with Image.open(path) as image:
            if image.format != "WEBP":
                return False
            width, height = image.size
            if not (0 < width <= THUMBNAIL_MAX_SIZE[0] and 0 < height <= THUMBNAIL_MAX_SIZE[1]):
                return False
            image.verify()
        return True
    except (OSError, RuntimeError, ValueError):
        return False


def _can_reuse_thumbnails(api_dir):
    thumbnail_root = Path(api_dir) / THUMBNAIL_SUBDIR
    config = _read_json_safe(_config_path(api_dir))
    if not thumbnail_root.is_dir() or not isinstance(config, dict):
        return False
    version = config.get("thumbnail_version")
    if type(version) is int and version == THUMBNAIL_VERSION:
        return True
    return version is None and any(thumbnail_root.rglob("*.webp"))


def _reuse_thumbnail(source, target):
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)


def _thumbnail_cache_by_id(api_root):
    thumbnail_root = Path(api_root) / THUMBNAIL_SUBDIR
    cached = {}
    if thumbnail_root.is_dir():
        for candidate in sorted(thumbnail_root.rglob("*.webp")):
            if candidate.is_file():
                cached.setdefault(candidate.stem, candidate)
    return cached


def _write_thumbnail(source, target):
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(_render_thumbnail_bytes(source))


def _search_index(wallpapers):
    return [
        {
            "id": item["id"],
            "title": item["title"],
            "category": item["category"],
            "image_path": _search_image_path(item),
            "thumbnail_path": _search_thumbnail_path(item),
            "width": item["width"],
            "height": item["height"],
        }
        for item in wallpapers
    ]


def _pages(wallpapers):
    total = len(wallpapers)
    count = (total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    return [
        {
            "page": page,
            "total_pages": count,
            "total_items": total,
            "items_per_page": ITEMS_PER_PAGE,
            "has_next": page < count,
            "has_prev": page > 1,
            "data": list(wallpapers[(page - 1) * ITEMS_PER_PAGE : page * ITEMS_PER_PAGE]),
        }
        for page in range(1, count + 1)
    ]


def _catalog_hash(wallpapers, categories, api_version=None):
    api_version = API_VERSION if api_version is None else api_version
    semantic = [{k: v for k, v in item.items() if k != "updated_at"} for item in wallpapers]
    raw = json.dumps(
        {
            "wallpapers": semantic,
            "categories": categories,
            "api_version": api_version,
            "items_per_page": ITEMS_PER_PAGE,
            "thumbnail_version": THUMBNAIL_VERSION,
            "search_schema_version": SEARCH_SCHEMA_VERSION,
            "wallpaper_id_version": WALLPAPER_ID_VERSION,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _content_version(current_hash, api_dir=None):
    previous = _read_json_safe(_config_path(api_dir))
    if isinstance(previous, dict):
        old = previous.get("content_version")
        if _is_int(old) and old > 0:
            return old if previous.get("catalog_hash") == current_hash else old + 1
    return 1


def _generated_at(current_hash, api_dir=None):
    previous = _read_json_safe(_config_path(api_dir))
    if isinstance(previous, dict) and previous.get("catalog_hash") == current_hash:
        generated_at = previous.get("generated_at")
        try:
            _parse_utc(generated_at)
            return generated_at
        except ValueError:
            pass
    return utc_iso()


def _generated_output_files(root):
    root = Path(root)
    files = [
        path
        for path in (root / "categories.json", root / "search_index.json", root / CONFIG_FILENAME)
        if path.is_file()
    ]
    pages = root / "wallpapers"
    if pages.is_dir():
        files.extend(p for p in pages.iterdir() if p.is_file() and _PAGE_RE.fullmatch(p.name))
    thumbnails = root / THUMBNAIL_SUBDIR
    if thumbnails.is_dir():
        files.extend(p for p in thumbnails.rglob("*.webp") if p.is_file())
    return files


def _remove_empty_dirs(root_dir):
    root_path = Path(root_dir)
    if not root_path.is_dir():
        return
    for path in sorted(root_path.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if path.is_dir():
            try:
                path.rmdir()
            except OSError:
                pass


def _replace_staged_output(stage_dir, api_dir=None, api_version=None, precomputed_images=None):
    """Move generated files into place and restore the previous set on failure."""
    api_dir = api_dir or API_DIR
    api_root = Path(api_dir)
    api_root.mkdir(parents=True, exist_ok=True)
    (api_root / "wallpapers").mkdir(parents=True, exist_ok=True)

    stage_dir = Path(stage_dir)
    stage_files = [path for path in stage_dir.rglob("*") if path.is_file()]
    existing_files = _generated_output_files(api_root)
    backup_dir = Path(
        tempfile.mkdtemp(prefix=f".{api_root.name}.backup-", dir=str(api_root.parent))
    )
    backup_map = {}
    installed_files = set()

    try:
        for path in existing_files:
            relative = path.relative_to(api_root)
            backup_path = backup_dir / relative
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            os.replace(path, backup_path)
            backup_map[path] = backup_path

        for path in stage_files:
            relative = path.relative_to(stage_dir)
            target = api_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(path, target)
            installed_files.add(target)

        _remove_empty_dirs(api_root / THUMBNAIL_SUBDIR)
        summary = validate_generated_api(
            api_root, api_version, precomputed_images=precomputed_images
        )
    except Exception:
        for path in installed_files:
            if path.exists():
                try:
                    path.unlink()
                except OSError:
                    pass
        for path, backup_path in backup_map.items():
            if backup_path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                os.replace(backup_path, path)
        raise
    finally:
        shutil.rmtree(backup_dir, ignore_errors=True)

    return summary


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
    fields = (
        "id", "title", "category", "image_url", "thumbnail_url",
        "size", "updated_at", "width", "height",
    )
    missing = [field for field in fields if field not in item]
    if missing:
        raise ValueError(f"{context} is missing fields: {', '.join(missing)}")
    for field in ("id", "title", "category", "image_url", "thumbnail_url", "updated_at"):
        if not isinstance(item[field], str) or not item[field]:
            raise ValueError(f"{context}.{field} must be a non-empty string")
    if not _valid_uuid(item["id"]):
        raise ValueError(f"{context}.id is not a UUID")
    for field in ("size", "width", "height"):
        if not _is_int(item[field]) or item[field] <= 0:
            raise ValueError(f"{context}.{field} must be a positive integer")
    _parse_utc(item["updated_at"])


def _validate_search_record(item, context):
    if not isinstance(item, dict):
        raise ValueError(f"{context} must be an object")
    fields = ("id", "title", "category", "image_path", "thumbnail_path", "width", "height")
    missing = [field for field in fields if field not in item]
    if missing:
        raise ValueError(f"{context} is missing fields: {', '.join(missing)}")
    if not _valid_uuid(item["id"]):
        raise ValueError(f"{context}.id is not a UUID")
    for field in ("title", "category", "image_path", "thumbnail_path"):
        if not isinstance(item[field], str) or not item[field]:
            raise ValueError(f"{context}.{field} must be a non-empty string")
    for field in ("width", "height"):
        if not _is_int(item[field]) or item[field] <= 0:
            raise ValueError(f"{context}.{field} must be a positive integer")


def _validate_catalog(
    wallpapers,
    categories,
    search,
    pages,
    config,
    local_images,
    api_dir=None,
    api_version=None,
    url_api_dir=None,
):
    if not isinstance(wallpapers, list):
        raise ValueError("Wallpaper data must be a list")
    if not isinstance(categories, list):
        raise ValueError("categories.json must contain an array")
    if not isinstance(search, list):
        raise ValueError("search_index.json must contain an array")
    if not isinstance(pages, list):
        raise ValueError("Wallpaper pages must be a list")

    api_dir = api_dir or API_DIR
    api_version = API_VERSION if api_version is None else api_version
    api_root = Path(api_dir)
    url_api_dir = url_api_dir or api_dir
    total = len(wallpapers)
    page_count = (total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE

    if len(pages) != page_count:
        raise ValueError("Wallpaper page count does not match total_items")

    ids = []
    urls = []
    local = {_normalize(item["relative"]): item for item in local_images}
    seen_paths = []
    expected_thumbnail_paths = set()

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
        thumbnail_relative = _thumbnail_relative(item["category"], item["id"])
        if item["thumbnail_url"] != _thumbnail_url(item["category"], item["id"], url_api_dir):
            raise ValueError("Wallpaper thumbnail URL is not canonical")
        thumbnail_path = api_root / Path(thumbnail_relative.replace("/", os.sep))
        if not thumbnail_path.is_file():
            raise ValueError(f"Wallpaper thumbnail is missing: {thumbnail_path}")
        if not _thumbnail_is_valid(thumbnail_path):
            raise ValueError(f"Wallpaper thumbnail is invalid or oversized: {thumbnail_path}")
        expected_thumbnail_paths.add(thumbnail_relative)
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
        required = ("id", "name", "count", "cover", "cover_thumbnail_url")
        if any(field not in category for field in required):
            raise ValueError(f"categories[{index}] is missing a required field")
        if not _valid_uuid(category["id"]) or not isinstance(category["name"], str) or not category["name"]:
            raise ValueError(f"categories[{index}] has invalid id or name")
        if not _is_int(category["count"]) or category["count"] < 0:
            raise ValueError(f"categories[{index}].count must be a non-negative integer")
        if not isinstance(category["cover"], str) or not category["cover"]:
            raise ValueError(f"categories[{index}].cover must be a non-empty string")
        if not isinstance(category["cover_thumbnail_url"], str) or not category["cover_thumbnail_url"]:
            raise ValueError(f"categories[{index}].cover_thumbnail_url must be a non-empty string")
        category_ids.append(category["id"])
        category_names.append(category["name"])

    if len(set(category_ids)) != len(category_ids):
        raise ValueError("Category IDs are duplicated")
    if len(set(category_names)) != len(category_names):
        raise ValueError("Category names are duplicated")
    if set(category_names) != {item["category"] for item in wallpapers}:
        raise ValueError("Category names do not match wallpaper records")

    for category in categories:
        matching = [item for item in wallpapers if item["category"] == category["name"]]
        if (
            category["id"] != _category_id(category["name"])
            or category["count"] != len(matching)
            or category["cover"] not in {item["image_url"] for item in matching}
            or category["cover_thumbnail_url"] not in {item["thumbnail_url"] for item in matching}
        ):
            raise ValueError("Category count or cover is invalid")
        if _url_relative(category["cover"]) not in expected_paths:
            raise ValueError("Category cover does not map to a local image")

    search_ids = []
    for index, result in enumerate(search):
        _validate_search_record(result, f"search_index[{index}]")
        search_ids.append(result["id"])
    if len(search_ids) != len(set(search_ids)):
        raise ValueError("Search index contains duplicate IDs")
    if set(search_ids) != set(ids):
        raise ValueError("Search index is incomplete or contains extra records")
    expected_search = {item["id"]: item for item in _search_index(wallpapers)}
    for result in search:
        if result != expected_search[result["id"]]:
            raise ValueError("Search index metadata differs from canonical data")

    thumbnail_root = api_root / THUMBNAIL_SUBDIR
    actual_thumbnail_paths = (
        {
            path.relative_to(api_root).as_posix()
            for path in thumbnail_root.rglob("*.webp")
            if path.is_file()
        }
        if thumbnail_root.is_dir()
        else set()
    )
    if actual_thumbnail_paths != expected_thumbnail_paths:
        raise ValueError("Thumbnail files do not match the wallpaper catalog")

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
        expected_length = (
            ITEMS_PER_PAGE if index < page_count else total - ITEMS_PER_PAGE * (page_count - 1)
        )
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
    if not _is_int(config.get("api_version")) or config.get("api_version") != api_version:
        raise ValueError("config.json api_version is invalid")
    if not _is_int(config.get("thumbnail_version")) or config["thumbnail_version"] != THUMBNAIL_VERSION:
        raise ValueError("config.json thumbnail_version is invalid")
    if not _is_int(config.get("search_schema_version")) or config["search_schema_version"] != SEARCH_SCHEMA_VERSION:
        raise ValueError("config.json search_schema_version is invalid")
    if not _is_int(config.get("wallpaper_id_version")) or config["wallpaper_id_version"] != WALLPAPER_ID_VERSION:
        raise ValueError("config.json wallpaper_id_version is invalid")
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
    if config["catalog_hash"] != _catalog_hash(wallpapers, categories, api_version):
        raise ValueError("config.json catalog_hash does not match the catalog")
    _parse_utc(config.get("generated_at"))


def _write_json(path, payload, compact=False):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(
            payload,
            handle,
            ensure_ascii=False,
            separators=(",", ":") if compact else None,
            indent=None if compact else 2,
        )
        handle.write("\n")


def validate_generated_api(api_dir=None, api_version=None, url_api_dir=None, precomputed_images=None):
    api_root = Path(api_dir or API_DIR)
    api_version = API_VERSION if api_version is None else api_version
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
    if precomputed_images is not None:
        local_images = precomputed_images
    else:
        local_images = [
            {"relative": f"{IMAGE_DIR}/{category}/{filename}", "path": path}
            for category, filename, path in _iter_images()
        ]

    _validate_catalog(
        wallpapers, categories, search, pages, config, local_images, api_root, api_version, url_api_dir
    )

    local_by_relative = {_normalize(item["relative"]): item for item in local_images}
    for item in wallpapers:
        relative = _url_relative(item["image_url"])
        local = local_by_relative.get(relative)
        if local is None:
            raise ValueError(f"Wallpaper URL does not map to a local image: {relative}")
        actual_path = local["path"]
        actual_size = local.get("size") or os.path.getsize(actual_path)
        actual_dimensions = (
            (local["width"], local["height"])
            if "width" in local and "height" in local
            else get_image_size(actual_path)
        )
        actual_hash = local.get("content_hash") or _sha256(actual_path)

        if _wallpaper_id(actual_hash) != item["id"]:
            raise ValueError(f"Wallpaper ID does not match the image content: {relative}")
        if item["size"] != actual_size:
            raise ValueError(f"Wallpaper size does not match the image: {relative}")
        if not actual_dimensions or (item["width"], item["height"]) != actual_dimensions:
            raise ValueError(f"Wallpaper dimensions do not match the image: {relative}")

    return {
        "total_items": len(wallpapers),
        "total_pages": len(pages),
        "categories": len(categories),
        "search_items": len(search),
    }


def _inspect_single_image(entry):
    category, filename, path = entry
    dimensions = get_image_size(path)
    if not dimensions or dimensions[0] <= 0 or dimensions[1] <= 0:
        raise ValueError(f"Could not read positive image dimensions: {path}")
    stat = os.stat(path)
    return {
        "category": category,
        "filename": filename,
        "relative": f"{IMAGE_DIR}/{category}/{filename}",
        "path": path,
        "title": get_clean_title(filename),
        "image_url": _url(category, filename),
        "size": stat.st_size,
        "updated_at": utc_iso(),
        "width": dimensions[0],
        "height": dimensions[1],
        "content_hash": _sha256(path),
    }


def process_images(api_dir=None, api_version=None):
    api_dir = api_dir or API_DIR
    api_version = API_VERSION if api_version is None else api_version
    if not os.path.isdir(IMAGE_DIR):
        raise FileNotFoundError(f"Directory '{IMAGE_DIR}' not found")

    previous = _load_previous_records(api_dir)
    raw_entries = list(_iter_images())

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        items = list(executor.map(_inspect_single_image, raw_entries))

    _reject_duplicate_images(items)
    wallpapers = _assign_ids(items, previous, api_dir)
    wallpapers.sort(key=lambda item: (item["category"], item["title"], item["image_url"]))

    grouped = {}
    for item in wallpapers:
        grouped.setdefault(item["category"], []).append(item)

    categories = [
        {
            "id": _category_id(name),
            "name": name,
            "count": len(values),
            "cover": values[0]["image_url"],
            "cover_thumbnail_url": values[0]["thumbnail_url"],
        }
        for name, values in sorted(grouped.items())
    ]

    search = _search_index(wallpapers)
    pages = _pages(wallpapers)
    current_hash = _catalog_hash(wallpapers, categories, api_version)
    config = {
        "api_version": api_version,
        "thumbnail_version": THUMBNAIL_VERSION,
        "search_schema_version": SEARCH_SCHEMA_VERSION,
        "wallpaper_id_version": WALLPAPER_ID_VERSION,
        "content_version": _content_version(current_hash, api_dir),
        "total_items": len(wallpapers),
        "total_pages": len(pages),
        "items_per_page": ITEMS_PER_PAGE,
        "generated_at": _generated_at(current_hash, api_dir),
        "catalog_hash": current_hash,
    }

    api_root = Path(api_dir)
    api_root.parent.mkdir(parents=True, exist_ok=True)
    stage_dir = Path(
        tempfile.mkdtemp(prefix=f".{api_root.name}.staging-", dir=str(api_root.parent))
    )

    try:
        (stage_dir / "wallpapers").mkdir(parents=True, exist_ok=True)
        for page in pages:
            _write_json(stage_dir / "wallpapers" / f"page_{page['page']}.json", page)
        _write_json(stage_dir / "categories.json", categories)
        _write_json(stage_dir / "search_index.json", search, compact=True)
        _write_json(stage_dir / CONFIG_FILENAME, config)

        public_ids_by_url = {item["image_url"]: item["id"] for item in wallpapers}
        can_reuse = _can_reuse_thumbnails(api_root)
        cached_thumbnails = _thumbnail_cache_by_id(api_root) if can_reuse else {}
        for category in grouped:
            (stage_dir / THUMBNAIL_SUBDIR / category).mkdir(parents=True, exist_ok=True)

        def _handle_thumbnail(item):
            record_id = public_ids_by_url[item["image_url"]]
            thumbnail_relative = _thumbnail_relative(item["category"], record_id)
            target = stage_dir / Path(thumbnail_relative.replace("/", os.sep))
            cached = cached_thumbnails.get(record_id)
            expected = api_root / Path(thumbnail_relative.replace("/", os.sep))
            if expected.is_file():
                cached = expected
            if can_reuse and cached is not None and _thumbnail_is_valid(cached):
                _reuse_thumbnail(cached, target)
            else:
                _write_thumbnail(item["path"], target)

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            list(executor.map(_handle_thumbnail, items))

        summary = _replace_staged_output(
            stage_dir, api_dir, api_version, precomputed_images=items
        )
    finally:
        shutil.rmtree(stage_dir, ignore_errors=True)

    print(f"Wallune static API generated and validated: {summary}")
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate or validate the Wallune static API")
    parser.add_argument("--api-dir", help="output directory, default: api/v1")
    parser.add_argument(
        "--api-version", type=int, help="API version written to config.json, default: 1"
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="validate the existing generated API without modifying any files",
    )
    args = parser.parse_args(argv)
    try:
        if args.validate_only:
            summary = validate_generated_api(args.api_dir, args.api_version)
            print(f"Wallune static API validation passed: {summary}")
        else:
            process_images(args.api_dir, args.api_version)
    except Exception as exc:
        action = "validation" if args.validate_only else "generation"
        print(f"Wallune static API {action} failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
