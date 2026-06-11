import sqlite3
from datetime import datetime
import json

class PatientDatabase:
    def __init__(self, db_file='patients.db'):
        self.db_file = db_file
        self.init_database()
    
    def init_database(self):
        conn = sqlite3.connect(self.db_file)
        
        # Patients table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS patients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                age INTEGER,
                gender TEXT,
                contact TEXT,
                email TEXT,
                address TEXT,
                medical_history TEXT,
                allergies TEXT,
                abha_id TEXT UNIQUE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                created_by TEXT
            )
        ''')
        
        # Add ABHA ID column if it doesn't exist (for existing databases)
        try:
            conn.execute('ALTER TABLE patients ADD COLUMN abha_id TEXT UNIQUE')
        except sqlite3.OperationalError:
            pass  # Column already exists
        
        # Patient diagnoses table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS patient_diagnoses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id TEXT,
                diagnosis_date DATE,
                symptoms TEXT,
                namaste_code TEXT,
                namaste_name TEXT,
                icd11_code TEXT,
                icd11_name TEXT,
                notes TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                created_by TEXT,
                FOREIGN KEY (patient_id) REFERENCES patients (patient_id)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def create_patient(self, data, created_by):
        conn = sqlite3.connect(self.db_file)
        
        try:
            # Generate patient ID
            cursor = conn.execute('SELECT COUNT(*) FROM patients')
            count = cursor.fetchone()[0]
            patient_id = f"P{str(count + 1).zfill(4)}"
            
            # Validate required fields
            if not data.get('name') or not data.get('contact'):
                raise ValueError('Name and contact are required fields')
            
            cursor = conn.execute('''
                INSERT INTO patients (patient_id, name, age, gender, contact, email, address, medical_history, allergies, abha_id, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (patient_id, data['name'], data['age'], data['gender'], data['contact'], 
                  data.get('email', ''), data.get('address', ''), data.get('medical_history', ''), 
                  data.get('allergies', ''), data.get('abha_id', ''), created_by))
            
            conn.commit()
            return patient_id
            
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def get_patient(self, patient_id):
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute('SELECT * FROM patients WHERE UPPER(patient_id) = UPPER(?)', (patient_id,))
        patient = cursor.fetchone()
        conn.close()
        return dict(patient) if patient else None
    
    def update_patient(self, patient_id, data):
        conn = sqlite3.connect(self.db_file)
        conn.execute('''
            UPDATE patients 
            SET name=?, age=?, gender=?, contact=?, email=?, address=?, medical_history=?, allergies=?, abha_id=?, updated_at=CURRENT_TIMESTAMP
            WHERE patient_id=?
        ''', (data['name'], data['age'], data['gender'], data['contact'], 
              data.get('email', ''), data.get('address', ''), data.get('medical_history', ''), 
              data.get('allergies', ''), data.get('abha_id', ''), patient_id))
        conn.commit()
        conn.close()
    
    def delete_patient(self, patient_id):
        conn = sqlite3.connect(self.db_file)
        conn.execute('DELETE FROM patients WHERE patient_id = ?', (patient_id,))
        conn.execute('DELETE FROM patient_diagnoses WHERE patient_id = ?', (patient_id,))
        conn.commit()
        conn.close()
    
    def search_patients(self, query='', filters=None):
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        
        sql = 'SELECT * FROM patients WHERE 1=1'
        params = []
        
        if query:
            sql += ' AND (UPPER(name) LIKE UPPER(?) OR UPPER(patient_id) LIKE UPPER(?) OR UPPER(contact) LIKE UPPER(?) OR UPPER(abha_id) LIKE UPPER(?))'
            params.extend([f'%{query}%', f'%{query}%', f'%{query}%', f'%{query}%'])
        
        if filters:
            if filters.get('gender'):
                sql += ' AND gender = ?'
                params.append(filters['gender'])
            if filters.get('age_min'):
                sql += ' AND age >= ?'
                params.append(filters['age_min'])
            if filters.get('age_max'):
                sql += ' AND age <= ?'
                params.append(filters['age_max'])
        
        sql += ' ORDER BY created_at DESC'
        
        cursor = conn.execute(sql, params)
        patients = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return patients
    
    def add_diagnosis(self, patient_id, diagnosis_data, created_by):
        conn = sqlite3.connect(self.db_file)
        
        # Get patient's ABHA ID
        patient = self.get_patient(patient_id)
        patient_abha_id = patient.get('abha_id', '') if patient else ''
        
        # Add ABHA ID column if it doesn't exist
        try:
            conn.execute('ALTER TABLE patient_diagnoses ADD COLUMN patient_abha_id TEXT')
        except sqlite3.OperationalError:
            pass  # Column already exists
        
        conn.execute('''
            INSERT INTO patient_diagnoses (patient_id, diagnosis_date, symptoms, namaste_code, namaste_name, icd11_code, icd11_name, notes, patient_abha_id, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (patient_id, diagnosis_data.get('date', datetime.now().date()), 
              diagnosis_data['symptoms'], diagnosis_data.get('namaste_code'), 
              diagnosis_data.get('namaste_name'), diagnosis_data.get('icd11_code'), 
              diagnosis_data.get('icd11_name'), diagnosis_data.get('notes', ''), patient_abha_id, created_by))
        conn.commit()
        conn.close()
    
    def get_patient_diagnoses(self, patient_id):
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute('''
            SELECT * FROM patient_diagnoses 
            WHERE UPPER(patient_id) = UPPER(?) 
            ORDER BY diagnosis_date DESC, created_at DESC
        ''', (patient_id,))
        diagnoses = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return diagnoses
    
    def get_all_patients(self):
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute('SELECT * FROM patients ORDER BY created_at DESC')
        patients = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return patients
    
    def get_all_diagnoses(self):
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute('SELECT * FROM patient_diagnoses ORDER BY created_at DESC')
        diagnoses = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return diagnoses