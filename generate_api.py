import os
import uuid
import json
import urllib.parse
from pathlib import Path

# Configuration
IMAGE_DIR = 'images'
WALLPAPERS_JSON = 'wallpapers.json'
CATEGORIES_JSON = 'categories.json'

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
        
    category_counts = {}
    wallpapers = []
    
    existing_uuids = {}
    if os.path.exists(WALLPAPERS_JSON):
        try:
            with open(WALLPAPERS_JSON, 'r', encoding='utf-8') as f:
                data = json.load(f)
                wallpapers_list = data.get('wallpapers', []) if isinstance(data, dict) else data
                for w in wallpapers_list:
                    existing_uuids[w.get('full_url')] = w.get('id')
        except Exception as e:
            print(f"Warning: Could not load existing JSON for UUIDs: {e}")
            
    for item in os.listdir(IMAGE_DIR):
        category_path = os.path.join(IMAGE_DIR, item)
        
        if os.path.isdir(category_path):
            category_name = item
            print(f"Processing category: {category_name}")
            category_counts[category_name] = 0
            
            for file in os.listdir(category_path):
                file_ext = os.path.splitext(file)[1].lower()
                if file_ext not in VALID_EXTENSIONS:
                    continue
                    
                category_counts[category_name] += 1
                    
                title = get_clean_title(file)
                
                cat_url = urllib.parse.quote(category_name)
                full_url_name = urllib.parse.quote(file)
                
                base_github_url = f"https://raw.githubusercontent.com/{GITHUB_USERNAME}/{GITHUB_REPO_NAME}/{BRANCH}/{IMAGE_DIR}"
                full_url = f"{base_github_url}/{cat_url}/{full_url_name}"
                
                wallpaper_id = existing_uuids.get(full_url, str(uuid.uuid4()))
                
                file_path = os.path.join(category_path, file)
                file_size = os.path.getsize(file_path)
                
                wallpapers.append({
                    "id": wallpaper_id,
                    "title": title,
                    "category": category_name,
                    "image_url": full_url,
                    "size": file_size
                })

    final_categories = [{"name": k, "count": v} for k, v in sorted(category_counts.items()) if v > 0]

    try:
        with open(WALLPAPERS_JSON, 'w', encoding='utf-8') as f:
            json.dump(wallpapers, f, indent=2, ensure_ascii=False)
        print(f"Successfully generated '{WALLPAPERS_JSON}' with {len(wallpapers)} wallpapers.")
    except Exception as e:
        print(f"Failed to write wallpapers JSON: {e}")

    try:
        with open(CATEGORIES_JSON, 'w', encoding='utf-8') as f:
            json.dump(final_categories, f, indent=2, ensure_ascii=False)
        print(f"Successfully generated '{CATEGORIES_JSON}' with {len(final_categories)} categories.")
    except Exception as e:
        print(f"Failed to write categories JSON: {e}")

if __name__ == "__main__":
    process_images()
