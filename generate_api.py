import os
import uuid
import json
import urllib.parse
from pathlib import Path

# Configuration
IMAGE_DIR = 'images'
OUTPUT_JSON = 'wallpapers.json'

GITHUB_USERNAME = 'OmarShawkey13'
GITHUB_REPO_NAME = 'Wallune'
BRANCH = 'main'

VALID_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}

def get_clean_title(filename):
    """
    Extract a clean title from the original filename.
    e.g., 'beautiful_sunset.jpg' -> 'Beautiful Sunset'
    """
    name, _ = os.path.splitext(filename)
    name = name.replace('_', ' ').replace('-', ' ')
    return name.title()

def process_images():
    if not os.path.exists(IMAGE_DIR):
        print(f"Error: Directory '{IMAGE_DIR}' not found.")
        return
        
    categories_set = set()
    wallpapers = []
    
    existing_uuids = {}
    if os.path.exists(OUTPUT_JSON):
        try:
            with open(OUTPUT_JSON, 'r', encoding='utf-8') as f:
                data = json.load(f)
                for w in data.get('wallpapers', []):
                    existing_uuids[w.get('full_url')] = w.get('id')
        except Exception as e:
            print(f"Warning: Could not load existing JSON for UUIDs: {e}")
            
    for item in os.listdir(IMAGE_DIR):
        category_path = os.path.join(IMAGE_DIR, item)
        
        if os.path.isdir(category_path):
            category_name = item
            print(f"Processing category: {category_name}")
            categories_set.add(category_name)
            
            for file in os.listdir(category_path):
                file_ext = os.path.splitext(file)[1].lower()
                if file_ext not in VALID_EXTENSIONS:
                    continue
                    
                title = get_clean_title(file)
                
                cat_url = urllib.parse.quote(category_name)
                full_url_name = urllib.parse.quote(file)
                
                base_github_url = f"https://raw.githubusercontent.com/{GITHUB_USERNAME}/{GITHUB_REPO_NAME}/{BRANCH}/{IMAGE_DIR}"
                full_url = f"{base_github_url}/{cat_url}/{full_url_name}"
                
                wallpaper_id = existing_uuids.get(full_url, str(uuid.uuid4()))
                
                wallpapers.append({
                    "id": wallpaper_id,
                    "title": title,
                    "category": category_name,
                    "full_url": full_url
                })

    output_data = {
        "categories": sorted(list(categories_set)),
        "wallpapers": wallpapers
    }
    
    try:
        with open(OUTPUT_JSON, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        print(f"Successfully generated '{OUTPUT_JSON}' with {len(wallpapers)} wallpapers across {len(categories_set)} categories.")
    except Exception as e:
        print(f"Failed to write JSON: {e}")

if __name__ == "__main__":
    process_images()
