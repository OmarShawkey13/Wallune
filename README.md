# Wallune Static Backend

This repository is the production content backend for the Wallune Flutter wallpaper app. It is deliberately static: GitHub serves the committed images and generated JSON files, while the Flutter app reads them through GitHub Raw URLs.

There is no server process, database, authentication layer, or upload endpoint. The generator uses Pillow at build time to produce lightweight WebP thumbnails; install it with `python -m pip install -r requirements.txt`.

## Production API

```text
https://raw.githubusercontent.com/OmarShawkey13/Wallune/main/api/v1
```

| Endpoint | Purpose |
| --- | --- |
| `config.json` | API and data-schema versions, totals, and catalog hash |
| `categories.json` | Category IDs, names, counts, and cover URLs |
| `search_index.json` | Records for local search |
| `wallpapers/page_N.json` | Canonical paginated wallpaper records |

Every wallpaper record contains a stable `id`, a display `title`, its `category`, a canonical full-size `image_url`, a lightweight `thumbnail_url`, the byte `size`, `updated_at`, and the original `width` and `height`. Use `thumbnail_url` in wallpaper grids and `cover_thumbnail_url` for category covers; load `image_url` on the detail or download screen.

`search_index.json` uses compact `search_schema_version: 3` records with `id`, `title`, `category`, `image_url`, `thumbnail_url`, `width`, and `height`. The URL fields match the names and values in paginated wallpaper records. File size and timestamp remain available in those records. The current 1,269-record index is 487,306 bytes; linear growth projects to about 3.84 MB at 10,000 records.

Each category contains a deterministic UUID `id` derived from its name. Each wallpaper ID is deterministically derived from the image's SHA-256 content hash, so it remains stable when the file is renamed or moved. The `wallpaper_id_version` config value identifies this ID scheme; the generator keeps no separate wallpaper ID ledger.

## Repository layout

```text
images/                         Production image catalog
  <Category>/<descriptive_name>.jpg
api/v1/                         Generated static API
  config.json
  categories.json
  search_index.json
  thumbnails/                   Generated WebP previews, keyed by wallpaper ID
  wallpapers/page_*.json
generate_api.py                 Generator and validator
tests/test_generate_api.py      Regression tests
requirements.txt                Build-time image library
STATIC_BACKEND.md               Arabic technical guide
WALLUNE_STATIC_BACKEND_FINAL_REPORT.md  Current audit report
```

`new_wall/` is an ignored local staging folder for incoming images. Review a batch there first, then move only approved images into a category under `images/`. It is intentionally not part of the production catalog.

## Updating the catalog

Use lowercase `snake_case` filenames and an existing category unless a new category is genuinely needed.

1. Review the incoming batch in `new_wall/` for policy, quality, and duplicate content.
2. Move approved images into `images/<Category>/`.
3. Install the generator dependency once:

   ```bash
   python -m pip install -r requirements.txt
   ```

4. Generate and validate the API from the repository root:

   ```bash
   python generate_api.py
   ```

   On Windows, `py -3 generate_api.py` is equivalent.

5. Run the regression suite:

   ```bash
   python -m unittest discover -s tests -v
   ```

6. Run the read-only validator before committing:

   ```bash
   python generate_api.py --validate-only
   ```

The generator reads supported images, checks their dimensions and SHA-256 hashes, preserves stable IDs, and writes JSON plus WebP thumbnails in a staging directory. It reuses valid thumbnails for existing wallpaper IDs, creates only missing or invalid thumbnails, then replaces the generated output and validates it with rollback on failure. It removes stale generated page and thumbnail files while preserving unrelated files.

## Current catalog snapshot

The current generated catalog contains:

| Metric | Value |
| --- | ---: |
| Supported images | 1,269 |
| Categories | 17 |
| API pages | 64 |
| Items per page | 20 |
| Final page | 9 items |
| Original image bytes | 198,872,143 (about 189.7 MiB) |
| Generated thumbnails | 1,269 (50,176,100 bytes, about 47.9 MiB) |
| Active wallpaper IDs | 1,269 |

The generated API is validated against every local image and thumbnail. It has no duplicate SHA-256 image bytes, no duplicate active IDs, no missing page or thumbnail files, and no broken local image mappings.

## Scope and limitations

GitHub Raw is public static hosting. It does not provide authentication, uploads, server-side filtering, rate limiting, or guaranteed application-level caching. The Flutter client should cache `config.json`, `search_index.json`, page responses, and downloaded thumbnails; refresh catalog data only when `content_version` changes; and handle non-200 responses or malformed JSON as recoverable errors.

Review image licensing before publishing new content.
