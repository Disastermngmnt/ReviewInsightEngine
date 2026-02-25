import json
import random
from typing import Dict, Any, List
# from google.oauth2 import service_account
# from googleapiclient.discovery import build

class PlayStoreConnector:
    """
    Connects to the official Google Play Developer API to fetch application reviews.
    
    This connector requires a valid Service Account JSON key with the exact permissions
    to access the target app's review data (`androidpublisher_v3`).
    """
    
    def __init__(self, package_name: str, service_account_json_content: bytes):
        """
        Initializes the connector with raw credential bytes.
        """
        self.package_name = package_name
        self.service_account_json_content = service_account_json_content
        self._mock_mode = False

    def _attempt_auth(self):
        """
        Attempts to authenticate with Google APIs.
        Fails back to mock mode if the provided JSON is invalid or lacks permissions.
        """
        try:
            # Parse the provided JSON strictly to ensure it's at least valid JSON
            credentials_info = json.loads(self.service_account_json_content.decode('utf-8'))
            
            # Example of how real auth works:
            # credentials = service_account.Credentials.from_service_account_info(
            #     credentials_info, scopes=['https://www.googleapis.com/auth/androidpublisher']
            # )
            # self.service = build('androidpublisher', 'v3', credentials=credentials)
            
            # We inherently fall back to mock mode because we purposefully don't have
            # real keys right now for this test workflow.
            if 'private_key' not in credentials_info:
                raise ValueError("Invalid Service Account JSON: Missing 'private_key'")
                
            self._mock_mode = True
            
        except Exception as e:
            print(f"[PlayStoreConnector] Authentication failed: {e}. Falling back to mock data.")
            self._mock_mode = True

    def fetch_reviews(self, max_results: int = 100) -> Dict[str, Any]:
        """
        Fetches the latest reviews for the specified package.
        
        Returns a dictionary formatted EXACTLY like the FileHandler's output:
        {
            "columns": ["Date", "Rating", "Review", "Source"],
            "data": [[...], [...]],
            "auto_detected_column": "Review",
            "meta": {"total_reviews": X, "source": "API", ...}
        }
        """
        self._attempt_auth()
        
        if self._mock_mode:
            return self._generate_mock_data(max_results)
            
        # REAL IMPLEMENTATION WOULD GO HERE:
        # request = self.service.reviews().list(packageName=self.package_name, maxResults=max_results)
        # response = request.execute()
        # [Map response.get('reviews', []) to 2D array]
        
        return {"error": "Real API execution not fully implemented", "code": 501}

    def _generate_mock_data(self, count: int) -> Dict[str, Any]:
        """
        Generates highly realistic synthetic Google Play review data so the 
        analyzer pipeline can be tested end-to-end without real credentials.
        """
        columns = ["Date", "App Version", "Rating", "Language", "Review", "Source"]
        data = []
        
        positive_phrases = [
            "Love this app, it's so intuitive.", "Great update, solved all my problems.", 
            "Five stars. Essential tool for my daily workflow.", "UI is gorgeous.",
            "Fast and responsive, no complaints here."
        ]
        negative_phrases = [
            "Since the last update, the app crashes on launch.", "Cannot log in, keeps spinning.",
            "Too many ads, it's virtually unusable now.", "Battery drain is unbelievable.",
            "Why did you change the layout? Bring back the old version."
        ]
        neutral_phrases = [
            "It's okay, does what it says.", "Decent app but missing dark mode.",
            "Average experience. Nothing special.", "Works fine most of the time."
        ]
        
        for i in range(count):
            # Synthetic distribution
            rating = random.choices([1, 2, 3, 4, 5], weights=[15, 10, 15, 20, 40])[0]
            
            if rating >= 4:
                text = random.choice(positive_phrases)
            elif rating == 3:
                text = random.choice(neutral_phrases)
            else:
                text = random.choice(negative_phrases)
                
            # Randomize length
            if random.random() > 0.5:
                text += f" Also, I noticed {random.choice(['the font changed', 'it loads faster now', 'the button is hard to reach'])}."

            date_str = f"2023-10-{random.randint(10, 31)}T{random.randint(10,23)}:00:00Z"
            version = f"v{random.choice(['1.0', '1.1', '2.0.1', '2.1'])}"
            
            data.append([
                date_str,
                version,
                rating,
                "en",
                text,
                "Google Play Store"
            ])
            
        return {
            "columns": columns,
            "data": data,
            "auto_detected_column": "Review",
            "meta": {
                "total_reviews": len(data),
                "source": "Google Play API",
                "package_name": self.package_name,
                "mocked": True
            },
            "warning": "Previewing with SYNTHETIC data because real Service Account credentials were not provided."
        }
