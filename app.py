import streamlit as st
import pandas as pd
import os
import sys
import tempfile
import asyncio
import shutil
from evergabe_scrape import scrape_evergabe
import database
from PIL import Image

# Initialize the database when the app starts
database.initialize_database()

# Function to clean up debug_pages folder
def cleanup_debug_pages():
    debug_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'debug_pages')
    if os.path.exists(debug_dir) and os.path.isdir(debug_dir):
        try:
            # Delete all files in the debug_pages folder
            for filename in os.listdir(debug_dir):
                file_path = os.path.join(debug_dir, filename)
                if os.path.isfile(file_path):
                    os.unlink(file_path)
            st.info(f"Cleaned up debug_pages folder")
        except Exception as e:
            st.error(f"Error cleaning up debug_pages folder: {e}")
    else:
        # Create the directory if it doesn't exist
        os.makedirs(debug_dir, exist_ok=True)
        st.info(f"Created debug_pages folder")

st.set_page_config(page_title="Evergabe Scraper", page_icon="🔍", layout="wide")

# Custom CSS for better styling
st.markdown("""
<style>
.main .block-container {
    padding-top: 2rem;
}
.stDataFrame {
    width: 100%;
}
</style>
""", unsafe_allow_html=True)

# Create two columns for the header section
col1, col2 = st.columns([2, 1])

# First column: App title and description
with col1:
    st.title("Evergabe Tender Scraper")
    st.markdown("""This app scrapes tender information from evergabe.de based on your search terms.  
Results are stored in a database and can be downloaded as CSV or Excel.""")

# Second column: Header image
with col2:
    header_image_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Header für AdvSolution2.png')
    if os.path.exists(header_image_path):
        header_image = Image.open(header_image_path)
        st.image(header_image, use_container_width=True)

# Sidebar for inputs
with st.sidebar:
    st.header("Search Options")
    
    # Option 1: Custom search term
    st.subheader("Option 1: Single Search Term")
    search_term = st.text_input("Enter a search term", value="strahlenschutz")
    max_days = st.slider("Days to look back", min_value=1, max_value=30, value=7)
    
    # Option 2: Upload MD file with search terms
    st.subheader("Option 2: Multiple Search Terms")
    st.markdown("Upload a markdown file with one search term per line")
    uploaded_file = st.file_uploader("Choose a markdown file", type=["md", "txt"])
    
    # Display options
    st.subheader("Display Options")
    hide_empty_columns = st.checkbox("Hide columns with no data", value=True, 
                                    help="Hide columns where all values are 'Nicht verfügbar'")
    
    # Database options
    st.subheader("Database Options")
    view_database = st.checkbox("View all database entries", value=False, 
                              help="Show all entries from the database instead of just the new ones")
    
    # Execution button
    run_button = st.button("Run Scraper", type="primary")

# Function to process a single search term
async def process_search_term(term, days):
    with st.spinner(f"Scraping evergabe.de for: {term} (last {days} days)..."):
        results_df = await scrape_evergabe(search_term=term, days=days)
        return results_df

# Main content area
if run_button:
    cleanup_debug_pages()  # Call the cleanup function here
    all_results = []
    
    # Process based on selected option
    if uploaded_file is not None:
        # Process the uploaded file with multiple search terms
        content = uploaded_file.getvalue().decode("utf-8")
        search_terms = [line.strip() for line in content.split("\n") if line.strip()]
        
        st.info(f"Found {len(search_terms)} search terms in the uploaded file")
        
        progress_bar = st.progress(0)
        combined_df = pd.DataFrame()
        
        for i, term in enumerate(search_terms):
            st.write(f"Processing search term: {term}")
            df = asyncio.run(process_search_term(term, max_days))
            if not df.empty:
                combined_df = pd.concat([combined_df, df], ignore_index=True)
            progress_bar.progress((i + 1) / len(search_terms))
        
        df = combined_df
    else:
        # Process the single search term
        df = asyncio.run(process_search_term(search_term, max_days))
    
    # Display results
    if not df.empty:
        # Insert the results into the database and get the count of new entries
        total_records, new_records = database.insert_tenders(df)
        
        # Display summary
        st.success(f"Found {total_records} tender results, added {new_records} new entries to the database")
        
        # Decide which data to display based on user preference
        if view_database:
            st.subheader("All Database Entries")
            display_df = database.get_all_tenders()
            if display_df.empty:
                st.warning("No entries found in the database.")
                st.stop()
        else:
            st.subheader("Newly Scraped Tender Results")
            display_df = df
        
        # Filter out columns where all values are "Nicht verfügbar" if option is selected
        if hide_empty_columns:
            # Find columns where all values are "Nicht verfügbar"
            empty_columns = [col for col in display_df.columns if (display_df[col] == "Nicht verfügbar").all()]
            
            # Ensure we don't hide essential columns
            essential_columns = ['Ausschreibungstitel', 'Suchbegriff', 'Link zur Ausschreibung', 'veröffentlicht seit', 'nächste Frist']
            empty_columns = [col for col in empty_columns if col not in essential_columns]
            
            if empty_columns:
                st.info(f"Hiding {len(empty_columns)} columns with no data: {', '.join(empty_columns)}")
                df_display = display_df.drop(columns=empty_columns)
            else:
                df_display = display_df.copy()
        else:
            df_display = display_df.copy()
        
        # Make sure we have at least some columns to display
        if df_display.empty or len(df_display.columns) == 0:
            st.warning("All columns would be hidden. Showing original data instead.")
            df_display = display_df.copy()
        
        # Make links clickable in the dataframe
        def make_clickable(val):
            return f'<a href="{val}" target="_blank">Link</a>' if val != "N/A" and val != "Nicht verfügbar" else "N/A"
        
        df_display['Link zur Ausschreibung'] = df_display['Link zur Ausschreibung'].apply(make_clickable)
        
        st.write(df_display.to_html(escape=False, index=False), unsafe_allow_html=True)
        
        # Download buttons
        col1, col2 = st.columns(2)
        with col1:
            csv = df_display.to_csv(index=False, encoding='utf-8-sig')
            st.download_button(
                label="Download CSV",
                data=csv,
                file_name="evergabe_results.csv",
                mime="text/csv",
            )
        
        with col2:
            # Create Excel file with clickable links
            excel_df = df_display.copy()
            
            # Convert clickable HTML links back to regular URLs for Excel
            if 'Link zur Ausschreibung' in excel_df.columns:
                excel_df['Link zur Ausschreibung'] = display_df['Link zur Ausschreibung']
            
            # Format links for Excel
            excel_df['Link zur Ausschreibung'] = excel_df['Link zur Ausschreibung'].apply(
                lambda x: f'=HYPERLINK("{x}","Link zur Ausschreibung")' if x != "N/A" and x != "Nicht verfügbar" else "N/A"
            )
            
            # Save to a temporary file
            with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
                excel_df.to_excel(tmp.name, index=False, engine='openpyxl')
                tmp_path = tmp.name
            
            with open(tmp_path, "rb") as file:
                st.download_button(
                    label="Download Excel",
                    data=file,
                    file_name="evergabe_results.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
            
            # Clean up the temporary file
            os.unlink(tmp_path)
    else:
        st.warning("No results found. Try a different search term or check your internet connection.")

# Add a section to view database contents without running the scraper
if not run_button:
    st.subheader("Database Contents")
    view_db_button = st.button("View Database Contents")
    
    if view_db_button:
        df = database.get_all_tenders()
        if not df.empty:
            st.success(f"Found {len(df)} entries in the database")
            
            # Filter out columns where all values are "Nicht verfügbar" if option is selected
            if hide_empty_columns:
                # Find columns where all values are "Nicht verfügbar"
                empty_columns = [col for col in df.columns if (df[col] == "Nicht verfügbar").all()]
                
                # Ensure we don't hide essential columns
                essential_columns = ['Ausschreibungstitel', 'Suchbegriff', 'Link zur Ausschreibung', 'veröffentlicht seit', 'nächste Frist']
                empty_columns = [col for col in empty_columns if col not in essential_columns]
                
                if empty_columns:
                    st.info(f"Hiding {len(empty_columns)} columns with no data: {', '.join(empty_columns)}")
                    df_display = df.drop(columns=empty_columns)
                else:
                    df_display = df.copy()
            else:
                df_display = df.copy()
            
            # Make links clickable in the dataframe
            def make_clickable(val):
                return f'<a href="{val}" target="_blank">Link</a>' if val != "N/A" and val != "Nicht verfügbar" else "N/A"
            
            df_display['Link zur Ausschreibung'] = df_display['Link zur Ausschreibung'].apply(make_clickable)
            
            st.write(df_display.to_html(escape=False, index=False), unsafe_allow_html=True)
            
            # Download buttons
            col1, col2 = st.columns(2)
            with col1:
                csv = df_display.to_csv(index=False, encoding='utf-8-sig')
                st.download_button(
                    label="Download CSV",
                    data=csv,
                    file_name="evergabe_database.csv",
                    mime="text/csv",
                )
            
            with col2:
                # Create Excel file with clickable links
                excel_df = df_display.copy()
                
                # Convert clickable HTML links back to regular URLs for Excel
                if 'Link zur Ausschreibung' in excel_df.columns:
                    excel_df['Link zur Ausschreibung'] = df['Link zur Ausschreibung']
                
                # Format links for Excel
                excel_df['Link zur Ausschreibung'] = excel_df['Link zur Ausschreibung'].apply(
                    lambda x: f'=HYPERLINK("{x}","Link zur Ausschreibung")' if x != "N/A" and x != "Nicht verfügbar" else "N/A"
                )
                
                # Save to a temporary file
                with tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx') as tmp:
                    excel_df.to_excel(tmp.name, index=False, engine='openpyxl')
                    tmp_path = tmp.name
                
                with open(tmp_path, "rb") as file:
                    st.download_button(
                        label="Download Excel",
                        data=file,
                        file_name="evergabe_database.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                
                # Clean up the temporary file
                os.unlink(tmp_path)
        else:
            st.warning("No entries found in the database.")

# Instructions at the bottom
with st.expander("How to use this app"):
    st.markdown("""
    ### Instructions
    
    #### Option 1: Single Search Term
    1. Enter a search term in the text input field
    2. Adjust the number of days to look back
    3. Click 'Run Scraper'
    
    #### Option 2: Multiple Search Terms
    1. Create a markdown (.md) or text (.txt) file with one search term per line
    2. Upload the file using the file uploader
    3. Click 'Run Scraper'
    
    #### Database Features
    - All scraped tenders are automatically saved to a database
    - Only new tenders are added to the database (duplicates are ignored)
    - You can view all database entries by checking the "View all database entries" option
    - You can also view the database contents without running the scraper by clicking "View Database Contents"
    
    #### Results
    - Results are filtered for tenders published in the specified time period
    - You can download the results as CSV or Excel (with clickable links)
    - The Excel file contains clickable links to the tender pages
    """)
