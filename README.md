# Evergabe Tender Scraper

This Streamlit application scrapes tender information from evergabe.de based on user-provided search terms. Results are filtered for tenders published in the last 7 days and can be downloaded as CSV or Excel files with clickable links.

## Features

- Search for tenders using a single search term or multiple terms from a file
- Filter results for the last 7 days
- Display results in a tabular format
- Export results to CSV and Excel (with clickable links)
- Configurable maximum number of pages to scrape
- Database storage of tender information with duplicate prevention
- Automatic cleanup of debug files between runs

## Data Collected

For each tender, the following information is collected:

- Website source (evergabe.de)
- Tender title (Ausschreibungstitel)
- Client (Auftraggeber)
- Awarding authority (Vergabestelle)
- Tender link
- Location (Leistungsort)
- Publication date
- Next deadline
- Tender ID (Vergabe-ID)

## Installation

1. Clone this repository
2. Install the required dependencies using one of the following methods:

### Option 1: Using requirements.txt (Recommended for most users)

```bash
pip install -r requirements.txt
```

### Option 2: Using pyproject.toml (For development or distribution)

If you have pip >= 21.3:

```bash
pip install -e .
```

Or if you use Poetry:

```bash
poetry install
```

## Usage

Run the Streamlit app:

```bash
streamlit run app.py
```

### Option 1: Single Search Term

1. Enter a search term in the text input field
2. Adjust the number of days to look back
3. Click 'Run Scraper'

### Option 2: Multiple Search Terms

1. Create a markdown (.md) or text (.txt) file with one search term per line
   - You can use the provided `sample_search_terms.md` as a template
2. Upload the file using the file uploader
3. Click 'Run Scraper'

### Database Features

- All scraped tenders are automatically saved to a SQLite database (tenders.db)
- Only new tenders are added to the database (duplicates are ignored)
- You can view all database entries by checking the "View all database entries" option
- You can also view the database contents without running the scraper by clicking "View Database Contents"

### Debugging

The scraper saves HTML content of scraped pages to the `debug_pages` folder for inspection. This folder is automatically cleaned at the start of each new scraper run.

## Requirements

The application requires:

- Python 3.7+
- Chrome browser (for Selenium)
- Dependencies listed in requirements.txt
