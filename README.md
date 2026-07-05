# Wallune Static API Generator

This script generates a static JSON-based backend for the Wallune wallpaper application, hosted entirely on GitHub. It traverses subdirectories inside the `images` folder (which act as categories), extracts human-readable titles from the filenames, and creates a highly-optimized set of API files designed specifically for a Flutter app to consume efficiently.

## Features

- **Paginated API**: Automatically chunks wallpapers into `page_X.json` files for fast, efficient fetching and infinite scrolling in Flutter.
- **Search Index**: Generates a lightweight, minified `search_index.json` to allow rapid client-side search filtering.
- **Metadata Generation**: Calculates file sizes and `updated_at` timestamps for precise app caching logic.
- **Persistent UUIDs**: Matches URLs with previous API builds to ensure image IDs never change, keeping user favorites intact.
- **Categorization**: Outputs category overviews with cover images and item counts.

## Prerequisites

- **Python 3**: Ensure you have Python installed (`python` or `py`). 
- **No external dependencies**: The script only uses standard Python libraries (`os`, `uuid`, `json`, `urllib`).

## Setup & Usage

1. **Create your Image Directories**:
   In the same directory as the script, ensure there is an `images` folder. Inside `images`, subfolders dictate the categories. Place your wallpapers in these subfolders.
   
   ```text
   D:\wallpaper_backend\
   ├── images/
   │   ├── Nature/
   │   │   ├── snowy_mountain_sunset.jpg
   │   │   └── autumn_forest.png
   │   ├── Cars/
   │   │   ├── red_sportscar.jpg
   │   └── Abstract/
   │       └── glass_chain.webp
   └── generate_api.py
   ```

2. **Verify Configuration**:
   The script is pre-configured with your GitHub details (`OmarShawkey13/Wallune`, branch `main`). If you ever change your username or repository name, update the constants at the top of `generate_api.py`.

3. **Run the Script**:
   Run the Python script from your terminal:
   ```bash
   py generate_api.py
   ```

4. **Check Output**:
   - The script cleans up filenames to use as titles.
   - Outputs the traditional monolithic JSON files (`wallpapers.json`, `categories.json`).
   - Generates the optimized V1 API folder:
     ```text
     api/v1/
     ├── search_index.json
     ├── categories.json
     └── wallpapers/
         ├── page_1.json
         ├── page_2.json
         └── ...
     ```

5. **Consume in Flutter**:
   You can fetch these directly from GitHub using the Raw URL format.
   For example, to fetch page 1:
   ```dart
   final response = await http.get(Uri.parse('https://raw.githubusercontent.com/OmarShawkey13/Wallune/main/api/v1/wallpapers/page_1.json'));
   ```

6. **Host on GitHub**:
   Commit and push your changes (the `images` folder, `api` folder, and monolithic JSONs) to your GitHub repository. Your Flutter app can immediately utilize the latest APIs via their Raw URLs.
