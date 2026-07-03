import os
import json
import shutil
from PIL import Image
from google import genai
from google.genai import types
import generate_api

# Configuration
NEW_WALL_DIR = 'new_wall'
IMAGES_DIR = 'images'
WALLPAPERS_JSON = 'wallpapers.json'

def get_categories():
    categories = [d for d in os.listdir(IMAGES_DIR) if os.path.isdir(os.path.join(IMAGES_DIR, d))]
    return categories

def process_images():
    categories = get_categories()
    
    # Initialize Gemini client
    # Expects GEMINI_API_KEY environment variable to be set
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY environment variable not set.")
        print("Please set it using: $env:GEMINI_API_KEY='your_api_key' in PowerShell")
        return

    # Using the google-genai SDK
    client = genai.Client()
    
    system_instruction = f"""
    You are an AI that categorizes and names wallpapers.
    Available categories: {', '.join(categories)}.
    Analyze the image and provide a JSON response with two keys:
    - "name": a short, descriptive file name for the image (using lowercase and underscores, e.g. "dark_forest_lake"). Do NOT include the extension.
    - "category": the exact name of the best matching category from the available list.
    """
    
    new_images = [f for f in os.listdir(NEW_WALL_DIR) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))]
    
    if not new_images:
        print("No new images found in 'new_wall'.")
        return
        
    for image_file in new_images:
        image_path = os.path.join(NEW_WALL_DIR, image_file)
        print(f"Processing {image_file}...")
        
        try:
            img = Image.open(image_path)
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=[img, system_instruction],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.2,
                )
            )
            
            result = json.loads(response.text)
            new_name = result.get('name', '').replace(' ', '_').lower()
            category = result.get('category', '')
            
            if category not in categories:
                print(f"  Warning: Invalid category '{category}' returned. Using 'Abstract' as fallback.")
                category = 'Abstract'
                
            if not new_name:
                new_name = "untitled"
                
            ext = os.path.splitext(image_file)[1].lower()
            new_filename = f"{new_name}{ext}"
            
            target_dir = os.path.join(IMAGES_DIR, category)
            os.makedirs(target_dir, exist_ok=True)
            target_path = os.path.join(target_dir, new_filename)
            
            # Ensure unique filename
            counter = 1
            while os.path.exists(target_path):
                new_filename = f"{new_name}_{counter}{ext}"
                target_path = os.path.join(target_dir, new_filename)
                counter += 1
                
            # Move and rename
            shutil.move(image_path, target_path)
            print(f"  -> Moved to {target_path}")
            
        except Exception as e:
            print(f"  Error processing {image_file}: {e}")
            
    print("\nAll new images processed.")
    print("Updating wallpapers.json by running generate_api.py...")
    generate_api.process_images()
    print("Done!")

if __name__ == "__main__":
    process_images()
