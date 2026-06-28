# AuraDrop Static API Generator

This script generates a static JSON-based backend for the AuraDrop wallpaper application hosted entirely on GitHub. It traverses subdirectories inside the `images` folder (which act as categories), extracts human-readable titles from the filenames, and creates a `wallpapers.json` API file linking to the Raw GitHub URLs.

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
   The script is pre-configured with your GitHub details (`OmarShawkey13/AuraDrop`, branch `main`). If you ever change your username or repository name, update the constants at the top of `generate_api.py`.

3. **Run the Script**:
   Run the Python script from your terminal:
   ```bash
   py generate_api.py
   ```

4. **Check Output**:
   - The script will read all supported image formats (`.jpg`, `.jpeg`, `.png`, `.webp`).
   - It cleans up the filename (e.g., `snowy_mountain_sunset.jpg` becomes `Snowy Mountain Sunset`) to act as the title.
   - A `wallpapers.json` file is created in the root directory containing all wallpapers, categorized, with unique UUIDs and direct links to the raw images on GitHub.

5. **Host on GitHub**:
   Commit and push your changes (the `images` folder and the updated `wallpapers.json`) to your GitHub repository. Your front-end app can immediately fetch `wallpapers.json` via its Raw URL.
