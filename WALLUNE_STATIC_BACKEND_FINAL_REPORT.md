# Wallune Static Backend — Current Audit

**Audit date:** 2026-10-24
**Repository:** `OmarShawkey13/Wallune`
**Production API:** `api/v1`

## Catalog

| Check | Result |
| --- | ---: |
| Supported images | 1,168 |
| Categories | 17 |
| API records | 1,168 |
| API pages | 59 |
| Items per page | 20 |
| Final page | 8 items |
| Original image bytes | 184,014,885 (about 175 MiB) |
| Generated WebP thumbnails | 1,168 |
| Thumbnail bytes | 45,718,242 (about 43.6 MiB) |
| Compact search index | 307,597 bytes (about 300 KiB) |
| Projected search index at 10,000 images | about 2.63 MB, using current average record size |
| Search schema version | 2 |
| Active IDs | 1,168 |

The first page's 20 original images total 3,368,627 bytes. Their WebP thumbnails total 575,792 bytes, an 82.9% reduction for that preview batch.

## Comparison with the original tracked API

The baseline is the repository's `HEAD` snapshot before this cleanup. JSON sizes include all API JSON files; thumbnail assets are reported separately.

| Metric | Original | Current | Change |
| --- | ---: | ---: | ---: |
| Search index | 335,366 bytes | 307,597 bytes | down 27,769 bytes (8.3%) |
| All API JSON | 1,307,601 bytes | 925,247 bytes | down 382,354 bytes (29.2%) |
| `wallpaper_ids.json` | 538,255 bytes | removed | removed from generation and output |
| WebP thumbnails | not present | 45,718,242 bytes | 1,168 generated previews added |

The JSON catalog is smaller overall. The thumbnail files add about 43.6 MiB to repository storage; gallery network traffic benefits when the Flutter client loads `thumbnail_url` instead of each full-size `image_url`. The current search index projects to about 2.63 MB at 10,000 images, compared with about 2.87 MB using the original index's average record size.

## API integrity

`generate_api.py --validate-only` passed for `api/v1`. Validation confirmed:

- every local image has one generated record and one thumbnail;
- each record's ID, dimensions, byte size, updated timestamp, and SHA-256 identity match its source;
- thumbnail files are valid WebP dimensions no larger than 480 × 854;
- category IDs, counts, covers, search records, page metadata, and config totals agree;
- page files are continuous from `page_1.json` through `page_59.json`;
- no duplicate active IDs or image URLs exist.

The temporary `api/v2` output directory was removed after the earlier migration check. Production remains on `api/v1`. Wallpaper IDs now come deterministically from image content hashes, so the generator no longer keeps a separate ID ledger. The compact search index contains `id`, `title`, `category`, relative `image_path` and `thumbnail_path`, `width`, and `height`; full image URLs and metadata remain in paginated records. The Flutter client should resolve search paths from a slash-terminated API base URI.

The build completed with 1,168 records, 59 pages, and 17 categories. The regression suite passed all 28 tests, including temporary v2 generation, incremental thumbnail reuse, invalid-thumbnail regeneration, content-derived IDs, migration timestamp handling when source bytes change but the thumbnail does not, pagination, rollback, and read-only validation. `--validate-only` also passed for the production `api/v1` output. Normal generation reuses valid thumbnails for unchanged wallpaper IDs and generates only missing or invalid files.

## Workflow

Install the image-generation dependency with `python -m pip install -r requirements.txt`. Then generate the API, run `python -m unittest discover -s tests -v`, and finish with `python generate_api.py --validate-only` before committing images and generated files together.
