import sqlite3
import pandas as pd
import os
import logging

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

DATABASE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'tenders.db')

def get_connection():
    """
    Create a connection to the SQLite database
    """
    try:
        conn = sqlite3.connect(DATABASE_PATH)
        return conn
    except sqlite3.Error as e:
        logger.error(f"Database connection error: {e}")
        raise

def initialize_database():
    """
    Create the database tables if they don't exist
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        # Create the tenders table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS tenders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            vergabe_id TEXT UNIQUE,
            ausschreibungstitel TEXT,
            auftraggeber TEXT,
            vergabestelle TEXT,
            link TEXT,
            leistungsort TEXT,
            veroeffentlicht_seit TEXT,
            naechste_frist TEXT,
            suchbegriff TEXT,
            website TEXT,
            scrape_date TEXT,
            UNIQUE(vergabe_id, suchbegriff)
        )
        ''')
        
        conn.commit()
        logger.info("Database initialized successfully")
    except sqlite3.Error as e:
        logger.error(f"Database initialization error: {e}")
        conn.rollback()
    finally:
        conn.close()

def insert_tenders(df):
    """
    Insert tenders from a DataFrame into the database
    Only inserts tenders that don't already exist in the database
    
    Returns:
        tuple: (total_records, new_records)
    """
    if df.empty:
        logger.info("No tenders to insert")
        return 0, 0
    
    # Rename DataFrame columns to match database columns
    column_mapping = {
        'Vergabe-ID': 'vergabe_id',
        'Ausschreibungstitel': 'ausschreibungstitel',
        'Auftraggeber': 'auftraggeber',
        'Vergabestelle': 'vergabestelle',
        'Link zur Ausschreibung': 'link',
        'Leistungsort': 'leistungsort',
        'veröffentlicht seit': 'veroeffentlicht_seit',
        'nächste Frist': 'naechste_frist',
        'Suchbegriff': 'suchbegriff',
        'Website': 'website'
    }
    
    # Create a copy of the DataFrame with renamed columns
    df_db = df.rename(columns=column_mapping)
    
    # Add scrape date
    from datetime import datetime
    df_db['scrape_date'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    # Select only the columns we need
    columns = ['vergabe_id', 'ausschreibungstitel', 'auftraggeber', 'vergabestelle', 
               'link', 'leistungsort', 'veroeffentlicht_seit', 'naechste_frist', 
               'suchbegriff', 'website', 'scrape_date']
    
    df_db = df_db[columns]
    
    # Connect to the database
    conn = get_connection()
    total_records = len(df_db)
    new_records = 0
    
    try:
        # For each row in the DataFrame, try to insert it
        for _, row in df_db.iterrows():
            try:
                cursor = conn.cursor()
                cursor.execute('''
                INSERT OR IGNORE INTO tenders 
                (vergabe_id, ausschreibungstitel, auftraggeber, vergabestelle, 
                 link, leistungsort, veroeffentlicht_seit, naechste_frist, 
                 suchbegriff, website, scrape_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    row['vergabe_id'],
                    row['ausschreibungstitel'],
                    row['auftraggeber'],
                    row['vergabestelle'],
                    row['link'],
                    row['leistungsort'],
                    row['veroeffentlicht_seit'],
                    row['naechste_frist'],
                    row['suchbegriff'],
                    row['website'],
                    row['scrape_date']
                ))
                
                if cursor.rowcount > 0:
                    new_records += 1
                
            except sqlite3.Error as e:
                logger.error(f"Error inserting tender: {e}")
                continue
        
        conn.commit()
        logger.info(f"Inserted {new_records} new tenders out of {total_records} total")
        
    except Exception as e:
        logger.error(f"Error during database insertion: {e}")
        conn.rollback()
    finally:
        conn.close()
    
    return total_records, new_records

def get_all_tenders():
    """
    Retrieve all tenders from the database
    
    Returns:
        pandas.DataFrame: DataFrame containing all tenders
    """
    conn = get_connection()
    
    try:
        # Reverse the column mapping to match the app's expected column names
        column_mapping = {
            'vergabe_id': 'Vergabe-ID',
            'ausschreibungstitel': 'Ausschreibungstitel',
            'auftraggeber': 'Auftraggeber',
            'vergabestelle': 'Vergabestelle',
            'link': 'Link zur Ausschreibung',
            'leistungsort': 'Leistungsort',
            'veroeffentlicht_seit': 'veröffentlicht seit',
            'naechste_frist': 'nächste Frist',
            'suchbegriff': 'Suchbegriff',
            'website': 'Website'
        }
        
        # Query the database
        df = pd.read_sql_query("SELECT * FROM tenders", conn)
        
        # Rename columns to match the app's expected column names
        if not df.empty:
            df = df.rename(columns=column_mapping)
        
        return df
    
    except sqlite3.Error as e:
        logger.error(f"Error retrieving tenders: {e}")
        return pd.DataFrame()
    finally:
        conn.close()

def search_tenders(search_term=None, days=None):
    """
    Search for tenders in the database based on search term and/or days
    
    Args:
        search_term (str, optional): Search term to filter by
        days (int, optional): Number of days to look back
        
    Returns:
        pandas.DataFrame: DataFrame containing matching tenders
    """
    conn = get_connection()
    
    try:
        query = "SELECT * FROM tenders WHERE 1=1"
        params = []
        
        if search_term:
            query += " AND suchbegriff LIKE ?"
            params.append(f"%{search_term}%")
        
        if days:
            query += " AND julianday('now') - julianday(scrape_date) <= ?"
            params.append(days)
        
        # Reverse the column mapping to match the app's expected column names
        column_mapping = {
            'vergabe_id': 'Vergabe-ID',
            'ausschreibungstitel': 'Ausschreibungstitel',
            'auftraggeber': 'Auftraggeber',
            'vergabestelle': 'Vergabestelle',
            'link': 'Link zur Ausschreibung',
            'leistungsort': 'Leistungsort',
            'veroeffentlicht_seit': 'veröffentlicht seit',
            'naechste_frist': 'nächste Frist',
            'suchbegriff': 'Suchbegriff',
            'website': 'Website'
        }
        
        # Query the database
        df = pd.read_sql_query(query, conn, params=params)
        
        # Rename columns to match the app's expected column names
        if not df.empty:
            df = df.rename(columns=column_mapping)
        
        return df
    
    except sqlite3.Error as e:
        logger.error(f"Error searching tenders: {e}")
        return pd.DataFrame()
    finally:
        conn.close()
