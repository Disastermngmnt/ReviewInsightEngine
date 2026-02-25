import json
import urllib.request
import urllib.error
from datetime import datetime
import dateutil.parser
import re
from utils.logger import setup_logger

logger = setup_logger(__name__)

class AppStoreConnector:
    """
    Fetches public App Store reviews via the iTunes RSS feed.
    Max 500 reviews (10 pages of 50).
    """
    
    BASE_URL = "https://itunes.apple.com/us/rss/customerreviews/page={page}/id={app_id}/sortby=mostrecent/json"
    
    @staticmethod
    def fetch_reviews(app_id: str, max_pages: int = 10) -> dict:
        """
        Fetches up to `max_pages` * 50 reviews from the App Store.
        Returns a dict conforming to the Dispatch file parsing standard.
        """
        # Clean app_id in case user provides full URL
        match = re.search(r'id(\d+)', app_id)
        if match:
            app_id = match.group(1)
        elif not app_id.isdigit():
             raise ValueError(f"Invalid App Store ID: {app_id}. Must be numeric (e.g., 389801252 for Instagram)")
        
        all_reviews = []
        
        for page in range(1, max_pages + 1):
            url = AppStoreConnector.BASE_URL.format(page=page, app_id=app_id)
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=10.0) as response:
                    data = json.loads(response.read().decode('utf-8'))
                
                entries = data.get("feed", {}).get("entry", [])
                if not entries:
                    logger.info(f"App Store API returned no more entries at page {page}")
                    break
                
                # Apple RSS quirk: The first entry on page 1 is often the app metadata itself, not a review.
                # A review has an author, rating, etc. We filter metadata entries.
                valid_entries = [e for e in entries if getattr(e.get("author", {}).get("name", {}), "get", lambda x: None)("label")]
                
                if page == 1 and valid_entries and entries[0] not in valid_entries:
                     logger.debug("Skipped metadata entry on page 1")
                     
                all_reviews.extend(valid_entries)
                
                if len(entries) < 50:
                    break # End of pagination
                    
            except urllib.error.HTTPError as e:
                # If page > 1, we just return what we have
                if page == 1:
                    logger.error(f"HTTPError fetching App Store data: {e.code} - {e.reason}")
                    raise ValueError(f"Failed to fetch App Store data for ID {app_id}: {e.reason}")
                break
            except Exception as e:
                if page == 1:
                     logger.error(f"Error fetching App Store data: {str(e)}")
                     raise ValueError(f"Connection failed for App Store ID {app_id}: {str(e)}")
                break

        if not all_reviews:
            raise ValueError(f"No reviews found for App Store ID {app_id}. Check if the ID is correct and the app has reviews in the US store.")

        # Format into the standard tabular structure expected by core/analyzer.py
        columns = ["Review Title", "Review Text", "Rating", "Reviewed at", "Author", "Version"]
        data_rows = []
        
        for entry in all_reviews:
            try:
                title = entry.get("title", {}).get("label", "")
                content = entry.get("content", {}).get("label", "")
                rating_str = entry.get("im:rating", {}).get("label", "0")
                version = entry.get("im:version", {}).get("label", "")
                author = entry.get("author", {}).get("name", {}).get("label", "Anonymous")
                
                raw_date_str = entry.get("updated", {}).get("label", "")
                dt_str = raw_date_str
                try:
                    if raw_date_str:
                        dt = dateutil.parser.parse(raw_date_str)
                        dt_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    pass
                    
                full_text = f"{title}\n{content}".strip()
                
                data_rows.append([
                    title,
                    full_text,
                    rating_str,
                    dt_str,
                    author,
                    version
                ])
            except Exception as e:
                logger.warning(f"Failed to parse a review entry: {str(e)}")
                continue
            
        return {
            "columns": columns,
            "data": data_rows,
            "total_fetched": len(data_rows)
        }
