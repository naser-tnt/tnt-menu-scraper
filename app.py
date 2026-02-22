import streamlit as st
import os
import shutil
import json
import pandas as pd
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse
from datetime import datetime
from scraper import fetch_html, extract_menu_data, process_menu_data, download_image, merge_data

st.set_page_config(page_title="Menu Scraper", layout="wide")

st.title("Menu Scraper")
st.markdown("Extract menu items, prices, and images from restaurant pages.")

# --- Session State Initialization ---
if 'data_processed' not in st.session_state:
    st.session_state.data_processed = False
if 'session_id' not in st.session_state:
    st.session_state.session_id = None
if 'excel_path' not in st.session_state:
    st.session_state.excel_path = None
if 'zip_path' not in st.session_state:
    st.session_state.zip_path = None
if 'logs' not in st.session_state:
    st.session_state.logs = []
if 'menu_df' not in st.session_state:
    st.session_state.menu_df = pd.DataFrame()

with st.sidebar:
    st.header("Advanced Settings")
    download_images = st.checkbox("Download Images", value=True)
    scrape_en = st.checkbox("Scrape English Menu", value=True)
    scrape_ar = st.checkbox("Scrape Arabic Menu", value=True)
    batch_size = st.slider("Image Download Batch Size", 1, 20, 10)
    name_format = st.selectbox("Image Naming Format", ["Product Name", "ID Only", "ID + Product Name"])

url_input = st.text_input("Enter Restaurant URL (English or Arabic)", placeholder="https://www.your-restaurant-url.com/...")

def run_scraper():
    if not url_input:
        st.error("Please enter a URL.")
        return
        
    if not scrape_en and not scrape_ar:
        st.error("Please select at least one language to scrape.")
        return

    # Create a timestamped session ID for file storage
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    try:
        path_parts = urlparse(url_input).path.split('/')
        if 'restaurant' in path_parts:
            idx = path_parts.index('restaurant')
            rest_name = path_parts[idx+2] if idx + 2 < len(path_parts) else "unknown"
        else:
            rest_name = "unknown"
    except:
        rest_name = "unknown"

    session_id = os.path.join("scraped_data", f"{timestamp}_{rest_name}")
    os.makedirs(session_id, exist_ok=True)
    images_dir = os.path.join(session_id, "images")
    os.makedirs(images_dir, exist_ok=True)
    
    st.session_state.session_id = session_id

    # Determine URLs
    url_en, url_ar = "", ""
    parsed_url = urlparse(url_input)
    path = parsed_url.path
    
    if "/ar/" in path:
        url_ar = url_input
        url_en = f"{parsed_url.scheme}://{parsed_url.netloc}{path.replace('/ar/', '/')}?{parsed_url.query}"
    else:
        url_en = url_input
        url_ar = f"{parsed_url.scheme}://{parsed_url.netloc}/ar{path}?{parsed_url.query}"

    st.info(f"Processing URLs:\n- EN: {url_en}\n- AR: {url_ar}")
    
    # Live Dashboard Metrics
    metric_cols = st.columns(3)
    metric_items = metric_cols[0].empty()
    metric_images = metric_cols[1].empty()
    metric_time = metric_cols[2].empty()
    
    metric_items.metric("Total Items Found", "0")
    metric_images.metric("Images Downloaded", "0")
    metric_time.metric("Elapsed Time", "0s")
    
    start_time = time.time()
    progress_bar = st.progress(0)
    
    st.markdown("### Process Log")
    log_container = st.empty()
    st.session_state.logs = []

    def log(message):
        ts = datetime.now().strftime("%H:%M:%S")
        st.session_state.logs.append(f"[{ts}] {message}")
        log_container.code("\n".join(st.session_state.logs), language="text")
        metric_time.metric("Elapsed Time", f"{int(time.time() - start_time)}s")

    data_en, data_ar = [], []
    
    # 1. Scrape English
    if scrape_en:
        log("Fetching English Menu...")
        try:
            html_en = fetch_html(url_en)
            json_en = extract_menu_data(html_en)
            if json_en:
                data_en = process_menu_data(json_en)
                log(f"Found {len(data_en)} items in English menu.")
            else:
                log("WARNING: Could not extract English menu data.")
        except Exception as e:
            log(f"ERROR fetching English URL: {e}")
            
    progress_bar.progress(30)
    
    # 2. Scrape Arabic
    if scrape_ar:
        log("Fetching Arabic Menu...")
        try:
            html_ar = fetch_html(url_ar)
            json_ar = extract_menu_data(html_ar)
            if json_ar:
                data_ar = process_menu_data(json_ar)
                log(f"Found {len(data_ar)} items in Arabic menu.")
            else:
                log("WARNING: Could not extract Arabic menu data.")
        except Exception as e:
            log(f"ERROR fetching Arabic URL: {e}")
            
    progress_bar.progress(60)
    
    # 3. Merge Data
    log("Merging Data...")
    df = merge_data(data_en, data_ar)
    
    metric_items.metric("Total Items Found", str(len(df)))
    
    excel_path = os.path.join(session_id, "menu_data.xlsx")
    df.to_excel(excel_path, index=False)
    st.session_state.excel_path = excel_path
    st.session_state.menu_df = df
    
    progress_bar.progress(70)
    
    # 4. Download Images
    if download_images and not df.empty and 'originalImage' in df.columns:
        log(f"Downloading Images in batches of {batch_size}...")
        total_images = len(df)
        downloaded_count = 0
        
        # Prepare list of tasks
        tasks = []
        for i, row in df.iterrows():
            img_url = row['originalImage']
            if img_url and pd.notna(img_url):
                product_name = row.get('name_en') or row.get('name_ar') or f"item_{i}"
                safe_product_name = "".join([c for c in str(product_name) if c.isalpha() or c.isdigit() or c in "._- "]).strip()
                item_id = row.get('id', i)
                
                if name_format == "Product Name":
                    custom_name = safe_product_name
                elif name_format == "ID + Product Name":
                    custom_name = f"{item_id}_{safe_product_name}"
                else:
                    custom_name = f"item_{item_id}"
                
                tasks.append((img_url, images_dir, "", custom_name))
        
        # Execute batch downloads
        completed = 0
        with ThreadPoolExecutor(max_workers=batch_size) as executor:
            futures = [executor.submit(download_image, t[0], t[1], t[2], t[3]) for t in tasks]
            for future in as_completed(futures):
                path = future.result()
                if path:
                    downloaded_count += 1
                
                completed += 1
                metric_images.metric("Images Downloaded", f"{downloaded_count} / {len(tasks)}")
                metric_time.metric("Elapsed Time", f"{int(time.time() - start_time)}s")
                
                if completed % batch_size == 0 or completed == len(tasks):
                    log(f"Progress: {completed}/{len(tasks)} tasks processed...")
                
                current_progress = 70 + int((completed / max(1, len(tasks))) * 30)
                progress_bar.progress(min(current_progress, 99))
            
        log(f"Finished downloading {downloaded_count} images.")
    
    progress_bar.progress(100)
    metric_time.metric("Elapsed Time", f"{int(time.time() - start_time)}s")
    log("Done! Ready for download.")
    
    zip_base_name = f"{session_id}_download"
    shutil.make_archive(zip_base_name, 'zip', session_id)
    st.session_state.zip_path = f"{zip_base_name}.zip"

    st.session_state.data_processed = True

if st.button("Start Scraping", use_container_width=True, type="primary"):
    run_scraper()

if st.session_state.data_processed:
    st.markdown("### Interactive Data Editor")
    
    edited_df = st.data_editor(st.session_state.menu_df, num_rows="dynamic", use_container_width=True)
    
    if not edited_df.equals(st.session_state.menu_df):
        st.session_state.menu_df = edited_df
        edited_df.to_excel(st.session_state.excel_path, index=False)
        
        session_id = st.session_state.session_id
        zip_base_name = f"{session_id}_download"
        shutil.make_archive(zip_base_name, 'zip', session_id)
        
        # We implicitly re-render because we've updated the zip archie right here.
        # But to be safe, we will just continue cleanly.

    st.subheader("Downloads")
    st.success(f"Scraping completed. Data saved to: {st.session_state.session_id}")
    
    col_d1, col_d2 = st.columns(2)
    
    # Read eagerly so modifications apply
    if st.session_state.excel_path and os.path.exists(st.session_state.excel_path):
        with open(st.session_state.excel_path, "rb") as f:
            excel_data = f.read()
            col_d1.download_button("Download Excel", data=excel_data, file_name="menu_data.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)

    if st.session_state.zip_path and os.path.exists(st.session_state.zip_path):
        with open(st.session_state.zip_path, "rb") as f:
            zip_data = f.read()
            col_d2.download_button("Download Full Menu (Zip)", data=zip_data, file_name="full_menu.zip", mime="application/zip", use_container_width=True)
