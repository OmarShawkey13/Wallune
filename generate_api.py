import os
import re
import uuid
import json
import urllib.parse
from pathlib import Path
from PIL import Image

# Configuration
IMAGE_DIR = 'images'
OUTPUT_JSON = 'wallpapers.json'

# Replace these or keep them as placeholders to replace in the final JSON
GITHUB_USERNAME = 'OmarShawkey13'
GITHUB_REPO_NAME = 'AuraDrop'
BRANCH = 'main'

THUMB_MAX_WIDTH = 400
THUMB_QUALITY = 60

VALID_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}

def clean_filename(filename):
    """
    Standardize image filenames: lowercase, replace spaces with underscores,
    remove special characters.
    """
    name, ext = os.path.splitext(filename)
    name = name.lower()
    name = name.replace(' ', '_')
    name = re.sub(r'[^a-z0-9_]', '', name)
    return f"{name}{ext.lower()}"

def get_clean_title(filename):
    """
    Extract a clean title from the original filename.
    e.g., 'beautiful_sunset_123.jpg' -> 'Beautiful Sunset 123'
    """
    name, _ = os.path.splitext(filename)
    # Replace underscores and hyphens with spaces
    name = name.replace('_', ' ').replace('-', ' ')
    # Capitalize words
    return name.title()

def process_images():
    if not os.path.exists(IMAGE_DIR):
        print(f"Error: Directory '{IMAGE_DIR}' not found.")
        print(f"Please create the '{IMAGE_DIR}' folder and add your category subdirectories with images inside them.")
        return
        
    categories_set = set()
    wallpapers = []
    
    # Iterate through subdirectories
    for item in os.listdir(IMAGE_DIR):
        category_path = os.path.join(IMAGE_DIR, item)
        
        if os.path.isdir(category_path):
            category_name = item
            print(f"Processing category: {category_name}")
            categories_set.add(category_name)
            
            for file in os.listdir(category_path):
                # Skip already processed files if script is re-run
                if any(file.endswith(f"_full{ext}") or file.endswith(f"_thumb{ext}") for ext in VALID_EXTENSIONS):
                    continue
                     
                file_ext = os.path.splitext(file)[1].lower()
                if file_ext not in VALID_EXTENSIONS:
                    print(f"  Skipping unsupported file or non-image: {file}")
                    continue
                    
                original_path = os.path.join(category_path, file)
                
                # 1. Clean and rename
                cleaned_name = clean_filename(file)
                base_name, ext = os.path.splitext(cleaned_name)
                
                # Generate new names
                full_name = f"{base_name}_full{ext}"
                thumb_name = f"{base_name}_thumb{ext}"
                
                full_path = os.path.join(category_path, full_name)
                thumb_path = os.path.join(category_path, thumb_name)
                
                print(f"  Processing image: {file} -> {full_name}")
                
                # Rename original to _full
                try:
                    os.rename(original_path, full_path)
                except Exception as e:
                    print(f"  Failed to rename {file}: {e}")
                    continue
                
                # 2. Generate thumbnail
                try:
                    with Image.open(full_path) as img:
                        # Convert to RGB if necessary to save as JPEG or avoid transparency issues
                        if img.mode in ("RGBA", "P"):
                            img = img.convert("RGB")
                            
                        # Resize maintaining aspect ratio
                        width_percent = (THUMB_MAX_WIDTH / float(img.size[0]))
                        height_size = int((float(img.size[1]) * float(width_percent)))
                        
                        # Only resize if original is wider than max width
                        if img.size[0] > THUMB_MAX_WIDTH:
                            thumb_img = img.resize((THUMB_MAX_WIDTH, height_size), Image.Resampling.LANCZOS)
                        else:
                            thumb_img = img.copy()
                            
                        # Save thumbnail
                        thumb_img.save(thumb_path, optimize=True, quality=THUMB_QUALITY)
                except Exception as e:
                    print(f"  Failed to process thumbnail for {full_name}: {e}")
                    # Revert renaming on failure
                    os.rename(full_path, original_path)
                    continue
                    
                # 3. Add to JSON structure
                wallpaper_id = str(uuid.uuid4())
                
                # Using the original filename base for the title is a nice touch
                original_base_name, _ = os.path.splitext(file)
                title = get_clean_title(original_base_name)
                
                # URL Encode parts to ensure valid URLs
                cat_url = urllib.parse.quote(category_name)
                full_url_name = urllib.parse.quote(full_name)
                thumb_url_name = urllib.parse.quote(thumb_name)
                
                base_github_url = f"https://raw.githubusercontent.com/{GITHUB_USERNAME}/{GITHUB_REPO_NAME}/{BRANCH}/{IMAGE_DIR}"
                
                wallpapers.append({
                    "id": wallpaper_id,
                    "title": title,
                    "category": category_name,
                    "thumbnail_url": f"{base_github_url}/{cat_url}/{thumb_url_name}",
                    "full_url": f"{base_github_url}/{cat_url}/{full_url_name}"
                })

    # 4. Generate JSON
    output_data = {
        "categories": sorted(list(categories_set)),
        "wallpapers": wallpapers
    }
    
    try:
        with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        print(f"\nSuccessfully generated '{OUTPUT_JSON}' with {len(wallpapers)} wallpapers across {len(categories_set)} categories.")
    except Exception as e:
        print(f"Failed to write JSON: {e}")

if __name__ == "__main__":
    process_images()
