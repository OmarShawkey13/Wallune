import os
import uuid
import json
import struct
import urllib.parse
from datetime import datetime
from typing import Dict, List, Any, Optional, Tuple

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

def get_image_size(fname: str) -> Optional[Tuple[int, int]]:
    """
    Determine the image type and return its (width, height).
    Works for PNG, GIF, JPEG, and WebP without external libraries.
    """
    try:
        with open(fname, 'rb') as fhandle:
            head = fhandle.read(24)
            if len(head) != 24:
                return None
            
            # Check for PNG
            if head.startswith(b'\x89PNG\r\n\x1a\n'):
                width, height = struct.unpack('>ii', head[16:24])
                return width, height
                
            # Check for GIF
            elif head.startswith(b'GIF87a') or head.startswith(b'GIF89a'):
                width, height = struct.unpack('<HH', head[6:10])
                return width, height
                
            # Check for WebP
            elif head.startswith(b'RIFF') and head[8:12] == b'WEBP':
                chunk_header = head[12:16]
                if chunk_header == b'VP8 ':
                    fhandle.seek(26)
                    data = fhandle.read(4)
                    if len(data) == 4:
                        width, height = struct.unpack('<HH', data)
                        return width & 0x3fff, height & 0x3fff
                elif chunk_header == b'VP8L':
                    fhandle.seek(21)
                    data = fhandle.read(4)
                    if len(data) == 4:
                        b1, b2, b3, b4 = data
                        width = 1 + (((b2 & 0x3F) << 8) | b1)
                        height = 1 + (((b4 & 0xF) << 10) | (b3 << 2) | ((b2 & 0xC0) >> 6))
                        return width, height
                elif chunk_header == b'VP8X':
                    fhandle.seek(24)
                    data = fhandle.read(6)
                    if len(data) == 6:
                        b1, b2, b3, b4, b5, b6 = data
                        width = 1 + (b1 | (b2 << 8) | (b3 << 16))
                        height = 1 + (b4 | (b5 << 8) | (b6 << 16))
                        return width, height
                        
            # Check for JPEG
            elif head.startswith(b'\xff\xd8'):
                fhandle.seek(2)
                b = fhandle.read(1)
                try:
                    while b and ord(b) != 0xDA:
                        while ord(b) != 0xFF: 
                            b = fhandle.read(1)
                        while ord(b) == 0xFF: 
                            b = fhandle.read(1)
                        if 0xC0 <= ord(b) <= 0xC3:
                            fhandle.seek(3, 1)
                            h, w = struct.unpack('>HH', fhandle.read(4))
                            return w, h
                        else:
                            fhandle.seek(struct.unpack('>H', fhandle.read(2))[0] - 2, 1)
                        b = fhandle.read(1)
                except struct.error:
                    pass
    except Exception as e:
        print(f"Error reading image dimensions for {fname}: {e}")
        pass
        
    return None

def get_clean_title(filename: str) -> str:
    """Extract a clean title from the original filename."""
    name, _ = os.path.splitext(filename)
    name = name.replace('_', ' ').replace('-', ' ')
    return name.title()

import glob

def load_existing_uuids(api_dir: str) -> Dict[str, str]:
    """Load existing UUIDs to maintain consistent IDs across generations."""
    existing_uuids = {}
    
    # 1. Load from the new paginated API
    wallpapers_dir = os.path.join(api_dir, 'wallpapers')
    if os.path.exists(wallpapers_dir):
        for file in glob.glob(os.path.join(wallpapers_dir, 'page_*.json')):
            try:
                with open(file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for w in data.get('data', []):
                        if 'image_url' in w and 'id' in w:
                            existing_uuids[w['image_url']] = w['id']
            except Exception as e:
                print(f"Warning: Could not load existing JSON for UUIDs from {file}: {e}")
                
    # 2. Fallback to old monolithic file during transition
    if os.path.exists(WALLPAPERS_JSON):
        try:
            with open(WALLPAPERS_JSON, 'r', encoding='utf-8') as f:
                data = json.load(f)
                wallpapers_list = data.get('wallpapers', []) if isinstance(data, dict) else data
                for w in wallpapers_list:
                    if 'image_url' in w and 'id' in w:
                        existing_uuids[w['image_url']] = w['id']
        except Exception:
            pass
            
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
        json.dump(search_index, f, separators=(',', ':'), ensure_ascii=False)
        
    print(f"Generated lightweight search index at '{index_path}'.")

def generate_dart_models(api_dir: str):
    """Generate Dart models to make it effortless to parse the API in Flutter."""
    dart_code = """// AUTO-GENERATED CODE - DO NOT MODIFY BY HAND
// Use this code in your Flutter app to easily parse the Wallune API

import 'dart:convert';

class Wallpaper {
  final String id;
  final String title;
  final String category;
  final String imageUrl;
  final int size;
  final String updatedAt;
  final int width;
  final int height;

  Wallpaper({
    required this.id,
    required this.title,
    required this.category,
    required this.imageUrl,
    required this.size,
    required this.updatedAt,
    required this.width,
    required this.height,
  });

  factory Wallpaper.fromJson(Map<String, dynamic> json) {
    return Wallpaper(
      id: json['id'] ?? '',
      title: json['title'] ?? '',
      category: json['category'] ?? '',
      imageUrl: json['image_url'] ?? '',
      size: json['size'] ?? 0,
      updatedAt: json['updated_at'] ?? '',
      width: json['width'] ?? 0,
      height: json['height'] ?? 0,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'title': title,
      'category': category,
      'image_url': imageUrl,
      'size': size,
      'updated_at': updatedAt,
      'width': width,
      'height': height,
    };
  }
}

class PaginatedResponse {
  final int page;
  final int totalPages;
  final int totalItems;
  final int itemsPerPage;
  final bool hasNext;
  final bool hasPrev;
  final List<Wallpaper> data;

  PaginatedResponse({
    required this.page,
    required this.totalPages,
    required this.totalItems,
    required this.itemsPerPage,
    required this.hasNext,
    required this.hasPrev,
    required this.data,
  });

  factory PaginatedResponse.fromJson(Map<String, dynamic> json) {
    return PaginatedResponse(
      page: json['page'] ?? 1,
      totalPages: json['total_pages'] ?? 1,
      totalItems: json['total_items'] ?? 0,
      itemsPerPage: json['items_per_page'] ?? 20,
      hasNext: json['has_next'] ?? false,
      hasPrev: json['has_prev'] ?? false,
      data: (json['data'] as List?)
          ?.map((e) => Wallpaper.fromJson(e))
          .toList() ?? [],
    );
  }
}

class Category {
  final String name;
  final int count;
  final String cover;

  Category({
    required this.name,
    required this.count,
    required this.cover,
  });

  factory Category.fromJson(Map<String, dynamic> json) {
    return Category(
      name: json['name'] ?? '',
      count: json['count'] ?? 0,
      cover: json['cover'] ?? '',
    );
  }
}
"""
    dart_path = os.path.join(api_dir, 'models.dart')
    with open(dart_path, 'w', encoding='utf-8') as f:
        f.write(dart_code)
    print(f"Generated Dart models at '{dart_path}'.")

def process_images():
    if not os.path.exists(IMAGE_DIR):
        print(f"Error: Directory '{IMAGE_DIR}' not found.")
        return
        
    categories_info = {}
    wallpapers = []
    
    existing_uuids = load_existing_uuids(API_DIR)
            
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
                    
                file_path = os.path.join(category_path, file)
                size_res = get_image_size(file_path)
                # Fallback dimensions if unreadable
                width, height = size_res if size_res else (0, 0)
                
                categories_info[category_name]["count"] += 1
                title = get_clean_title(file)
                
                cat_url = urllib.parse.quote(category_name)
                full_url_name = urllib.parse.quote(file)
                
                base_github_url = f"https://raw.githubusercontent.com/{GITHUB_USERNAME}/{GITHUB_REPO_NAME}/{BRANCH}/{IMAGE_DIR}"
                full_url = f"{base_github_url}/{cat_url}/{full_url_name}"
                
                if categories_info[category_name]["cover"] is None:
                    categories_info[category_name]["cover"] = full_url
                
                wallpaper_id = existing_uuids.get(full_url, str(uuid.uuid4()))
                
                file_size = os.path.getsize(file_path)
                file_stat = os.stat(file_path)
                updated_at = datetime.fromtimestamp(file_stat.st_mtime).isoformat() + "Z"
                
                wallpapers.append({
                    "id": wallpaper_id,
                    "title": title,
                    "category": category_name,
                    "image_url": full_url,
                    "size": file_size,
                    "updated_at": updated_at,
                    "width": width,
                    "height": height
                })

    # Sort wallpapers by category then title to ensure determinism
    wallpapers.sort(key=lambda x: (x['category'], x['title']))

    final_categories = [
        {"name": k, "count": info["count"], "cover": info["cover"]} 
        for k, info in sorted(categories_info.items()) if info["count"] > 0
    ]

    # Write modern API structure
    os.makedirs(API_DIR, exist_ok=True)
    generate_paginated_api(wallpapers, API_DIR)
    generate_search_index(wallpapers, API_DIR)
    generate_dart_models(API_DIR)
    
    with open(os.path.join(API_DIR, 'categories.json'), 'w', encoding='utf-8') as f:
        json.dump(final_categories, f, indent=2, ensure_ascii=False)
        
    print(f"API generation complete. V1 API is available in '{API_DIR}'.")

if __name__ == "__main__":
    process_images()
