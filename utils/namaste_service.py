import os
import requests
import csv
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

class NAMASTEService:
    def __init__(self, csv_file='namaste_codes.csv'):
        self.api_key = os.getenv('NAMASTE_API_KEY')
        self.api_base_url = 'https://namaste-ayush.gov.in/api'
        self.csv_file = csv_file
        self.csv_data = self._load_csv_data()
        
    def _load_csv_data(self) -> List[Dict]:
        """Load CSV data as fallback"""
        if not os.path.exists(self.csv_file):
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

def get_namaste_service(csv_file='namaste_codes.csv') -> NAMASTEService:
    """Get or create global NAMASTE service instance"""
    global _namaste_service
    if _namaste_service is None:
        _namaste_service = NAMASTEService(csv_file)
    return _namaste_service

def get_namaste_codes(query: str) -> Dict:
    """Convenience function to get NAMASTE codes"""
    service = get_namaste_service()
    return service.get_namaste_codes(query)