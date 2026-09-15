# Wallune Static Backend — Final Report

## 1. Summary

The repository was hardened as a GitHub Raw static backend for the Wallune Flutter wallpaper application.

Implemented changes:

- Canonicalized all generated URLs to OmarShawkey13/Wallune on main.
- Reworked UUID persistence around image-content hashes and committed metadata.
- Added retired UUID tombstones so deleted IDs are not reassigned.
- Added safe stale-page cleanup for generated page files only.
- Added UTC-correct timestamps.
- Expanded the local search index with displayable wallpaper metadata.
- Added config.json with API and catalog version metadata.
- Added pre-write and post-write validation of the complete catalog.
- Added deterministic UUIDs to category records and Dart models.
- Added duplicate-byte detection to prevent duplicate images from entering the catalog.
- Regenerated the real catalog and added isolated standard-library tests.
- Updated README.md and the static backend documentation.
- Performed a visual content review, removed one clearly identifiable tobacco image, and removed four byte-identical duplicate files.

No Flutter application, image binary, server runtime, database, AWS service, or external network dependency was added.

## Visual Content Review

All 674 source images in the original catalog were reviewed in contact sheets and suspicious filenames were checked at full resolution. One image clearly showed a lit cigarette and was removed from `images`: `images/Abstract/smoking_neon_skull.jpg`. Four byte-identical duplicate files were also removed: `images/Abstract/cloaked_figure_skull_gby34.jpg`, `images/Animals/dove_silhouette_ixylt.jpg`, `images/Nature/sunset_landscape_with_birds_bcte3.jpg`, and `images/Space/milky_way_canopy_2.jpg`. No clear alcohol, drug, nudity, explicit sexual content, casino, card-table, or wagering imagery was identified. Atmospheric smoke, fantasy characters, weapons artwork, and ordinary non-alcoholic drinks were left in place because they did not show one of those prohibited items.

The removed files are stored outside the repository under `D:\wallpaper_backend_quarantine_20260915\images\...` for recovery if needed. Their UUIDs are retained as retired tombstones so they cannot be reassigned.

After cleanup, an additional low-resolution perceptual comparison found no near-duplicate pairs among the 669 remaining images.

## 2. Repository Identity

- Owner: OmarShawkey13
- Repository: Wallune
- Branch: main
- Production base: https://raw.githubusercontent.com/OmarShawkey13/Wallune/main/

The generator constants and all regenerated image_url and cover values use this identity.

## 3. Generator Improvements

generate_api.py now:

- reads only .jpg, .jpeg, .png, and .webp;
- traverses category directories in deterministic order;
- extracts dimensions without third-party libraries;
- computes file size and a SHA-256 content fingerprint;
- converts filesystem timestamps to timezone-aware UTC;
- sorts records by category, title, and URL;
- writes paginated pages with 20 items per page;
- removes only files matching page_<number>.json before writing pages;
- writes categories, search index, ID metadata, config, and Dart models;
- validates the in-memory catalog before writing and validates the files again afterward;
- raises an exception and exits non-zero when an invariant fails.

## 4. Stable ID Strategy

api/v1/wallpaper_ids.json is the durable identity store. Each record contains:

- id: UUID used by Flutter favorites and local persistence;
- content_hash: SHA-256 of the image bytes;
- aliases: historical images/<category>/<filename> paths;
- retired: tombstone state for deleted records.

On the first hardened generation, existing page records are migrated by decoding their historical image URLs and hashing the corresponding local files. The migration preserved all 674 existing production IDs.

The content hash keeps an ID independent of repository, branch, URL encoding, category, and filename changes when the image bytes remain the same. Path aliases preserve an ID across a file rename. Exact duplicate image bytes are rejected by the generator, and retired records remain in metadata and are not reused for new images.

## 5. Pagination

- Total items: 669
- Total pages: 34
- Items per page: 20
- Final page size: 9
- Stale-page cleanup: passed; the output directory contains exactly page_1.json through page_34.json.

Each page exposes page, total_pages, total_items, items_per_page, has_next, has_prev, and data.

## 6. Categories

- Category count: 35
- Category counts sum to 669.
- Every category has a deterministic UUID `id` derived from its name.
- Every generated wallpaper category exists in categories.json.
- Every cover URL points to a wallpaper in its own category.
- All category URLs use the canonical Wallune owner, repository, and branch.

## 7. Search Index

api/v1/search_index.json contains 669 records and is 191,724 bytes.

Each record contains:

- id
- title
- category
- image_url
- size
- updated_at
- width
- height

The index is complete, has no orphan IDs, and matches canonical page data exactly. It contains metadata only and no image bytes.

## 8. Config API

api/v1/config.json currently contains:

~~~json
{
  "api_version": 1,
  "content_version": 3,
  "total_items": 669,
  "total_pages": 34,
  "items_per_page": 20,
  "generated_at": "2026-09-15T12:33:20Z",
  "catalog_hash": "e38e8cf3df3dcc26cfe6cdd16d0ea2ceb27988b5a74cb4b0fafb454887b66260"
}
~~~

api_version identifies the schema. catalog_hash fingerprints catalog semantics while ignoring filesystem mtime noise. content_version is kept when that hash is unchanged and incremented when the catalog changes. generated_at is always produced in real UTC.

## 9. URL Validation

All 669 wallpaper URLs and all 35 category cover URLs resolve structurally to:

https://raw.githubusercontent.com/OmarShawkey13/Wallune/main/

URL path segments are encoded per segment, including spaces and special characters. Local validation found no missing image mappings and no URL mismatches.

## 10. Tests

Command:

~~~bash
python -m unittest discover -s tests -v
~~~

Result: 12 tests passed.

Coverage includes:

- 0, 1, 20, and 21 images;
- multiple categories;
- duplicate filenames in different categories;
- duplicate-byte rejection;
- unsupported extensions;
- stale page cleanup;
- ID preservation across repository and branch URL changes;
- path rename preservation;
- deleted ID tombstones and new ID allocation;
- real UTC timestamps;
- URL encoding;
- search-index completeness;
- config version retention;
- invalid-page validation failure;
- invalid image-dimension failure.

Tests use temporary fixture directories and do not access the network.

## 11. Production Validation

The final generated catalog passed:

| Check | Result |
| --- | ---: |
| Local supported images | 669 |
| API records | 669 |
| Categories | 35 |
| Page files | 34 |
| Duplicate IDs | 0 |
| Duplicate URLs | 0 |
| Invalid dimensions | 0 |
| Non-positive sizes | 0 |
| Missing local files | 0 |
| Category count mismatches | 0 |
| Invalid category covers | 0 |
| Search orphans/missing records | 0 |
| Stale generated pages | 0 |
| Malformed JSON files | 0 |
| IDs preserved from previous API | 674 / 674 (669 active, 5 retired) |
| Remaining image binary modifications | none |

The generator completed successfully against the reviewed real catalog, and the independent validator plus the full test suite passed afterward.

## 12. Files Changed

Source and documentation:

- generate_api.py
- README.md
- .gitignore
- STATIC_BACKEND.md
- WALLUNE_STATIC_BACKEND_FINAL_REPORT.md
- tests/test_generate_api.py

Generated API:

- api/v1/config.json
- api/v1/categories.json
- api/v1/search_index.json
- api/v1/wallpaper_ids.json
- api/v1/models.dart
- api/v1/wallpapers/page_1.json through page_34.json

The 669 remaining image binaries were not modified. One visually reviewed tobacco image and four byte-identical duplicates were moved outside the repository to an external quarantine folder. Their former UUIDs remain as retired tombstones.

## 13. Remaining Limitations

GitHub Raw is public static delivery. It does not provide authentication, uploads, server-side filtering, rate limiting, or an application-level cache contract. Availability and response behavior depend on GitHub.

The Flutter client should handle non-200 responses, invalid JSON, and unavailable images as recoverable errors. It can cache config.json, search_index.json, and page data locally, using content_version to decide when to refresh.

Image licensing and redistribution rights must be reviewed before public release.

## 14. Flutter Migration Contract

Base URL:

~~~text
https://raw.githubusercontent.com/OmarShawkey13/Wallune/main/api/v1
~~~

Endpoints:

- /config.json
- /categories.json
- /search_index.json
- /wallpapers/page_N.json

Page semantics:

- page numbering starts at 1;
- items_per_page is 20;
- request the next page while has_next is true;
- stop when has_next is false;
- has_prev is true for pages after page 1;
- the final page may contain fewer than 20 records;
- when the catalog is empty, total_items and total_pages are 0 and no page file is generated.

Wallpaper schema:

~~~json
{
  "id": "uuid",
  "title": "Snowy Mountain Sunset",
  "category": "Nature",
  "image_url": "https://raw.githubusercontent.com/OmarShawkey13/Wallune/main/images/Nature/snowy_mountain_sunset.jpg",
  "size": 123456,
  "updated_at": "2026-09-15T10:30:45Z",
  "width": 864,
  "height": 1536
}
~~~

Search semantics:

- load /search_index.json once and cache it locally;
- filter by title and category on-device;
- use the indexed image_url, dimensions, and metadata to render a result immediately;
- match favorites by stable id.

Category semantics:

- each category has id, name, count, and cover;
- count equals the number of canonical page records for that category;
- cover is a valid image URL belonging to that category.

Config and caching:

- read content_version from /config.json;
- refresh cached catalog data when content_version changes;
- generated_at and every updated_at value are UTC ISO-8601 timestamps ending in Z;
- use width and height for predictable grid layout;
- use size and updated_at as optional cache metadata.

Error cases:

- treat HTTP status other than 200 as a request failure;
- treat malformed JSON or missing required fields as invalid API data;
- retry transient downloads and show a recoverable empty/error state;
- do not assume every image URL is available forever;
- do not depend on a monolithic wallpapers.json file or a server-side filter endpoint.
