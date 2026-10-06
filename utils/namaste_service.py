import os
import requests
import csv
import logging
from pathlib import Path
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

#: The shipped code table, resolved against this file rather than the working
#: directory. A bare 'namaste_codes.csv' silently resolved to nothing whenever the
#: app was started from anywhere other than the repo root -- which does not raise,
#: it just returns zero NAMASTE results and leaves the search page half empty.
DEFAULT_CSV = Path(__file__).resolve().parent.parent / 'namaste_codes.csv'


def resolve_csv(csv_file):
    """Find the code table, preferring an explicitly supplied path.

    Falls back to the copy shipped beside the project so the service works no
    matter which directory Flask was launched from.
    """
    if not csv_file:
        return DEFAULT_CSV
    given = Path(csv_file)
    if given.is_absolute() or given.exists():
        return given
    if DEFAULT_CSV.exists():
        return DEFAULT_CSV
    return given


class NAMASTEService:
    def __init__(self, csv_file=None):
        self.api_key = os.getenv('NAMASTE_API_KEY')
        self.api_base_url = 'https://namaste-ayush.gov.in/api'
        self.csv_file = resolve_csv(csv_file)
        self.csv_data = self._load_csv_data()
        if not self.csv_data:
            logger.warning('No NAMASTE rows loaded from %s', self.csv_file)

    def _load_csv_data(self) -> List[Dict]:
        """Load CSV data as fallback"""
        if not self.csv_file.exists():
            return []
        
        data = []
        try:
            with open(self.csv_file, 'r', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                for row in reader:
                    data.append(row)
        except Exception as e:
            logger.error(f"Error loading CSV data: {e}")
        return data
    
    def _search_api(self, query: str) -> Optional[List[Dict]]:
        """Search using official NAMASTE API"""
        if not self.api_key:
            return None
            
        try:
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            }
            
            params = {
                'q': query,
                'limit': 50
            }
            
            response = requests.get(
                f'{self.api_base_url}/codes/search',
                headers=headers,
                params=params,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                return self._format_api_results(data)
            else:
                logger.warning(f"NAMASTE API returned status {response.status_code}")
                return None
                
        except requests.exceptions.RequestException as e:
            logger.error(f"NAMASTE API request failed: {e}")
            return None
        except Exception as e:
            logger.error(f"NAMASTE API error: {e}")
            return None
    
    def _format_api_results(self, api_data) -> List[Dict]:
        """Format API results to match expected structure"""
        results = []
        
        # Handle different possible API response structures
        codes = api_data.get('codes', api_data.get('data', []))
        if isinstance(codes, dict):
            codes = [codes]
            
        for item in codes:
            results.append({
                'code': item.get('code', ''),
                'name': item.get('name', item.get('title', '')),
                'description': item.get('description', item.get('desc', '')),
                'system': item.get('system', item.get('category', 'NAMASTE'))
            })
            
        return results
    
    def _search_csv(self, query: str) -> List[Dict]:
        """Search CSV data as fallback"""
        query_lower = query.lower()
        results = []
        
        for row in self.csv_data:
            if (query_lower in row.get('code', '').lower() or 
                query_lower in row.get('name', '').lower() or
                query_lower in row.get('description', '').lower()):
                results.append({
                    'code': row.get('code', ''),
                    'name': row.get('name', ''),
                    'description': row.get('description', ''),
                    'system': row.get('system', 'NAMASTE')
                })
        
        return results
    
    def get_namaste_codes(self, query: str) -> Dict:
        """
        Main function to get NAMASTE codes with API + CSV fallback
        Returns dict with results and source information
        """
        if not query or len(query.strip()) < 2:
            return {
                'results': [],
                'source': 'none',
                'message': 'Query too short'
            }
        
        query = query.strip()
        
        # Try API first if available
        if self.api_key:
            api_results = self._search_api(query)
            if api_results is not None:
                return {
                    'results': api_results,
                    'source': 'api',
                    'message': 'Results from official NAMASTE API'
                }
        
        # Fallback to CSV
        csv_results = self._search_csv(query)
        source_msg = 'CSV fallback (demo data)' if self.api_key else 'CSV data (no API key configured)'
        
        return {
            'results': csv_results,
            'source': 'csv',
            'message': source_msg
        }
    
    def search(self, query: str) -> List[Dict]:
        """
        Backward compatibility method - returns just the results list
        """
        response = self.get_namaste_codes(query)
        return response.get('results', [])

# Global instance for backward compatibility
_namaste_service = None

def get_namaste_service(csv_file=None) -> NAMASTEService:
    """Get or create global NAMASTE service instance"""
    global _namaste_service
    if _namaste_service is None:
        _namaste_service = NAMASTEService(csv_file)
    return _namaste_service

def get_namaste_codes(query: str) -> Dict:
    """Convenience function to get NAMASTE codes"""
    service = get_namaste_service()
    return service.get_namaste_codes(query)