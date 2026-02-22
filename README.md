# Menu Scraper 

A Streamlit web application to scrape menu data from restaurant pages, supporting both English and Arabic menus, image downloading, and Excel export.

## Features
- **Dual Language Scraping**: Automatically fetches English and Arabic menus (where available).
- **Data Merging**: Combines data into a single Excel file with aligned columns.
- **Image Downloading**: Downloads item images as part of the job.
- **Real-time Logging**: Terminal-style logs directly inside the UI.
- **Persistent History**: Saves scraped data to timestamped folders locally.

## Installation

1.  **Clone the repository**:
    ```bash
    git clone <your-repo-url>
    cd scraper
    ```

2.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

3.  **Run the app**:
    ```bash
    streamlit run app.py
    ```

## Usage
Simply enter the URL of the restaurant you wish to scrape and click "Start Scraping". Wait for the progress bar to complete and download the entire zip file or just the generated excel sheet.
