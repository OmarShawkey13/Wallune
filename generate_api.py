import os
import uuid
import json
import urllib.parse
from datetime import datetime
from typing import Dict, List, Any

# --- Configuration ---
IMAGE_DIR = 'images'
API_DIR = 'api/v1'
WALLPAPERS_JSON = 'wallpapers.json'
CATEGORIES_JSON = 'categories.json'

GITHUB_USERNAME = 'OmarShawkey13'
GITHUB_REPO_NAME = 'Wallune'
BRANCH = 'main'

VALID_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp'}
ITEMS_PER_PAGE = 20

def get_clean_title(filename: str) -> str:
    """Extract a clean title from the original filename."""
    name, _ = os.path.splitext(filename)
    name = name.replace('_', ' ').replace('-', ' ')
    return name.title()

def load_existing_uuids(json_path: str) -> Dict[str, str]:
    """Load existing UUIDs to maintain consistent IDs across generations."""
    existing_uuids = {}
    if os.path.exists(json_path):
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                wallpapers_list = data.get('wallpapers', []) if isinstance(data, dict) else data
                for w in wallpapers_list:
                    if 'image_url' in w and 'id' in w:
                        existing_uuids[w['image_url']] = w['id']
        except Exception as e:
            print(f"Warning: Could not load existing JSON for UUIDs: {e}")
    return existing_uuids

def generate_paginated_api(wallpapers: List[Dict[str, Any]], api_dir: str):
    """Generate paginated JSON files for efficient Flutter app consumption."""
    os.makedirs(os.path.join(api_dir, 'wallpapers'), exist_ok=True)
    
    total_items = len(wallpapers)
    total_pages = (total_items + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
    
    for page in range(1, total_pages + 1):
        start_idx = (page - 1) * ITEMS_PER_PAGE
        end_idx = start_idx + ITEMS_PER_PAGE
        page_items = wallpapers[start_idx:end_idx]
        
        page_data = {
            "page": page,
            "total_pages": total_pages,
            "total_items": total_items,
            "items_per_page": ITEMS_PER_PAGE,
            "has_next": page < total_pages,
            "has_prev": page > 1,
            "data": page_items
        }
        
        page_path = os.path.join(api_dir, 'wallpapers', f'page_{page}.json')
        with open(page_path, 'w', encoding='utf-8') as f:
            json.dump(page_data, f, indent=2, ensure_ascii=False)
            
    print(f"Generated {total_pages} paginated wallpaper files in '{api_dir}/wallpapers/'.")

def generate_search_index(wallpapers: List[Dict[str, Any]], api_dir: str):
    """Generate a lightweight search index with essential fields."""
    search_index = [
        {
            "id": w["id"],
            "title": w["title"],
            "category": w["category"]
        }
        for w in wallpapers
    ]
    
    index_path = os.path.join(api_dir, 'search_index.json')
    with open(index_path, 'w', encoding='utf-8') as f:
        # Minified output for faster downloading
        json.dump(search_index, f, separators=(',', ':'), ensure_ascii=False)
        
    print(f"Generated lightweight search index at '{index_path}'.")

def process_images():
    if not os.path.exists(IMAGE_DIR):
        print(f"Error: Directory '{IMAGE_DIR}' not found.")
        return
        
    categories_info = {}
    wallpapers = []
    
    existing_uuids = load_existing_uuids(WALLPAPERS_JSON)
            
    for item in os.listdir(IMAGE_DIR):
        category_path = os.path.join(IMAGE_DIR, item)
        
        if os.path.isdir(category_path):
            category_name = item
            print(f"Processing category: {category_name}")
            categories_info[category_name] = {"count": 0, "cover": None}
            
            for file in os.listdir(category_path):
                file_ext = os.path.splitext(file)[1].lower()
                if file_ext not in VALID_EXTENSIONS:
                    continue
                    
                categories_info[category_name]["count"] += 1
                title = get_clean_title(file)
                
                cat_url = urllib.parse.quote(category_name)
                full_url_name = urllib.parse.quote(file)
                
                base_github_url = f"https://raw.githubusercontent.com/{GITHUB_USERNAME}/{GITHUB_REPO_NAME}/{BRANCH}/{IMAGE_DIR}"
                full_url = f"{base_github_url}/{cat_url}/{full_url_name}"
                
                if categories_info[category_name]["cover"] is None:
                    categories_info[category_name]["cover"] = full_url
                
                wallpaper_id = existing_uuids.get(full_url, str(uuid.uuid4()))
                
                file_path = os.path.join(category_path, file)
                file_size = os.path.getsize(file_path)
                
                file_stat = os.stat(file_path)
                updated_at = datetime.fromtimestamp(file_stat.st_mtime).isoformat() + "Z"
                
                wallpapers.append({
                    "id": wallpaper_id,
                    "title": title,
                    "category": category_name,
                    "image_url": full_url,
                    "size": file_size,
                    "updated_at": updated_at
                })

    # Sort wallpapers by category then title to ensure determinism
    wallpapers.sort(key=lambda x: (x['category'], x['title']))

    final_categories = [
        {"name": k, "count": info["count"], "cover": info["cover"]} 
        for k, info in sorted(categories_info.items()) if info["count"] > 0
    ]

    # Write root JSON files (legacy/monolithic)
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

    # Write modern API structure
    os.makedirs(API_DIR, exist_ok=True)
    generate_paginated_api(wallpapers, API_DIR)
    generate_search_index(wallpapers, API_DIR)
    
    with open(os.path.join(API_DIR, 'categories.json'), 'w', encoding='utf-8') as f:
        json.dump(final_categories, f, indent=2, ensure_ascii=False)
        
    print(f"API generation complete. V1 API is available in '{API_DIR}'.")

if __name__ == "__main__":
    process_images()
