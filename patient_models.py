import db
from datetime import datetime

class PatientDatabase:
    def __init__(self, db_file='patients.db'):
        self.db_file = db_file
        self.init_database()
    
    def init_database(self):
        """Create the schema, once per process. See db.ensure_once."""
        db.ensure_once(f'PatientDatabase:{self.db_file}', self._create_schema)

    def _create_schema(self):
        conn = db.connect(self.db_file)
        
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
                icd11_code TEXT,
                disease_name TEXT,
                abha_id TEXT UNIQUE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                created_by TEXT
            )
        ''')
        
        # Add ABHA ID column if it doesn't exist (for existing databases)
        try:
            conn.execute('ALTER TABLE patients ADD COLUMN abha_id TEXT')
        except (db.OperationalError, Exception):
            pass  # Column already exists

        # Add the ICD-11/NAMASTE columns for databases created before them.
        # CREATE TABLE IF NOT EXISTS above is a no-op on an existing table, so
        # without these a pre-existing register would reject the INSERT that
        # now names these columns.
        for _column, _decl in (('icd11_code', 'TEXT'), ('disease_name', 'TEXT')):
            try:
                conn.execute(f'ALTER TABLE patients ADD COLUMN {_column} {_decl}')
            except (db.OperationalError, Exception):
                pass  # Column already exists

        try:
            conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_patients_abha_id ON patients(abha_id)')
        except (db.OperationalError, Exception):
            pass
        
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
                patient_abha_id TEXT,
                FOREIGN KEY (patient_id) REFERENCES patients (patient_id)
            )
        ''')

        # Same for the ABHA column add_diagnosis() writes. It used to run that
        # ALTER on every insert, once per diagnosis saved.
        try:
            conn.execute('ALTER TABLE patient_diagnoses ADD COLUMN patient_abha_id TEXT')
        except (db.OperationalError, Exception):
            pass  # Column already exists
        
        conn.commit()
        conn.close()
    
    def create_patient(self, data, created_by):
        conn = db.connect(self.db_file)
        
        try:
            # Generate patient ID
            cursor = conn.execute('SELECT COUNT(*) FROM patients')
            count = cursor.fetchone()[0]
            patient_id = f"P{str(count + 1).zfill(4)}"
            
            # Validate required fields
            if not data.get('name') or not data.get('contact'):
                raise ValueError('Name and contact are required fields')

            abha_id = data.get('abha_id', '')
            cursor = conn.execute('''
                INSERT INTO patients (patient_id, name, age, gender, contact, email, address, medical_history, allergies, icd11_code, disease_name, abha_id, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (patient_id, data['name'], data.get('age'), data.get('gender'), data.get('contact'),
                  data.get('email', ''), data.get('address', ''), data.get('medical_history', ''),
                  data.get('allergies', ''), data.get('icd11_code', ''), data.get('disease_name', ''),
                  (abha_id if abha_id else None), created_by))
            
            conn.commit()
            return patient_id
            
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()
    
    def get_patient(self, patient_id):
        conn = db.connect(self.db_file)
        conn.row_factory = db.Row
        cursor = conn.execute('SELECT * FROM patients WHERE UPPER(patient_id) = UPPER(?)', (patient_id,))
        patient = cursor.fetchone()
        conn.close()
        return dict(patient) if patient else None
    
    def update_patient(self, patient_id, data):
        conn = db.connect(self.db_file)
        abha_id = data.get('abha_id', '')
        if abha_id == '':
            abha_id = None
        conn.execute('''
            UPDATE patients 
            SET name=?, age=?, gender=?, contact=?, email=?, address=?, medical_history=?, allergies=?, icd11_code=?, disease_name=?, abha_id=?, updated_at=CURRENT_TIMESTAMP
            WHERE patient_id=?
        ''', (data.get('name'), data.get('age'), data.get('gender'), data.get('contact'),
              data.get('email', ''), data.get('address', ''), data.get('medical_history', ''),
              data.get('allergies', ''), data.get('icd11_code', ''), data.get('disease_name', ''),
              abha_id, patient_id))
        conn.commit()
        conn.close()
    
    def delete_patient(self, patient_id):
        conn = db.connect(self.db_file)
        conn.execute('DELETE FROM patients WHERE patient_id = ?', (patient_id,))
        conn.execute('DELETE FROM patient_diagnoses WHERE patient_id = ?', (patient_id,))
        conn.commit()
        conn.close()
    
    def search_patients(self, query='', filters=None):
        conn = db.connect(self.db_file)
        conn.row_factory = db.Row
        
        sql = 'SELECT * FROM patients WHERE 1=1'
        params = []
        
        if query:
            # disease_name/icd11_code included so searching "diabetes" or "5A11"
            # finds the patient, not just the ones whose name happens to match.
            sql += ' AND (UPPER(name) LIKE UPPER(?) OR UPPER(patient_id) LIKE UPPER(?) OR UPPER(contact) LIKE UPPER(?) OR UPPER(abha_id) LIKE UPPER(?) OR UPPER(disease_name) LIKE UPPER(?) OR UPPER(icd11_code) LIKE UPPER(?))'
            params.extend([f'%{query}%'] * 6)
        
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
        conn = db.connect(self.db_file)
        
        # Get patient's ABHA ID
        patient = self.get_patient(patient_id)
        patient_abha_id = patient.get('abha_id', '') if patient else ''
        
        symptoms = diagnosis_data.get('symptoms') or diagnosis_data.get('condition_name') or diagnosis_data.get('notes', '') or ''
        diag_date = diagnosis_data.get('date') or datetime.now().date()
        if hasattr(diag_date, 'isoformat'):
            diag_date = diag_date.isoformat()
        conn.execute('''
            INSERT INTO patient_diagnoses (patient_id, diagnosis_date, symptoms, namaste_code, namaste_name, icd11_code, icd11_name, notes, patient_abha_id, created_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (patient_id, diag_date,
              symptoms, diagnosis_data.get('namaste_code'),
              diagnosis_data.get('namaste_name'), diagnosis_data.get('icd11_code'),
              diagnosis_data.get('icd11_name'), diagnosis_data.get('notes', '') or '', patient_abha_id or '', created_by))
        conn.commit()
        conn.close()
    
    def get_patient_diagnoses(self, patient_id):
        conn = db.connect(self.db_file)
        conn.row_factory = db.Row
        cursor = conn.execute('''
            SELECT * FROM patient_diagnoses 
            WHERE UPPER(patient_id) = UPPER(?) 
            ORDER BY diagnosis_date DESC, created_at DESC
        ''', (patient_id,))
        diagnoses = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return diagnoses
    
    def get_diagnoses_for_patients(self, patient_ids):
        """Every diagnosis for a set of patients, grouped by patient_id.

        The per-patient report view needs the diagnoses of all of one doctor's
        patients. Calling get_patient_diagnoses() in a loop issues one query per
        patient; this issues one for the whole set.

        Ordering within each group is the same as get_patient_diagnoses() would
        return (diagnosis_date DESC, created_at DESC), so a caller that iterates
        the groups in the order it passed the ids sees exactly what the loop
        produced. A patient_id with no rows is simply absent from the result.

        Matching is case-insensitive, as it is per patient, and rows are filed
        under the id the caller passed rather than the casing stored in the row,
        so the keys line up with the argument.
        """
        grouped = {}
        if not patient_ids:
            return grouped

        # Two ids differing only in case would share a group, exactly as they
        # would have shared a single get_patient_diagnoses() result.
        wanted = {pid.upper(): pid for pid in patient_ids}

        conn = db.connect(self.db_file)
        conn.row_factory = db.Row
        placeholders = ', '.join(['?'] * len(patient_ids))
        cursor = conn.execute(f'''
            SELECT * FROM patient_diagnoses
            WHERE UPPER(patient_id) IN ({placeholders})
            ORDER BY diagnosis_date DESC, created_at DESC
        ''', tuple(patient_ids))
        for row in cursor.fetchall():
            record = dict(row)
            key = wanted.get(record['patient_id'].upper())
            if key is not None:
                grouped.setdefault(key, []).append(record)
        conn.close()
        return grouped

    def get_all_patients(self):
        conn = db.connect(self.db_file)
        conn.row_factory = db.Row
        cursor = conn.execute('SELECT * FROM patients ORDER BY created_at DESC')
        patients = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return patients
    
    def get_all_diagnoses(self):
        conn = db.connect(self.db_file)
        conn.row_factory = db.Row
        cursor = conn.execute('SELECT * FROM patient_diagnoses ORDER BY created_at DESC')
        diagnoses = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return diagnoses

    def count_patients(self, created_by):
        """How many patients this clinician created."""
        conn = db.connect(self.db_file)
        cursor = conn.execute(
            'SELECT COUNT(*) FROM patients WHERE created_by = ?', (created_by,))
        count = cursor.fetchone()[0]
        conn.close()
        return count

    def count_diagnoses(self, created_by):
        """How many diagnoses this clinician recorded."""
        conn = db.connect(self.db_file)
        cursor = conn.execute(
            'SELECT COUNT(*) FROM patient_diagnoses WHERE created_by = ?', (created_by,))
        count = cursor.fetchone()[0]
        conn.close()
        return count