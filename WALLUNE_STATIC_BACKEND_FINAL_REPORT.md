# Wallune Static Backend — Current Audit

**Audit date:** 2026-10-24
**Repository:** `OmarShawkey13/Wallune`
**Production API:** `api/v1`

## Catalog

| Check | Result |
| --- | ---: |
| Supported images | 1,269 |
| Categories | 17 |
| API records | 1,269 |
| API pages | 64 |
| Items per page | 20 |
| Final page | 9 items |
| Original image bytes | 198,872,143 (about 189.7 MiB) |
| Generated WebP thumbnails | 1,269 |
| Thumbnail bytes | 50,176,100 (about 47.9 MiB) |
| Compact search index | 487,306 bytes (about 476 KiB) |
| Projected search index at 10,000 images | about 3.84 MB, using current average record size |
| Search schema version | 3 |
| Active IDs | 1,269 |

The first page's 20 original images total 2,612,952 bytes. Their WebP thumbnails total 504,516 bytes, an 80.7% reduction for that preview batch.

## Comparison with schema 2

This comparison uses the same current catalog of 1,269 images and rebuilds its search index with the previous relative-path schema to isolate the effect of full URLs.

| Metric | Schema 2 with relative paths | Schema 3 with full URLs | Change |
| --- | ---: | ---: | ---: |
| Search index | 333,756 bytes | 487,306 bytes | up 153,550 bytes (46.0%) |
| All API JSON | 1,003,792 bytes | 1,157,342 bytes | up 153,550 bytes (15.3%) |
| Projected index at 10,000 images | 2.63 MB | 3.84 MB | remains below 5 MB |

The full-URL fields make the search index larger, while matching the wallpaper record names and values directly. The search index remains projected below 5 MB at 10,000 images. The 101 images added since the previous build are included in the current catalog, bringing it from 1,168 to 1,269 records.

## API integrity

`generate_api.py --validate-only` passed for `api/v1`. Validation confirmed:

- every local image has one generated record and one thumbnail;
- each record's ID, dimensions, byte size, updated timestamp, and SHA-256 identity match its source;
- thumbnail files are valid WebP dimensions no larger than 480 × 854;
- category IDs, counts, covers, search records, page metadata, and config totals agree;
- page files are continuous from `page_1.json` through `page_64.json`;
- no duplicate active IDs or image URLs exist.

The temporary `api/v2` output directory was removed after the earlier migration check. Production remains on `api/v1`. Wallpaper IDs now come deterministically from image content hashes, so the generator no longer keeps a separate ID ledger. Search schema 3 contains `id`, `title`, `category`, `image_url`, `thumbnail_url`, `width`, and `height`; the URL names and values match the wallpaper records. File size and timestamp remain in paginated records.

The build completed with 1,269 records, 64 pages, and 17 categories. The regression suite passed all 28 tests, including temporary v2 generation, incremental thumbnail reuse, invalid-thumbnail regeneration, content-derived IDs, migration timestamp handling when source bytes change but the thumbnail does not, pagination, rollback, and read-only validation. `--validate-only` also passed for the production `api/v1` output. Normal generation reuses valid thumbnails for unchanged wallpaper IDs and generates only missing or invalid files.

## Workflow

Install the image-generation dependency with `python -m pip install -r requirements.txt`. Then generate the API, run `python -m unittest discover -s tests -v`, and finish with `python generate_api.py --validate-only` before committing images and generated files together.
