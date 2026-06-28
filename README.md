# Wallpaper App Backend Automation

This script generates a static JSON-based backend for a wallpaper application hosted on GitHub. It traverses subdirectories inside the `images` folder (which act as categories), processes the images, and creates a `wallpapers.json` API file.

## Prerequisites

1.  **Python 3**: Ensure you have Python installed.
2.  **Install Requirements**:
    Install the required dependencies (mainly Pillow for image processing):
    ```bash
    pip install -r requirements.txt
    ```

## Setup & Usage

1.  **Create your Image Directories**:
    In the same directory as the script, create an `images` folder. Inside `images`, create subfolders for each category. Put your high-resolution wallpapers in these subfolders.
    
    ```
    D:\wallpaper_backend\
    ├── images/
    │   ├── Nature/
    │   │   ├── mountain.jpg
    │   │   └── beautiful sunset.png
    │   ├── Cars/
    │   │   ├── sportscar.jpg
    │   └── Abstract/
    │       └── shapes.webp
    ├── generate_api.py
    └── requirements.txt
    ```

2.  **Verify Configuration**:
    The script is already pre-configured with your GitHub details (`OmarShawkey13/AuraDrop`).
    *(Optional)* You can open `generate_api.py` to adjust `THUMB_MAX_WIDTH` and `THUMB_QUALITY`.

3.  **Run the Script**:
    Run the Python script from your terminal:
    ```bash
    python generate_api.py
    ```

4.  **Check Output**:
    *   Your original images will be renamed to include `_full` (e.g., `mountain_full.jpg`).
    *   Compressed thumbnails will be generated alongside them (e.g., `mountain_thumb.jpg`).
    *   A `wallpapers.json` file will be created in the root directory.

5.  **Host on GitHub**:
    Commit and push all these files (the `images` folder with processed images, and `wallpapers.json`) to your GitHub repository. Your app can now fetch `wallpapers.json` directly from GitHub via the Raw URL.
