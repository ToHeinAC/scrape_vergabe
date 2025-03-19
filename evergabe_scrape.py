import pandas as pd
from datetime import datetime, timedelta
import os
import time
import random
import asyncio
from bs4 import BeautifulSoup
from crawl4ai import AsyncWebCrawler, CacheMode
from crawl4ai.async_configs import BrowserConfig, CrawlerRunConfig

# Ensure debug directory exists
os.makedirs('debug_pages', exist_ok=True)

# Save HTML content for debugging
def save_debug_page(page_num, content):
    with open(f'debug_pages/page_{page_num}.html', 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Saved debug HTML to debug_pages/page_{page_num}.html")

# Save individual tender page for debugging
def save_debug_tender(tender_id, content):
    with open(f'debug_pages/tender_{tender_id}.html', 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Saved tender HTML to debug_pages/tender_{tender_id}.html")

# Extract data from HTML content using BeautifulSoup
def extract_tender_data(html_content, tender_url=None, search_term=None):
    data = {
        'Website': 'https://www.evergabe.de',
        'Suchbegriff': search_term if search_term else 'Nicht verfügbar',
        'Ausschreibungstitel': 'Nicht verfügbar',
        'Auftraggeber': 'Nicht verfügbar',
        'Vergabestelle': 'Nicht verfügbar',
        'Link zur Ausschreibung': tender_url if tender_url else 'Nicht verfügbar',
        'Leistungsort': 'Nicht verfügbar',
        'veröffentlicht seit': 'Nicht verfügbar',
        'nächste Frist': 'Nicht verfügbar',
        'Vergabe-ID': 'Nicht verfügbar'
    }
    
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Extract title
        title_elem = soup.select_one('h1, .title, .headline, .tender-title')
        if title_elem:
            data['Ausschreibungstitel'] = title_elem.get_text(strip=True)
        
        # Extract client and awarding authority
        authority_elements = soup.select('.authority, .client, .contracting-authority, .awarding-authority')
        for elem in authority_elements:
            text = elem.get_text(strip=True)
            if 'auftraggeber' in text.lower() and data['Auftraggeber'] == 'Nicht verfügbar':
                parts = text.split(':', 1)
                if len(parts) > 1:
                    data['Auftraggeber'] = parts[1].strip()
            elif 'vergabestelle' in text.lower() and data['Vergabestelle'] == 'Nicht verfügbar':
                parts = text.split(':', 1)
                if len(parts) > 1:
                    data['Vergabestelle'] = parts[1].strip()
        
        # Extract location
        # First, try to find the specific "Ausführungsort:" field as shown in the screenshot
        ausfuehrungsort_found = False
        
        # Look for the specific section with ID "award_procedure_places" which contains the location
        award_places_section = soup.find(id="award_procedure_places")
        if award_places_section:
            # Look for the headline that says "Ausführungsort"
            headlines = award_places_section.find_all("h2", class_="headline")
            for headline in headlines:
                if "Ausführungsort" in headline.get_text():
                    # Location is often in a list item with an icon
                    location_list = award_places_section.find("ul", class_="list-iconized")
                    if location_list:
                        location_items = location_list.find_all("li")
                        for item in location_items:
                            # Get the text excluding the icon
                            location_text = item.get_text(strip=True)
                            if location_text:
                                data['Leistungsort'] = location_text
                                ausfuehrungsort_found = True
                                break
        
        # If not found in the dedicated section, try other methods
        if not ausfuehrungsort_found:
            # Look for elements with the exact label "Ausführungsort:" 
            ausfuehrungsort_labels = soup.find_all(string=lambda text: text and "Ausführungsort:" in text)
            for label in ausfuehrungsort_labels:
                # The location is often in the next sibling or parent's next sibling
                parent = label.parent
                if parent:
                    # Try to find the location text which is often in a nearby element
                    next_element = parent.next_sibling
                    if next_element and next_element.string and next_element.string.strip():
                        data['Leistungsort'] = next_element.string.strip()
                        ausfuehrungsort_found = True
                        break
                    # If not in next sibling, try parent's next sibling
                    parent_next = parent.parent.next_sibling if parent.parent else None
                    if parent_next and parent_next.string and parent_next.string.strip():
                        data['Leistungsort'] = parent_next.string.strip()
                        ausfuehrungsort_found = True
                        break
        
        # If not found with direct label, try to find it in a table or definition list
        if not ausfuehrungsort_found:
            # Look for dt/dd pairs or table rows
            dt_elements = soup.select('dt, th')
            for dt in dt_elements:
                if "Ausführungsort:" in dt.get_text() or "Ausführungsort" in dt.get_text():
                    # Find the corresponding dd or td
                    dd = dt.find_next('dd') if dt.name == 'dt' else dt.find_next('td')
                    if dd and dd.get_text(strip=True):
                        data['Leistungsort'] = dd.get_text(strip=True)
                        ausfuehrungsort_found = True
                        break
        
        # Try another approach - look for elements with class containing location information
        if not ausfuehrungsort_found:
            location_elements = soup.select('.ausfuehrungsort, .ausführungsort, .ort, .location')
            for elem in location_elements:
                if elem.get_text(strip=True):
                    data['Leistungsort'] = elem.get_text(strip=True)
                    ausfuehrungsort_found = True
                    break
        
        # Fallback to the original method if still not found
        if not ausfuehrungsort_found:
            location_elements = soup.select('.location, .place-of-performance, span[title*="ort"]')
            for elem in location_elements:
                text = elem.get_text(strip=True)
                if text and ('leistungsort' in text.lower() or 'ausführungsort' in text.lower()) and data['Leistungsort'] == 'Nicht verfügbar':
                    parts = text.split(':', 1)
                    if len(parts) > 1:
                        location_part = parts[1].strip()
                        # Clean up location if it contains a zip code
                        if ' ' in location_part and any(c.isdigit() for c in location_part):
                            # Try to extract just the city name
                            location = ' '.join(location_part.split()[1:]) if location_part.split()[0].isdigit() else location_part
                        else:
                            location = location_part.strip()
                        data['Leistungsort'] = location
                        break
        
        # If Leistungsort is still not found, try looking for specific elements with Ausführungsort
        if data['Leistungsort'] == 'Nicht verfügbar':
            # Look for elements containing Ausführungsort
            ausfuehrungsort_elements = soup.find_all(lambda tag: tag.name and 'ausführungsort' in tag.get_text().lower())
            for elem in ausfuehrungsort_elements:
                text = elem.get_text(strip=True)
                parts = text.split(':', 1)
                if len(parts) > 1:
                    location_part = parts[1].strip()
                    # Clean up location if it contains a zip code
                    if ' ' in location_part and any(c.isdigit() for c in location_part):
                        # Try to extract just the city name
                        location = ' '.join(location_part.split()[1:]) if location_part.split()[0].isdigit() else location_part
                    else:
                        location = location_part.strip()
                    data['Leistungsort'] = location
                    break
        
        # Extract tender ID (Vergabe-ID)
        vergabe_id_found = False
        
        # Look for the specific heading pattern: "Vergabe-ID <span class="small">(bei evergabe.de)</span>"
        vergabe_id_headings = soup.select('h2.headline:contains("Vergabe-ID")')
        if not vergabe_id_headings:
            # Try with a more general selector
            vergabe_id_headings = soup.find_all(lambda tag: tag.name == 'h2' and 'Vergabe-ID' in tag.get_text())
            
        for heading in vergabe_id_headings:
            # The ID is often in the text right after the heading
            next_text = heading.next_sibling
            if next_text and next_text.strip().isdigit():
                data['Vergabe-ID'] = next_text.strip()
                vergabe_id_found = True
                break
            # Sometimes the ID is within the same element
            heading_text = heading.get_text(strip=True)
            import re
            id_match = re.search(r'Vergabe-ID.*?([0-9]+)', heading_text)
            if id_match:
                data['Vergabe-ID'] = id_match.group(1)
                vergabe_id_found = True
                break
        
        # If not found with the heading approach, try the parent div that contains the heading
        if not vergabe_id_found:
            file_number_divs = soup.select('#file_number_contracting_authority')
            for div in file_number_divs:
                # Look for text content after the heading
                for element in div.find_all(text=True, recursive=True):
                    if element.strip().isdigit():
                        data['Vergabe-ID'] = element.strip()
                        vergabe_id_found = True
                        break
                if vergabe_id_found:
                    break
        
        # If still not found, use the previous approach as fallback
        if not vergabe_id_found:
            tender_id_elements = soup.select('.vergabe-id, .tender-id, .reference-number, .reference, .id')
            for elem in tender_id_elements:
                elem_text = elem.get_text(strip=True)
                if any(term in elem_text.lower() for term in ['vergabe-id', 'vergabeid', 'tender-id', 'id:', 'reference', 'referenznummer']):
                    # Extract the ID
                    id_parts = elem_text.split(':', 1)
                    if len(id_parts) > 1:
                        # Extract just the numeric part
                        import re
                        id_match = re.search(r'\d+', id_parts[1])
                        if id_match:
                            data['Vergabe-ID'] = id_match.group(0)
                            vergabe_id_found = True
                        else:
                            data['Vergabe-ID'] = id_parts[1].strip()
                            vergabe_id_found = True
                    else:
                        # If no colon, check if there's a number pattern
                        import re
                        id_match = re.search(r'\d+', elem_text)
                        if id_match:
                            data['Vergabe-ID'] = id_match.group(0)
                            vergabe_id_found = True
        
        # If Vergabe-ID is still not found, try to extract from URL
        if not vergabe_id_found and tender_url:
            # Try to extract ID from the URL
            import re
            id_match = re.search(r'/(\d+)(?:\?|$)', tender_url)
            if id_match:
                data['Vergabe-ID'] = id_match.group(1)
                vergabe_id_found = True
        
        # Extract Angebotsfrist (due date) - specific to the format shown in the image
        # Look for the Angebotsfrist element which typically contains date and time
        angebotsfrist_elements = soup.select('.angebotsfrist, div:contains("Angebotsfrist"), span:contains("Angebotsfrist")')
        if not angebotsfrist_elements:
            # Try with more specific CSS selectors based on the image
            angebotsfrist_elements = soup.select('.tag-container, .frist-container, .deadline-container')
        
        for elem in angebotsfrist_elements:
            elem_text = elem.get_text(strip=True)
            if 'angebotsfrist' in elem_text.lower() or 'frist' in elem_text.lower():
                # Extract the date and time
                # The format might be like "15.04.2025 09:00 Uhr"
                date_parts = elem_text.split(':', 1)
                if len(date_parts) > 1:
                    # Clean the date string to only include date and time
                    date_str = date_parts[1].strip()
                    # Extract date and time using regex
                    import re
                    date_match = re.search(r'(\d{1,2}\.\d{1,2}\.\d{4})\s*(\d{1,2}:\d{2})', date_str)
                    if date_match:
                        date, time = date_match.groups()
                        data['nächste Frist'] = f"{date} {time}"
                    else:
                        # If regex fails, try simple cleaning
                        date_str = date_str.replace('Uhr', '').strip()
                        data['nächste Frist'] = date_str
                else:
                    # If no colon separator, try to extract date directly using regex
                    import re
                    date_match = re.search(r'(\d{1,2}\.\d{1,2}\.\d{4})\s*(\d{1,2}:\d{2})', elem_text)
                    if date_match:
                        date, time = date_match.groups()
                        data['nächste Frist'] = f"{date} {time}"
                break
        
        # If still not found, try looking for time elements with specific attributes
        if data['nächste Frist'] == 'Nicht verfügbar':
            time_elements = soup.select('time')
            for time_elem in time_elements:
                if time_elem.get('title') and ('frist' in time_elem.get('title').lower() or 'angebot' in time_elem.get('title').lower()):
                    time_text = time_elem.get_text(strip=True) or time_elem.get('datetime')
                    # Clean the time text
                    time_text = time_text.replace('Uhr', '').strip()
                    # Extract date and time using regex
                    import re
                    date_match = re.search(r'(\d{1,2}\.\d{1,2}\.\d{4})\s*(\d{1,2}:\d{2})', time_text)
                    if date_match:
                        date, time = date_match.groups()
                        data['nächste Frist'] = f"{date} {time}"
                    else:
                        data['nächste Frist'] = time_text
                    break
        
        # Try to find the specific layout from the image with days tag and date
        if data['nächste Frist'] == 'Nicht verfügbar':
            # Look for elements with class containing 'tag' and nearby text elements
            tag_elements = soup.select('.tag, .days, .countdown')
            for tag_elem in tag_elements:
                # Check if there's a nearby date element
                parent = tag_elem.parent
                if parent:
                    date_elem = parent.select_one('time, .date, .deadline-date')
                    if date_elem:
                        date_text = date_elem.get_text(strip=True)
                        if date_text:
                            # Clean the date text
                            date_text = date_text.replace('Uhr', '').strip()
                            # Extract date and time using regex
                            import re
                            date_match = re.search(r'(\d{1,2}\.\d{1,2}\.\d{4})\s*(\d{1,2}:\d{2})', date_text)
                            if date_match:
                                date, time = date_match.groups()
                                data['nächste Frist'] = f"{date} {time}"
                            else:
                                data['nächste Frist'] = date_text
                            break
        
        # Extract dates - improved approach
        # 1. Look for dt/dd pairs in the definition list
        dl_rows = soup.select('dl.row.dl-row')
        for dl in dl_rows:
            dt_elements = dl.select('dt')
            dd_elements = dl.select('dd')
            
            # Match dt with corresponding dd
            for i in range(min(len(dt_elements), len(dd_elements))):
                dt_text = dt_elements[i].get_text(strip=True).lower()
                dd_text = dd_elements[i].get_text(strip=True)
                
                # Extract deadline (Frist)
                if any(term in dt_text for term in ['frist', 'einreichung', 'abgabe', 'angebotsfrist', 'teilnahmefrist']) and data['nächste Frist'] == 'Nicht verfügbar':
                    if dd_text and dd_text != 'Nach Freischalten sichtbar':
                        data['nächste Frist'] = dd_text
                
                # Extract publication date (if available)
                if any(term in dt_text for term in ['veröffentlicht', 'publiziert', 'datum', 'bekanntmachung', 'bekannt']) and data['veröffentlicht seit'] == 'Nicht verfügbar':
                    if dd_text and dd_text != 'Nach Freischalten sichtbar':
                        data['veröffentlicht seit'] = dd_text
        
        # 2. Look for publication date in meta tags or specific elements
        if data['veröffentlicht seit'] == 'Nicht verfügbar':
            # Try to find meta tags with publication date
            meta_tags = soup.select('meta[property="article:published_time"], meta[name="date"], meta[name="publication-date"]')
            for meta in meta_tags:
                content = meta.get('content')
                if content:
                    data['veröffentlicht seit'] = content
                    break
            
            # Try to find span elements with date information
            date_spans = soup.select('span.date, span.published-date, span[title*="datum"], span[title*="veröffentlicht"]')
            for span in date_spans:
                span_text = span.get_text(strip=True)
                if span_text and span_text != 'Nach Freischalten sichtbar':
                    data['veröffentlicht seit'] = span_text
                    break
        
        # 3. Look for time elements with datetime attributes
        if data['veröffentlicht seit'] == 'Nicht verfügbar' or data['nächste Frist'] == 'Nicht verfügbar':
            time_elements = soup.select('time')
            for time_elem in time_elements:
                time_text = time_elem.get_text(strip=True).lower()
                datetime_attr = time_elem.get('datetime')
                title_attr = time_elem.get('title', '')
                
                if datetime_attr:
                    # Check element text, title, and parent elements for clues
                    parent_text = ''
                    if time_elem.parent:
                        parent_text = time_elem.parent.get_text(strip=True).lower()
                    
                    # Publication date indicators
                    if (any(term in time_text for term in ['veröffentlicht', 'publiziert', 'bekannt']) or 
                        any(term in title_attr.lower() for term in ['veröffentlicht', 'publiziert', 'bekannt']) or
                        any(term in parent_text for term in ['veröffentlicht', 'publiziert', 'bekannt', 'datum'])):
                        data['veröffentlicht seit'] = time_elem.get_text(strip=True) or datetime_attr
                    
                    # Deadline indicators
                    elif (any(term in time_text for term in ['frist', 'einreichung', 'abgabe', 'angebotsfrist']) or
                          any(term in title_attr.lower() for term in ['frist', 'einreichung', 'abgabe', 'angebotsfrist']) or
                          any(term in parent_text for term in ['frist', 'einreichung', 'abgabe', 'angebotsfrist'])):
                        data['nächste Frist'] = time_elem.get_text(strip=True) or datetime_attr
        
        # 4. Look for date spans or divs (as backup)
        if data['veröffentlicht seit'] == 'Nicht verfügbar' or data['nächste Frist'] == 'Nicht verfügbar':
            date_elements = soup.select('.date, .dates, .deadline, .published-date, span[title*="datum"], div[class*="date"], div[class*="published"]')
            for date_elem in date_elements:
                date_text = date_elem.get_text(strip=True).lower()
                
                if any(term in date_text for term in ['veröffentlicht', 'publiziert', 'bekannt', 'datum']) and data['veröffentlicht seit'] == 'Nicht verfügbar':
                    # Try to extract the date from the text
                    date_parts = date_text.split(':', 1)
                    if len(date_parts) > 1:
                        data['veröffentlicht seit'] = date_parts[1].strip()
                    else:
                        # If no colon, check if there's a date pattern in the text
                        data['veröffentlicht seit'] = date_text
                
                if any(term in date_text for term in ['frist', 'einreichung', 'abgabe', 'angebotsfrist']) and data['nächste Frist'] == 'Nicht verfügbar':
                    # Try to extract the date from the text
                    date_parts = date_text.split(':', 1)
                    if len(date_parts) > 1:
                        data['nächste Frist'] = date_parts[1].strip()
                    else:
                        # If no colon, check if there's a date pattern in the text
                        data['nächste Frist'] = date_text
        
        # 5. If we still don't have a publication date, try a more aggressive approach
        if data['veröffentlicht seit'] == 'Nicht verfügbar':
            # Look for any text that might contain date information
            all_text = soup.get_text(strip=True).lower()
            date_indicators = ['veröffentlicht am', 'veröffentlicht:', 'publiziert am', 'publiziert:', 'bekanntmachung vom']
            
            for indicator in date_indicators:
                if indicator in all_text:
                    start_idx = all_text.find(indicator) + len(indicator)
                    # Try to extract the next 20 characters which might contain the date
                    potential_date = all_text[start_idx:start_idx+20].strip()
                    # Clean up the potential date
                    potential_date = potential_date.split('\n')[0].strip()
                    if potential_date:
                        data['veröffentlicht seit'] = potential_date
                        break
    
    except Exception as e:
        print(f"Fehler bei der Datenextraktion: {str(e)}")
    
    return data

# Extract data from a tender item on the search results page
async def extract_tender_from_search_page(tender, crawler, crawler_config, search_term):
    try:
        # Extract basic information from search page
        title_elem = tender.select_one('h3 a, .title a, .headline a')
        if not title_elem:
            return None
        
        title = title_elem.get_text(strip=True)
        link = title_elem.get('href')
        if not link.startswith('http'):
            link = 'https://www.evergabe.de' + link
        
        # Initialize data with basic info
        data = {
            'Website': 'https://www.evergabe.de',
            'Suchbegriff': search_term,
            'Ausschreibungstitel': title,
            'Auftraggeber': 'Nicht verfügbar',
            'Vergabestelle': 'Nicht verfügbar',
            'Link zur Ausschreibung': link,
            'Leistungsort': 'Nicht verfügbar',
            'veröffentlicht seit': 'Nicht verfügbar',
            'nächste Frist': 'Nicht verfügbar',
            'Vergabe-ID': 'Nicht verfügbar'
        }
        
        # Extract deadline from search page if available
        deadline_elem = tender.select_one('.deadline, .frist, time[title*="frist"]')
        if deadline_elem:
            deadline = deadline_elem.get_text(strip=True)
            if deadline and deadline != 'Nach Freischalten sichtbar':
                data['nächste Frist'] = deadline
        
        # Visit the detail page to get more information
        print(f"Visiting tender detail page: {link}")
        detail_result = await crawler.arun(url=link, config=crawler_config)
        
        # Save detail page for debugging
        tender_id = link.split('/')[-1].split('?')[0]
        save_debug_tender(tender_id, detail_result.html)
        
        # Extract detailed information
        detail_data = extract_tender_data(detail_result.html, link, search_term)
        
        # Update data with details from the detail page
        # Only update if the detail page has better information
        for key, value in detail_data.items():
            if value != 'Nicht verfügbar' or data[key] == 'Nicht verfügbar':
                data[key] = value
        
        return data
    
    except Exception as e:
        print(f"Fehler bei der Extraktion des Tenders: {str(e)}")
        return None

# Hauptfunktion
async def scrape_evergabe(search_term='strahlenschutz', days=7):
    # Berechne das Datum vor 7 Tagen
    date_from = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    date_to = datetime.now().strftime('%Y-%m-%d')
    
    # URL mit Suchbegriff und Datumsfilter
    url = f"https://www.evergabe.de/auftraege/auftrag-suchen?search[query]={search_term}&search[dateFrom]={date_from}&search[dateTo]={date_to}&search[orderBy]=date&search[orderDirection]=desc&page=1&per_page=100"
    
    print(f"Suche nach Ausschreibungen mit dem Begriff '{search_term}' der letzten {days} Tage...")
    
    # Browser-Konfiguration
    browser_config = BrowserConfig(headless=True)  # Set headless=True for production
    
    # Crawler-Konfiguration
    crawler_config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,  # Don't use cache
        wait_until="networkidle",  # Wait until network is idle
        page_timeout=60000,  # 60 seconds timeout
        js_only=False,  # Process both JavaScript and HTML
        verbose=True  # Enable verbose logging
    )
    
    # Initialisiere den Crawler
    async with AsyncWebCrawler(config=browser_config) as crawler:
        print(f"Navigiere zu: {url}")
        
        # Crawle die Seite
        result = await crawler.arun(url=url, config=crawler_config)
        
        # Speichere die HTML-Seite für Debugging
        html_content = result.html
        save_debug_page(1, html_content)
        
        # Parse die HTML mit BeautifulSoup
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Finde alle Ausschreibungen
        tenders = soup.select('#result_list > ul > li')
        if not tenders:
            # Alternative Selektoren versuchen
            tenders = soup.select('.result-list > .result-item, .tender-list > .tender-item')
        
        print(f"Gefundene Ausschreibungen mit Selector '#result_list > ul > li': {len(tenders)}")
        
        # Extrahiere Daten aus jeder Ausschreibung
        results = []
        print(f"Verarbeite {len(tenders)} Ausschreibungen...")
        
        for i, tender in enumerate(tenders):
            print(f"Verarbeite Ausschreibung {i+1} von {len(tenders)}...")
            
            # Extrahiere Daten und füge sie zu den Ergebnissen hinzu
            data = await extract_tender_from_search_page(tender, crawler, crawler_config, search_term)
            if data:
                results.append(data)
            
            # Kurze Pause, um den Server nicht zu überlasten
            await asyncio.sleep(random.uniform(1.0, 2.0))
        
        # Erstelle einen DataFrame aus den Ergebnissen
        df = pd.DataFrame(results)
        
        # Überprüfe, ob Ergebnisse gefunden wurden
        if df.empty:
            print(f"Keine Ausschreibungen für '{search_term}' in den letzten {days} Tagen gefunden.")
        else:
            # Generate timestamp for the filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_filename = f"vergabe_results_{timestamp}.xlsx"

            # Save to Excel file with clickable links
            print(f"Saving {len(results)} results to {output_filename}")
            
            # Create Excel writer with openpyxl engine
            with pd.ExcelWriter(output_filename, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='Tender Results')
                
                # Access the workbook and the worksheet
                workbook = writer.book
                worksheet = writer.sheets['Tender Results']
                
                # Find the column index for the link column
                link_col_idx = None
                for idx, col in enumerate(df.columns):
                    if col == 'Link zur Ausschreibung':
                        link_col_idx = idx + 1  # +1 because Excel is 1-indexed
                        break
                
                # If link column exists, make the links clickable
                if link_col_idx is not None:
                    for row_idx, link in enumerate(df['Link zur Ausschreibung']):
                        if link != 'Nicht verfügbar':
                            cell = worksheet.cell(row=row_idx + 2, column=link_col_idx)  # +2 for header and 1-indexing
                            cell.hyperlink = link
                            cell.style = 'Hyperlink'

            print(f"Results saved to {output_filename}")
            
            # Ergebnisse anzeigen
            print("\nGefundene Ausschreibungen:")
            print(df)
        
        return df

# Hauptprogramm
async def main():
    # Führe das Scraping aus
    await scrape_evergabe(search_term='strahlenschutz', days=7)

# Führe das Hauptprogramm aus
if __name__ == "__main__":
    asyncio.run(main())