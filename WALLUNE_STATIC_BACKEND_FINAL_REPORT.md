# Wallune Static Backend — Review and Final Report

## Scope

This review hardened the GitHub Raw static backend for the Wallune Flutter wallpaper application. The working tree contained 100 supported production images, so the generated API was synchronized with that full catalog. The earlier 17-image sample was treated as sample material and was never used to overwrite the production catalog.

The backend remains static: GitHub serves committed images and JSON files. There is no server process, database, authentication layer, upload endpoint, or deployment step in this change.

## Current production snapshot

| Check | Result |
| --- | ---: |
| Supported images | 100 |
| Categories | 17 |
| API wallpaper records | 100 |
| Page files | `page_1.json` through `page_5.json` |
| Items per page | 20 |
| Final page size | 20 |
| Image bytes | 14,619,642 (about 13.9 MiB) |
| Generated `api/v1` bytes | 292,837 |
| Identity metadata records | 726 |
| Active identities | 100 |
| Retired tombstones | 626 |
| Duplicate image bytes | 0 |
| Duplicate public IDs | 0 |
| Missing local image mappings | 0 |
| Invalid dimensions or sizes | 0 |

The current config is:

```json
{
  "api_version": 1,
  "content_version": 8,
  "total_items": 100,
  "total_pages": 5,
  "items_per_page": 20,
  "generated_at": "2026-10-12T11:39:33Z",
  "catalog_hash": "2af03ac45d1b799b6b21e8a4f23ae935028bbce04f50a04be4db86d98f2900cf"
}
```

## Content review

All 100 current images were reviewed in contact sheets, with suspicious silhouettes checked at full resolution. No retained image shows tobacco, alcohol, drugs, nudity, explicit sexual content, or graphic violence. Weapon and superhero artwork is decorative and non-graphic. The generator also performed a SHA-256 byte comparison and found no duplicate image bytes.

## Generator changes

`generate_api.py` now:

- reads `.jpg`, `.jpeg`, `.png`, and `.webp` files under direct category folders;
- creates canonical, URL-encoded GitHub Raw URLs for `OmarShawkey13/Wallune` on `main`;
- reads positive dimensions and actual file sizes;
- computes SHA-256 content hashes;
- assigns deterministic category UUIDs;
- emits `config.json`, `categories.json`, `search_index.json`, `wallpaper_ids.json`, `models.dart`, and paginated wallpaper pages;
- rejects duplicate image bytes before writing;
- validates the in-memory catalog before writing;
- validates the staged files and the final production files;
- supports `python generate_api.py --validate-only`, which performs no writes and returns a non-zero exit code with an actionable error when validation fails.

Generated pages are exactly `page_1.json` through `page_N.json`. Only files matching `page_<number>.json` are eligible for stale-page cleanup; unrelated files under `api/v1/wallpapers` are preserved.

## Stable wallpaper identity

`api/v1/wallpaper_ids.json` is the durable identity store. Each record contains:

- `id`: the UUID consumed by favorites and local persistence;
- `content_hash`: SHA-256 of the image bytes;
- `aliases`: current and historical `images/<category>/<filename>` paths;
- `retired`: tombstone state;
- `updated_at`: persisted UTC timestamp for the identity.

The rules are:

1. The same bytes keep the same UUID across filename, category, repository, branch, or URL changes.
2. Replacing bytes at the same path creates a new UUID and retires the old UUID.
3. A retired UUID is never reused.
4. A byte-for-byte duplicate is a generation error.
5. After `wallpaper_ids.json` exists, it is authoritative; stale pages cannot silently rebuild identity metadata. An empty metadata file is rejected when legacy pages still contain UUIDs, preventing an identity reset.
6. A valid legacy `updated_at` is preserved during migration. Missing or invalid legacy timestamps use the fixed fallback `2000-01-01T00:00:00Z`.
7. Existing timestamps do not change when filesystem mtime changes or a file is renamed.

Malformed identity metadata fails loudly. The generator never silently resets the identity store.

## Validation coverage

`validate_generated_api()` is read-only and checks:

- exact page filenames, page numbers, page lengths, totals, and navigation flags;
- JSON field types, required fields, UUID format, positive sizes, dimensions, and UTC timestamps;
- every public URL against a real local image;
- actual image size, dimensions, and SHA-256 against public data and identity metadata;
- active public IDs against active metadata IDs, with no retired ID exposed publicly;
- current path ownership and historical aliases;
- category UUIDs, names, counts, and covers;
- search-index completeness, duplicate IDs, and field equality with canonical pages;
- `catalog_hash`, `content_version`, and config totals.

Generation uses a staging directory. Existing generated files are copied to a temporary backup, staged files are replaced, and the result is validated. On an exception, the previous generated files are restored. This is a per-file replacement and rollback process; it does not claim a filesystem-atomic whole-directory swap.

## Tests

The isolated suite contains 26 regression tests and does not access the network or modify production files. It covers:

- empty, one, twenty, and twenty-one image catalogs;
- valid JPEG, PNG, and WebP dimension parsing;
- multiple categories and duplicate filenames in different categories;
- duplicate-byte rejection;
- rename preservation and byte replacement with retired IDs;
- authoritative and malformed identity metadata;
- timestamp stability across mtime changes;
- `content_version` changes when pagination configuration changes;
- wrong size, dimensions, and identity hash;
- page gaps, extra page files, duplicate search rows, and invalid catalog hashes;
- write-failure rollback and validate-only no-write behavior;
- category IDs, category counts, URL encoding, search completeness, and stale-page cleanup.

Commands run successfully:

```bash
python -m unittest discover -s tests -v
python generate_api.py
python generate_api.py --validate-only
git diff --check
```

Result: 26 tests passed, production generation passed for 100 images, validation passed, and `git diff --check` reported no whitespace errors.

## Flutter API contract

Base URL:

```text
https://raw.githubusercontent.com/OmarShawkey13/Wallune/main/api/v1
```

Endpoints:

- `/config.json`
- `/categories.json`
- `/search_index.json`
- `/wallpapers/page_N.json`

Each wallpaper record contains `id`, `title`, `category`, `image_url`, `size`, `updated_at`, `width`, and `height`. Each category record contains `id`, `name`, `count`, and `cover`. `models.dart` contains matching Dart models, including `Category.id` and `ApiConfig`.

The Flutter client can cache `config.json`, `search_index.json`, and page responses. Refresh catalog data when `content_version` changes, use `id` for favorites, and use `width` and `height` for predictable image layouts. Treat non-200 responses, malformed JSON, missing fields, and unavailable images as recoverable errors.

## Files to publish

- `images/`
- `api/v1/config.json`
- `api/v1/categories.json`
- `api/v1/search_index.json`
- `api/v1/wallpaper_ids.json`
- `api/v1/models.dart`
- `api/v1/wallpapers/page_1.json` through `page_5.json`
- `generate_api.py`
- `tests/`
- `README.md`
- `STATIC_BACKEND.md`
- this report

Do not delete `wallpaper_ids.json`, replace the paginated API with a monolithic `wallpapers.json`, or add a server runtime. Review image licensing and redistribution rights before publishing to GitHub.
