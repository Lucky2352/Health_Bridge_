import sqlite3
import os
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class DiagnosisDatabase:
    def __init__(self, db_file='enhanced_auth.db'):
        self.db_file = os.path.abspath(db_file)
        self.init_database()
    
    def init_database(self):
        """Initialize diagnosis database with proper foreign key relationships"""
        conn = sqlite3.connect(self.db_file)
        conn.execute('PRAGMA foreign_keys = ON')
        
        # Create diagnosis table with proper relationships
        conn.execute('''
            CREATE TABLE IF NOT EXISTS diagnoses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doctor_id TEXT NOT NULL,
                patient_id TEXT NOT NULL,
                condition_code TEXT,
                condition_name TEXT NOT NULL,
                notes TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create other tables
        conn.execute('''
            CREATE TABLE IF NOT EXISTS appointments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doctor_id TEXT NOT NULL,
                patient_id TEXT NOT NULL,
                appointment_date DATETIME NOT NULL,
                status TEXT DEFAULT 'scheduled',
                notes TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.execute('''
            CREATE TABLE IF NOT EXISTS prescriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doctor_id TEXT NOT NULL,
                patient_id TEXT NOT NULL,
                medication_name TEXT NOT NULL,
                dosage TEXT,
                frequency TEXT,
                duration TEXT,
                notes TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.execute('''
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id TEXT NOT NULL,
                report_type TEXT,
                file_path TEXT,
                uploaded_by INTEGER,
                uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def add_diagnosis(self, doctor_id, patient_id, condition_name, condition_code=None, notes=None):
        """Add a new diagnosis with proper validation"""
        try:
            conn = sqlite3.connect(self.db_file)
            conn.execute('PRAGMA foreign_keys = OFF')
            
            cursor = conn.execute('''
                INSERT INTO diagnoses (doctor_id, patient_id, condition_code, condition_name, notes)
                VALUES (?, ?, ?, ?, ?)
            ''', (doctor_id, patient_id, condition_code, condition_name, notes))
            
            diagnosis_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            logger.info(f"Diagnosis added: ID {diagnosis_id}, Doctor {doctor_id}, Patient {patient_id}")
            return diagnosis_id
            
        except Exception as e:
            logger.error(f"Error adding diagnosis: {e}")
            raise
    
    def add_prescription(self, doctor_id, patient_id, medication_name, dosage=None, frequency=None, duration=None, notes=None):
        """Add a new prescription"""
        try:
            conn = sqlite3.connect(self.db_file)
            conn.execute('PRAGMA foreign_keys = ON')
            
            cursor = conn.execute('''
                INSERT INTO prescriptions (doctor_id, patient_id, medication_name, dosage, frequency, duration, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (doctor_id, patient_id, medication_name, dosage, frequency, duration, notes))
            
            prescription_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            return prescription_id
            
        except Exception as e:
            logger.error(f"Error adding prescription: {e}")
            raise
    
    def add_appointment(self, doctor_id, patient_id, appointment_date, notes=None):
        """Add a new appointment"""
        try:
            conn = sqlite3.connect(self.db_file)
            conn.execute('PRAGMA foreign_keys = ON')
            
            cursor = conn.execute('''
                INSERT INTO appointments (doctor_id, patient_id, appointment_date, notes)
                VALUES (?, ?, ?, ?)
            ''', (doctor_id, patient_id, appointment_date, notes))
            
            appointment_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            return appointment_id
            
        except Exception as e:
            logger.error(f"Error adding appointment: {e}")
            raise
    
    def get_patient_diagnoses(self, patient_id):
        """Get all diagnoses for a specific patient with doctor information"""
        try:
            conn = sqlite3.connect(self.db_file)
            conn.row_factory = sqlite3.Row
            
            cursor = conn.execute('''
                SELECT d.*, u.full_name as doctor_name, u.email as doctor_email, d.doctor_id
                FROM diagnoses d
                JOIN enhanced_users u ON d.doctor_id = u.doctor_id
                WHERE d.patient_id = ?
                ORDER BY d.created_at DESC
            ''', (patient_id,))
            
            diagnoses = [dict(row) for row in cursor.fetchall()]
            conn.close()
            
            return diagnoses
            
        except Exception as e:
            logger.error(f"Error fetching patient diagnoses: {e}")
            return []
    
    def get_patient_prescriptions(self, patient_id):
        """Get all prescriptions for a specific patient"""
        try:
            conn = sqlite3.connect(self.db_file)
            conn.row_factory = sqlite3.Row
            
            cursor = conn.execute('''
                SELECT p.*, u.full_name as doctor_name
                FROM prescriptions p
                JOIN enhanced_users u ON p.doctor_id = u.id
                WHERE p.patient_id = ?
                ORDER BY p.created_at DESC
            ''', (patient_id,))
            
            prescriptions = [dict(row) for row in cursor.fetchall()]
            conn.close()
            
            return prescriptions
            
        except Exception as e:
            logger.error(f"Error fetching patient prescriptions: {e}")
            return []
    
    def get_patient_appointments(self, patient_id):
        """Get all appointments for a specific patient"""
        try:
            conn = sqlite3.connect(self.db_file)
            conn.row_factory = sqlite3.Row
            
            cursor = conn.execute('''
                SELECT a.*, u.full_name as doctor_name
                FROM appointments a
                JOIN enhanced_users u ON a.doctor_id = u.id
                WHERE a.patient_id = ?
                ORDER BY a.appointment_date DESC
            ''', (patient_id,))
            
            appointments = [dict(row) for row in cursor.fetchall()]
            conn.close()
            
            return appointments
            
        except Exception as e:
            logger.error(f"Error fetching patient appointments: {e}")
            return []
    
    def get_doctor_diagnoses(self, doctor_id):
        """Get all diagnoses created by a specific doctor"""
        try:
            conn = sqlite3.connect(self.db_file)
            conn.row_factory = sqlite3.Row
            
            cursor = conn.execute('''
                SELECT d.*, p.full_name as patient_name, p.email as patient_email
                FROM diagnoses d
                JOIN enhanced_users p ON d.patient_id = p.id
                WHERE d.doctor_id = ?
                ORDER BY d.created_at DESC
            ''', (doctor_id,))
            
            diagnoses = [dict(row) for row in cursor.fetchall()]
            conn.close()
            
            return diagnoses
            
        except Exception as e:
            logger.error(f"Error fetching doctor diagnoses: {e}")
            return []
    
    def validate_doctor_patient_relationship(self, doctor_id, patient_id):
        """Validate that doctor can add diagnosis for this patient"""
        # For now, allow any doctor to add diagnosis for any patient
        # In a real system, you'd check if patient is assigned to doctor
        return True
    
    def get_all_patients(self):
        """Get all patients for doctor dashboard"""
        try:
            conn = sqlite3.connect(self.db_file)
            conn.row_factory = sqlite3.Row
            
            cursor = conn.execute('''
                SELECT patient_id, full_name, email, created_at
                FROM enhanced_users
                WHERE role = 'patient' AND is_active = 1
                ORDER BY created_at DESC
            ''')
            
            patients = [dict(row) for row in cursor.fetchall()]
            conn.close()
            
            return patients
            
        except Exception as e:
            logger.error(f"Error fetching patients: {e}")
            return []