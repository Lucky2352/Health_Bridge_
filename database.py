import sqlite3
from datetime import datetime

class Database:
    def __init__(self, db_file='diagnosis.db'):
        self.db_file = db_file
        self.init_db()
    
    def init_db(self):
        conn = sqlite3.connect(self.db_file)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS diagnosis_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id TEXT NOT NULL,
                symptom TEXT NOT NULL,
                namaste_code TEXT,
                icd11_code TEXT,
                patient_abha_id TEXT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Add ABHA ID column if it doesn't exist (for existing databases)
        try:
            conn.execute('ALTER TABLE diagnosis_records ADD COLUMN patient_abha_id TEXT')
        except sqlite3.OperationalError:
            pass  # Column already exists
        
        # Create search tracking table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS search_operations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                search_query TEXT NOT NULL,
                operation_type TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def add_diagnosis(self, patient_id, symptom, namaste_code=None, icd11_code=None, abha_id=None):
        conn = sqlite3.connect(self.db_file)
        cursor = conn.execute('''
            INSERT INTO diagnosis_records (patient_id, symptom, namaste_code, icd11_code, patient_abha_id)
            VALUES (?, ?, ?, ?, ?)
        ''', (patient_id, symptom, namaste_code, icd11_code, abha_id))
        record_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return record_id
    
    def get_patient_history(self, patient_id):
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute('''
            SELECT * FROM diagnosis_records 
            WHERE UPPER(patient_id) = UPPER(?) 
            ORDER BY timestamp DESC
        ''', (patient_id,))
        records = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return records
    
    def log_search_operation(self, user_id, query, operation_type):
        conn = sqlite3.connect(self.db_file)
        conn.execute('''
            INSERT INTO search_operations (user_id, search_query, operation_type)
            VALUES (?, ?, ?)
        ''', (user_id, query, operation_type))
        conn.commit()
        conn.close()
    
    def get_user_search_count(self, user_id):
        conn = sqlite3.connect(self.db_file)
        cursor = conn.execute('''
            SELECT COUNT(*) FROM search_operations WHERE user_id = ?
        ''', (user_id,))
        count = cursor.fetchone()[0]
        conn.close()
        return count