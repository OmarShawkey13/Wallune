"""Generate and validate the Wallune static API.

This repository is a static content backend. The script produces GitHub Raw
JSON and image references, with no server or external runtime dependency.
"""

from datetime import datetime, timezone
import hashlib
import os
import json
import re
import struct
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


def _metadata_path():
    return os.path.join(API_DIR, ID_METADATA_FILENAME)


def _config_path():
    return os.path.join(API_DIR, CONFIG_FILENAME)


def _validate_metadata(records):
    seen = set()
    for record in records:
        record_id = record.get("id")
        if not _valid_uuid(record_id) or record_id in seen:
            raise ValueError("UUID metadata contains an invalid or duplicate ID")
        if not isinstance(record.get("content_hash"), str) or not re.fullmatch(r"[0-9a-f]{64}", record["content_hash"]):
            raise ValueError("UUID metadata contains an invalid content hash")
        if not isinstance(record.get("aliases", []), list):
            raise ValueError("UUID metadata contains invalid aliases")
        seen.add(record_id)


def _load_metadata():
    path = _metadata_path()
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
    records = payload.get("wallpapers", []) if isinstance(payload, dict) else []
    if not isinstance(records, list):
        raise ValueError("Invalid wallpaper_ids.json format")
    normalized = []
    for record in records:
        normalized.append({
            "id": record.get("id"),
            "content_hash": record.get("content_hash"),
            "aliases": sorted({_normalize(alias) for alias in record.get("aliases", [])}),
            "retired": bool(record.get("retired", False)),
        })
    _validate_metadata(normalized)
    return normalized


def _legacy_pages():
    result = []
    directory = Path(API_DIR) / "wallpapers"
    if directory.is_dir():
        paths = sorted(
            (path for path in directory.iterdir() if _PAGE_RE.fullmatch(path.name)),
            key=lambda path: int(_PAGE_RE.fullmatch(path.name).group(1)),
        )
        for path in paths:
            with open(path, encoding="utf-8") as handle:
                result.extend(json.load(handle).get("data", []))
    legacy = Path("wallpapers.json")
    if legacy.is_file():
        try:
            with open(legacy, encoding="utf-8") as handle:
                payload = json.load(handle)
            result.extend(payload.get("wallpapers", []) if isinstance(payload, dict) else payload)
        except (OSError, ValueError):
            pass
    return result


def _load_identity_records():
    records = _load_metadata()
    by_id = {record["id"]: record for record in records}
    for item in _legacy_pages():
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
        record = by_id.get(record_id)
        if record is None:
            record = {"id": record_id, "content_hash": digest, "aliases": [], "retired": False}
            records.append(record)
            by_id[record_id] = record
        elif record["content_hash"] != digest:
            raise ValueError("A legacy UUID maps to different image bytes")
        if relative not in record["aliases"]:
            record["aliases"].append(relative)
    _validate_metadata(records)
    return records


def _assign_ids(items, previous):
    metadata = [{
        "id": record["id"],
        "content_hash": record["content_hash"],
        "aliases": list(record.get("aliases", [])),
        "retired": bool(record.get("retired", False)),
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
                "_was_active": True,
            }
            metadata.append(record)
            by_hash.setdefault(item["content_hash"], []).append(record)
        record["retired"] = False
        record["aliases"] = sorted(set(record["aliases"]) | {item["relative"]})
        assigned.add(record["id"])
        public.append({
            "id": record["id"],
            "title": item["title"],
            "category": item["category"],
            "image_url": item["image_url"],
            "size": item["size"],
            "updated_at": item["updated_at"],
            "width": item["width"],
            "height": item["height"],
        })
    for record in metadata:
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
    raw = json.dumps({"wallpapers": semantic, "categories": categories}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
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


def _cleanup_pages():
    directory = Path(API_DIR) / "wallpapers"
    directory.mkdir(parents=True, exist_ok=True)
    for path in directory.iterdir():
        if path.is_file() and _PAGE_RE.fullmatch(path.name):
            path.unlink()


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


def _validate_catalog(wallpapers, categories, search, pages, config, local_images):
    total = len(wallpapers)
    page_count = (total + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    if len(pages) != page_count or sum(item["count"] for item in categories) != total:
        raise ValueError("Wallpaper and category totals are inconsistent")
    ids = [item.get("id") for item in wallpapers]
    urls = [item.get("image_url") for item in wallpapers]
    if any(not _valid_uuid(item) for item in ids) or len(set(ids)) != len(ids):
        raise ValueError("Wallpaper IDs are missing, invalid, or duplicated")
    if len(set(urls)) != len(urls):
        raise ValueError("Wallpaper URLs are duplicated")
    local = {_normalize(item["relative"]): item for item in local_images}
    seen_paths = []
    fields = ("id", "title", "category", "image_url", "size", "updated_at", "width", "height")
    for item in wallpapers:
        if any(field not in item for field in fields):
            raise ValueError("Wallpaper record is missing a field")
        if item["size"] <= 0 or item["width"] <= 0 or item["height"] <= 0:
            raise ValueError("Wallpaper metadata contains non-positive values")
        _parse_utc(item["updated_at"])
        relative = _url_relative(item["image_url"])
        if not relative or relative not in local:
            raise ValueError("Wallpaper URL does not map to a local image")
        parts = relative.split("/")
        if len(parts) != 3 or parts[0] != IMAGE_DIR:
            raise ValueError("Wallpaper URL path is invalid")
        if item["image_url"] != _url(parts[1], parts[2]):
            raise ValueError("Wallpaper URL does not use canonical Wallune identity")
        seen_paths.append(relative)
    expected_paths = set(local)
    if len(seen_paths) != len(expected_paths) or set(seen_paths) != expected_paths:
        raise ValueError("Local images and generated records are not a one-to-one mapping")
    category_ids = [item.get("id") for item in categories]
    if any(not _valid_uuid(value) for value in category_ids) or len(set(category_ids)) != len(category_ids):
        raise ValueError("Category IDs are missing, invalid, or duplicated")
    names = {item["name"] for item in categories}
    if names != {item["category"] for item in wallpapers}:
        raise ValueError("Category names do not match wallpaper records")
    for category in categories:
        matching = [item for item in wallpapers if item["category"] == category["name"]]
        if (
            category["id"] != _category_id(category["name"])
            or category["count"] != len(matching)
            or category["cover"] not in {item["image_url"] for item in matching}
        ):
            raise ValueError("Category count or cover is invalid")
    by_id = {item["id"]: item for item in wallpapers}
    search_by_id = {item.get("id"): item for item in search}
    if len(search_by_id) != total or set(search_by_id) != set(by_id):
        raise ValueError("Search index is incomplete or contains orphans")
    for record_id, result in search_by_id.items():
        if any(result.get(field) != by_id[record_id].get(field) for field in fields):
            raise ValueError("Search index metadata differs from canonical data")
    for index, page in enumerate(pages, 1):
        expected_length = ITEMS_PER_PAGE if index < page_count else total - ITEMS_PER_PAGE * (page_count - 1)
        if (
            page.get("page") != index
            or page.get("total_pages") != page_count
            or page.get("total_items") != total
            or page.get("items_per_page") != ITEMS_PER_PAGE
            or len(page.get("data", [])) != expected_length
            or page.get("has_next") != (index < page_count)
            or page.get("has_prev") != (index > 1)
        ):
            raise ValueError("Pagination metadata is invalid")
    if (
        config.get("api_version") != 1
        or not isinstance(config.get("content_version"), int)
        or config["content_version"] <= 0
        or config.get("total_items") != total
        or config.get("total_pages") != page_count
        or config.get("items_per_page") != ITEMS_PER_PAGE
    ):
        raise ValueError("config.json totals are invalid")
    _parse_utc(config.get("generated_at"))


def _write_json(path, payload, compact=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, separators=(",", ":") if compact else None, indent=None if compact else 2)
        handle.write("\n")


def _write_models():
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
    os.makedirs(API_DIR, exist_ok=True)
    with open(os.path.join(API_DIR, "models.dart"), "w", encoding="utf-8", newline="\n") as handle:
        handle.write(dart)


def validate_generated_api():
    with open(os.path.join(API_DIR, "categories.json"), encoding="utf-8") as handle:
        categories = json.load(handle)
    with open(os.path.join(API_DIR, "search_index.json"), encoding="utf-8") as handle:
        search = json.load(handle)
    with open(_config_path(), encoding="utf-8") as handle:
        config = json.load(handle)
    directory = Path(API_DIR) / "wallpapers"
    paths = sorted(
        (path for path in directory.iterdir() if _PAGE_RE.fullmatch(path.name)),
        key=lambda path: int(_PAGE_RE.fullmatch(path.name).group(1)),
    )
    pages = []
    for path in paths:
        with open(path, encoding="utf-8") as handle:
            pages.append(json.load(handle))
    wallpapers = [item for page in pages for item in page.get("data", [])]
    local_images = [
        {"relative": f"{IMAGE_DIR}/{category}/{filename}", "path": path}
        for category, filename, path in _iter_images()
    ]
    _validate_catalog(wallpapers, categories, search, pages, config, local_images)
    metadata = _load_metadata()
    active_ids = {item["id"] for item in wallpapers}
    metadata_ids = {record["id"] for record in metadata}
    if not active_ids.issubset(metadata_ids):
        raise ValueError("Generated wallpaper is missing from UUID metadata")
    if any(not record["retired"] and record["id"] not in active_ids for record in metadata):
        raise ValueError("Active UUID metadata contains an orphan")
    return {"total_items": len(wallpapers), "total_pages": len(pages), "categories": len(categories), "search_items": len(search)}


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
            "updated_at": utc_iso(os.stat(path).st_mtime),
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
    os.makedirs(API_DIR, exist_ok=True)
    _cleanup_pages()
    for page in pages:
        _write_json(os.path.join(API_DIR, "wallpapers", f"page_{page['page']}.json"), page)
    _write_json(os.path.join(API_DIR, "categories.json"), categories)
    _write_json(os.path.join(API_DIR, "search_index.json"), search, compact=True)
    _write_json(os.path.join(API_DIR, ID_METADATA_FILENAME), {"schema_version": 1, "wallpapers": metadata})
    _write_json(os.path.join(API_DIR, CONFIG_FILENAME), config)
    _write_models()
    summary = validate_generated_api()
    print("Wallune static API generated and validated: " + str(summary))
    return summary


if __name__ == "__main__":
    process_images()
