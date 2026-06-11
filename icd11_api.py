import requests
import json
from datetime import datetime, timedelta

class WHO_ICD_API:
    def __init__(self, client_id=None, client_secret=None):
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_url = "https://icdaccessmanagement.who.int/connect/token"
        self.base_url = "https://id.who.int/icd"
        self.access_token = None
        self.token_expires = None
    
    def get_access_token(self):
        """Get OAuth2 access token from WHO"""
        if not self.client_id or not self.client_secret:
            return None
            
        if self.access_token and self.token_expires and datetime.now() < self.token_expires:
            return self.access_token
        
        payload = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'scope': 'icdapi_access',
            'grant_type': 'client_credentials'
        }
        
        try:
            response = requests.post(self.token_url, data=payload, timeout=10)
            if response.status_code == 200:
                token_data = response.json()
                self.access_token = token_data['access_token']
                self.token_expires = datetime.now() + timedelta(seconds=token_data['expires_in'] - 60)
                return self.access_token
        except Exception:
            pass
        
        return None
    
    def search_icd11(self, keyword):
        """Search ICD-11 using WHO API"""
        if not keyword or len(keyword.strip()) < 2:
            return []
        
        token = self.get_access_token()
        if not token:
            return []
        
        headers = {
            'Authorization': f'Bearer {token}',
            'Accept': 'application/json',
            'API-Version': 'v2',
            'Accept-Language': 'en'
        }
        
        # Search in ICD-11 MMS
        search_url = f"{self.base_url}/release/11/2022-02/mms/search"
        params = {
            'q': keyword.strip(),
            'subtreeFilterUsesFoundationDescendants': 'false',
            'includeKeywordResult': 'true',
            'useFlexisearch': 'false',
            'flatResults': 'true'
        }
        
        try:
            response = requests.get(search_url, headers=headers, params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                results = []
                
                for entity in data.get('destinationEntities', [])[:10]:
                    # Extract code
                    code = entity.get('theCode', '')
                    
                    # Extract title
                    title = entity.get('title', {})
                    if isinstance(title, dict):
                        name = title.get('@value', '')
                    else:
                        name = str(title) if title else ''
                    
                    if code and name:
                        results.append({
                            'code': code,
                            'name': name,
                            'category': 'ICD-11'
                        })
                
                return results
        
        except Exception:
            pass
        
        return []

# Global instance - will be configured with your credentials
icd_api = WHO_ICD_API()

def configure_icd_api(client_id, client_secret):
    """Configure WHO ICD API with your credentials"""
    global icd_api
    icd_api = WHO_ICD_API(client_id, client_secret)

def search_icd11(keyword):
    """Search ICD-11 codes from WHO API only"""
    return icd_api.search_icd11(keyword)