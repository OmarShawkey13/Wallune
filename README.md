# Wallune Static Backend

This repository is the production content backend for the Wallune Flutter wallpaper application.

It is intentionally static:

~~~
Flutter application
       |
       +--> GitHub Raw JSON API
       |
       +--> GitHub Raw wallpaper images
~~~

There is no backend server, database, authentication layer, AWS dependency, or runtime API. GitHub serves the committed images and generated JSON files.

## Repository identity

- GitHub owner: OmarShawkey13
- Repository: Wallune
- Branch: main
- Raw base URL: https://raw.githubusercontent.com/OmarShawkey13/Wallune/main

The generator is configured with this identity in generate_api.py. Every generated image_url, category cover, and API URL must use the same owner, repository, and branch.

## Layout

~~~
images/
  Nature/
    snowy_mountain_sunset.jpg
  Cars/
    red_bmw_front.jpg

api/v1/
  config.json
  categories.json
  search_index.json
  wallpaper_ids.json
  models.dart
  wallpapers/
    page_1.json
    page_2.json
    ...

generate_api.py
tests/
  test_generate_api.py
~~~

Each direct folder under images is a category. Supported image extensions are .jpg, .jpeg, .png, and .webp.

## Static endpoints

Set this base URL in the Flutter client:

~~~
https://raw.githubusercontent.com/OmarShawkey13/Wallune/main/api/v1
~~~

| Endpoint | Purpose |
| --- | --- |
| /config.json | API version, content version, totals, and generation time |
| /categories.json | Category names, counts, and valid cover URLs |
| /search_index.json | Local search records with display metadata |
| /wallpapers/page_N.json | Paginated canonical wallpaper records |

A page has this shape:

~~~json
{
  "page": 1,
  "total_pages": 34,
  "total_items": 674,
  "items_per_page": 20,
  "has_next": true,
  "has_prev": false,
  "data": []
}
~~~

Each wallpaper in data contains id, title, category, image_url, size, updated_at, width, and height. The search index contains the same lightweight fields, so a search result can be displayed without fetching another page. The generated models.dart file also includes ApiConfig for config.json.

## Configuration and versions

config.json contains:

~~~json
{
  "api_version": 1,
  "content_version": 1,
  "total_items": 674,
  "total_pages": 34,
  "items_per_page": 20,
  "generated_at": "2026-09-15T10:30:45Z",
  "catalog_hash": "..."
}
~~~

api_version identifies the JSON schema. content_version is retained when the catalog semantics are unchanged and incremented when the catalog changes. catalog_hash is the deterministic catalog fingerprint used to make that decision. generated_at is always a real UTC timestamp.

## Stable IDs

The generated wallpaper IDs are persisted in api/v1/wallpaper_ids.json. A record stores:

- a UUID
- a SHA-256 hash of the image bytes
- historical relative-path aliases
- a retired flag

On the first hardened generation, existing page files are migrated into this metadata file so current Flutter favorites keep their IDs. The image content hash is independent of the GitHub repository, branch, URL encoding, category, and filename. Path aliases and deterministic duplicate matching distinguish equal image bytes in different categories.

Retired records remain as tombstones and are never assigned to a newly introduced image. A new image receives a new UUID. Do not delete wallpaper_ids.json.

## Generate and validate

Use Python 3 from the repository root:

~~~bash
python generate_api.py
~~~

Windows users can also use:

~~~bash
py generate_api.py
~~~

Generation:

1. reads supported files under images;
2. extracts positive dimensions and file sizes;
3. assigns or preserves stable IDs;
4. sorts records by category, title, and URL;
5. writes exactly the required page_*.json files;
6. writes categories, search index, ID metadata, config, and models.dart;
7. validates all cross-file invariants before and after writing.

Only files named page_<number>.json are removed during stale-page cleanup. Unrelated files in api/v1/wallpapers are left alone. If there are no images, total_pages is zero and no page files are generated.

## Adding or removing wallpapers

1. Put the image in an existing category folder or create a new direct child of images.
2. Keep the extension supported and the filename URL-safe after encoding.
3. Run the generator.
4. Run the test suite.
5. Review the generated diff and commit images, api/v1, generate_api.py, tests, and documentation.

The generator does not recompress, resize, rename, or move image binaries. A filename or category rename keeps the UUID when the image bytes remain the same. Changing the image bytes creates a new identity.

## Validation and tests

The validator checks counts, page continuity, page flags, UUID format and uniqueness, canonical Wallune URLs, URL encoding, local-image coverage, dimensions, sizes, categories and covers, search-index completeness, config totals, and UTC timestamps.

Run:

~~~bash
python -m unittest discover -s tests -v
~~~

Tests use temporary fixture directories and do not require network access. They cover empty catalogs, 1/20/21 item pagination, multiple categories, duplicate filenames, unsupported extensions, stale cleanup, ID preservation across URL changes, new and deleted images, UTC timestamps, URL encoding, search completeness, category counts, config totals, and final-page metadata.

## Generated files to commit

- images/
- api/v1/config.json
- api/v1/categories.json
- api/v1/search_index.json
- api/v1/wallpaper_ids.json
- api/v1/models.dart
- api/v1/wallpapers/page_*.json
- generate_api.py
- tests/
- documentation

Do not add a monolithic wallpapers.json file. Do not add Firebase, Supabase, AWS, Node.js, PHP, Django, Flask, or another server runtime.

## Current catalog snapshot

The current catalog contains 674 supported images in 35 categories, generated into 34 pages with 20 items per page (14 on the final page). The image binaries are about 108 MiB. These are generated values, not hardcoded limits.

## Operational limitations

GitHub Raw provides public, static delivery. It does not provide authentication, server-side filtering, uploads, rate limiting, or guaranteed application-level caching. The Flutter client should cache config and search_index locally, use content_version to decide when to refresh catalog data, and treat non-200 responses and malformed JSON as recoverable API errors.

Review image licensing before publishing the repository.
