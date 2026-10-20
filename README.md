# Wallune Static Backend

This repository is the production content backend for the Wallune Flutter wallpaper app. It is deliberately static: GitHub serves the committed images and generated JSON files, while the Flutter app reads them through GitHub Raw URLs.

There is no server process, database, authentication layer, upload endpoint, or runtime dependency.

## Production API

```text
https://raw.githubusercontent.com/OmarShawkey13/Wallune/main/api/v1
```

| Endpoint | Purpose |
| --- | --- |
| `config.json` | API version, catalog version, totals, and catalog hash |
| `categories.json` | Category IDs, names, counts, and cover URLs |
| `search_index.json` | Lightweight records for local search |
| `wallpapers/page_N.json` | Canonical paginated wallpaper records |

Every wallpaper record contains a stable `id`, a display `title`, its `category`, a canonical `image_url`, the byte `size`, `updated_at`, and the original `width` and `height`.

Each category contains a deterministic UUID `id`. The ID is derived from the category name, so it remains stable across normal regenerations. `wallpaper_ids.json` is the identity ledger for wallpapers; retired records are kept as tombstones so an old ID is never reused for a different image.

## Repository layout

```text
images/                         Production image catalog
  <Category>/<descriptive_name>.jpg
api/v1/                         Generated static API
  config.json
  categories.json
  search_index.json
  wallpaper_ids.json
  wallpapers/page_*.json
generate_api.py                 Generator and validator
tests/test_generate_api.py      Regression tests
STATIC_BACKEND.md               Arabic technical guide
WALLUNE_STATIC_BACKEND_FINAL_REPORT.md  Current audit report
```

`new_wall/` is an ignored local staging folder for incoming images. Review a batch there first, then move only approved images into a category under `images/`. It is intentionally not part of the production catalog.

## Updating the catalog

Use lowercase `snake_case` filenames and an existing category unless a new category is genuinely needed.

1. Review the incoming batch in `new_wall/` for policy, quality, and duplicate content.
2. Move approved images into `images/<Category>/`.
3. Generate and validate the API from the repository root:

   ```bash
   python generate_api.py
   ```

   On Windows, `py -3 generate_api.py` is equivalent.

4. Run the regression suite:

   ```bash
   python -m unittest discover -s tests -v
   ```

5. Run the read-only validator before committing:

   ```bash
   python generate_api.py --validate-only
   ```

The generator reads supported images, checks their dimensions and SHA-256 hashes, preserves stable IDs, creates the JSON files in a staging directory, validates the staged catalog, then replaces the generated output with rollback on failure. It removes only stale files matching `wallpapers/page_<number>.json`; unrelated files under `api/v1/wallpapers/` are left untouched.

## Current catalog snapshot

The committed catalog currently contains:

| Metric | Value |
| --- | ---: |
| Supported images | 453 |
| Categories | 17 |
| API pages | 23 |
| Items per page | 20 |
| Final page | 13 items |
| Image bytes | 61,850,981 (about 59 MiB) |
| Active wallpaper IDs | 453 |
| Retired ID tombstones | 627 |

The generated API was validated against every local image. It has no duplicate SHA-256 image bytes, no duplicate active IDs, no missing page records, and no broken local image mappings.

## Scope and limitations

GitHub Raw is public static hosting. It does not provide authentication, uploads, server-side filtering, rate limiting, or guaranteed application-level caching. The Flutter client should cache `config.json`, `search_index.json`, and page responses, refresh when `content_version` changes, and handle non-200 responses or malformed JSON as recoverable errors.

Review image licensing before publishing new content.
