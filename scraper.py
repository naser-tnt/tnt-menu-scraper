import requests
import json
import re
import os
import time
import pandas as pd
from tenacity import retry, stop_after_attempt, wait_fixed
import mimetypes
from urllib.parse import urlparse

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

@retry(stop=stop_after_attempt(3), wait=wait_fixed(2))
def fetch_html(url, proxy=None):
    """Fetches HTML content from a URL, optionally using a proxy."""
    proxies = None
    if proxy:
        proxies = {
            "http": proxy,
            "https": proxy,
        }
    
    try:
        response = requests.get(url, headers=HEADERS, proxies=proxies, timeout=10)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        print(f"Error fetching {url} with proxy {proxy}: {e}")
        raise

def extract_menu_data(html_content):
    """Extracts the menuData JSON object from the HTML."""
    # Look for the pattern "menuData": { ... }
    # This is a bit heuristic. It often appears inside a larger JSON structure in a script tag.
    # We'll try to find the specific script tag or regex match.
    
    # Strategy 1: Regex for "menuData":\s*(\{.*?\}) but matching balanced braces is hard with regex.
    # Strategy 2: Look for the Next.js data or similar state object if it exists.
    # Strategy 3: Simple string search and json parsing (brute force).
    
    # Let's try to find the script tag that contains "menuData"
    # The user provided snippet shows "menuData": { "items": ... }
    
    # Often in these sites it's in window.__DATA__ or similar.
    # Let's try a regex that captures the JSON object assuming it's part of a larger structure
    # We will look for the specific key and then try to parse the object.
    
    match = re.search(r'"menuData"\s*:\s*({)', html_content)
    if not match:
        # Fallback: maybe it's not quoted?
        match = re.search(r'menuData\s*:\s*({)', html_content)
    
    if match:
        start_index = match.start(1)
        # We need to find the matching closing brace.
        # This is a simple parser to find the end of the JSON object.
        brace_count = 0
        for i, char in enumerate(html_content[start_index:]):
            if char == '{':
                brace_count += 1
            elif char == '}':
                brace_count -= 1
                if brace_count == 0:
                    json_str = html_content[start_index : start_index + i + 1]
                    try:
                        return json.loads(json_str)
                    except json.JSONDecodeError:
                        print("Failed to parse extracted JSON string.")
                        return None
        print("Could not find closing brace for menuData.")
        return None
    
    print("Could not find 'menuData' in HTML.")
    return None

def process_menu_data(menu_data):
    """Parses the menuData dictionary into a flat list of items."""
    if not menu_data or 'items' not in menu_data:
        return []
    
    items = []
    for item in menu_data['items']:
        # Extract relevant fields
        processed_item = {
            'id': item.get('id'),
            'name': item.get('name'),
            'description': item.get('description'),
            'price': item.get('price'),
            'originalSection': item.get('originalSection'),
            'image': item.get('image'), # Thumbnail?
            'originalImage': item.get('originalImage'), # Full size
            'sectionName': item.get('sectionName')
        }
        items.append(processed_item)
    return items

def download_image(url, save_dir, filename_prefix="", custom_filename=None):
    """Downloads an image and saves it to the specified directory."""
    if not url:
        return None
    
    # Clean URL (sometimes they have query params)
    clean_url = url.split('?')[0]
    
    try:
        response = requests.get(url, headers=HEADERS, stream=True)
        response.raise_for_status()
        
        # Determine extension
        ext = os.path.splitext(clean_url)[1]
        if not ext:
            content_type = response.headers.get('Content-Type')
            if content_type:
                ext = mimetypes.guess_extension(content_type)
        
        if not ext:
            ext = ".jpg" # Default fallback
            
        if custom_filename:
            # Sanitize custom filename
            safe_name = "".join([c for c in custom_filename if c.isalpha() or c.isdigit() or c in "._- "]).strip()
            filename = f"{safe_name}{ext}"
        else:
            filename = f"{filename_prefix}{os.path.basename(clean_url)}"
            # Ensure filename is safe
            filename = "".join([c for c in filename if c.isalpha() or c.isdigit() or c in "._- "]).strip()
            
        save_path = os.path.join(save_dir, filename)
        
        # Handle duplicates if using custom filename
        if custom_filename and os.path.exists(save_path):
            base, extension = os.path.splitext(filename)
            counter = 1
            while os.path.exists(save_path):
                save_path = os.path.join(save_dir, f"{base}_{counter}{extension}")
                counter += 1
        elif os.path.exists(save_path):
             return save_path # Skip if exists (only for non-custom names where we assume URL is unique ID)

        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(1024):
                f.write(chunk)
        time.sleep(0.5) # Rate limiting
        return save_path
    except Exception as e:
        print(f"Failed to download image {url}: {e}")
        return None

def merge_data(english_items, arabic_items):
    """Merges English and Arabic item lists into a DataFrame."""
    # Convert to DataFrames
    df_en = pd.DataFrame(english_items)
    df_ar = pd.DataFrame(arabic_items)
    
    # Rename columns for clarity before merge
    df_en = df_en.rename(columns={
        'name': 'name_en',
        'description': 'description_en',
        'originalSection': 'section_en',
        'price': 'price_en'
    })
    
    df_ar = df_ar.rename(columns={
        'name': 'name_ar',
        'description': 'description_ar',
        'originalSection': 'section_ar',
        'price': 'price_ar' # Should be same, but good to have
    })
    
    # Merge on ID
    # Assuming 'id' is consistent. If not, we might need to merge on index if lists are identical order.
    # But ID is safer.
    
    if 'id' in df_en.columns and 'id' in df_ar.columns:
        merged_df = pd.merge(df_en, df_ar[['id', 'name_ar', 'description_ar', 'section_ar']], on='id', how='outer')
    else:
        # Fallback: concat if IDs missing (unlikely for API data)
        print("Warning: IDs missing, merging by index.")
        merged_df = pd.concat([df_en, df_ar[['name_ar', 'description_ar', 'section_ar']]], axis=1)

    # Select and Reorder columns for CSV export
    # "category name, item name, descreption price"
    # We'll include both languages
    
    final_columns = [
        'id',
        'section_en', 'section_ar',
        'name_en', 'name_ar',
        'description_en', 'description_ar',
        'price_en',
        'originalImage'
    ]
    
    # Filter only existing columns
    final_columns = [c for c in final_columns if c in merged_df.columns]
    
    return merged_df[final_columns]
