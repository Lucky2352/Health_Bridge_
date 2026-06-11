import csv
import os

class CSVService:
    def __init__(self, csv_file='namaste_codes.csv'):
        self.csv_file = csv_file
        self.data = self._load_data()
    
    def _load_data(self):
        if not os.path.exists(self.csv_file):
            return []
        
        data = []
        with open(self.csv_file, 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for row in reader:
                data.append(row)
        return data
    
    def search(self, keyword):
        keyword_lower = keyword.lower()
        results = []
        
        for row in self.data:
            if (keyword_lower in row['code'].lower() or 
                keyword_lower in row['name'].lower()):
                results.append({
                    'code': row['code'],
                    'name': row['name'],
                    'description': row['description'],
                    'system': row['system']
                })
        
        return results