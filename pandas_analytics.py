import pandas as pd
import sqlite3
from datetime import datetime, timedelta
import json

class PandasAnalytics:
    def __init__(self):
        self.patients_db = 'patients.db'
        self.diagnosis_db = 'diagnosis.db'
    
    def get_patient_registration_data(self, doctor_id=None):
        """Get patient registration data grouped by time intervals"""
        try:
            conn = sqlite3.connect(self.patients_db)
            
            # Fetch patient data - filter by doctor if provided
            if doctor_id:
                query = """
                SELECT patient_id, name, created_at, gender, age
                FROM patients 
                WHERE created_by = ?
                ORDER BY created_at DESC
                """
                df = pd.read_sql_query(query, conn, params=[doctor_id])
            else:
                query = """
                SELECT patient_id, name, created_at, gender, age
                FROM patients 
                ORDER BY created_at DESC
                """
                df = pd.read_sql_query(query, conn)
            
            conn.close()
            
            if df.empty:
                return {'weekly': [], 'monthly': []}
            
            # Convert created_at to datetime
            df['created_at'] = pd.to_datetime(df['created_at'])
            
            # Group by week
            df['week'] = df['created_at'].dt.to_period('W')
            weekly_counts = df.groupby('week').size().reset_index(name='count')
            weekly_counts['week'] = weekly_counts['week'].astype(str)
            
            # Group by month
            df['month'] = df['created_at'].dt.to_period('M')
            monthly_counts = df.groupby('month').size().reset_index(name='count')
            monthly_counts['month'] = monthly_counts['month'].astype(str)
            
            return {
                'weekly': weekly_counts.to_dict('records'),
                'monthly': monthly_counts.to_dict('records')
            }
            
        except Exception:
            return {'weekly': [], 'monthly': []}
    
    def get_diagnosis_distribution(self, doctor_id=None):
        """Get diagnosis distribution data"""
        try:
            # Get data from both databases
            patients_conn = sqlite3.connect(self.patients_db)
            diagnosis_conn = sqlite3.connect(self.diagnosis_db)
            
            # Fetch patient diagnoses - filter by doctor if provided
            if doctor_id:
                patient_query = """
                SELECT patient_id, symptoms, namaste_code, icd11_code, diagnosis_date
                FROM patient_diagnoses 
                WHERE symptoms IS NOT NULL AND symptoms != '' AND created_by = ?
                """
                df1 = pd.read_sql_query(patient_query, patients_conn, params=[doctor_id])
                
                # Fetch diagnosis records
                diagnosis_query = """
                SELECT patient_id, symptom as symptoms, namaste_code, icd11_code, timestamp as diagnosis_date
                FROM diagnosis_records 
                WHERE symptom IS NOT NULL AND symptom != ''
                """
                df2 = pd.read_sql_query(diagnosis_query, diagnosis_conn)
                # Filter df2 by patients that belong to this doctor
                patient_ids_query = "SELECT patient_id FROM patients WHERE created_by = ?"
                doctor_patients = pd.read_sql_query(patient_ids_query, patients_conn, params=[doctor_id])
                if not doctor_patients.empty:
                    df2 = df2[df2['patient_id'].isin(doctor_patients['patient_id'])]
            else:
                patient_query = """
                SELECT patient_id, symptoms, namaste_code, icd11_code, diagnosis_date
                FROM patient_diagnoses 
                WHERE symptoms IS NOT NULL AND symptoms != ''
                """
                df1 = pd.read_sql_query(patient_query, patients_conn)
                
                diagnosis_query = """
                SELECT patient_id, symptom as symptoms, namaste_code, icd11_code, timestamp as diagnosis_date
                FROM diagnosis_records 
                WHERE symptom IS NOT NULL AND symptom != ''
                """
                df2 = pd.read_sql_query(diagnosis_query, diagnosis_conn)
            
            patients_conn.close()
            diagnosis_conn.close()
            
            # Combine dataframes
            df = pd.concat([df1, df2], ignore_index=True)
            
            if df.empty:
                return {'categories': [], 'codes': []}
            
            # Group by symptoms/categories
            symptom_counts = df['symptoms'].value_counts().head(10)
            total_symptoms = symptom_counts.sum()
            
            categories_data = []
            for symptom, count in symptom_counts.items():
                percentage = (count / total_symptoms) * 100
                categories_data.append({
                    'category': symptom[:30],  # Truncate long names
                    'count': int(count),
                    'percentage': round(percentage, 1)
                })
            
            # Group by NAMASTE codes
            namaste_counts = df[df['namaste_code'].notna()]['namaste_code'].value_counts().head(8)
            codes_data = []
            for code, count in namaste_counts.items():
                codes_data.append({
                    'code': code,
                    'count': int(count),
                    'type': 'NAMASTE'
                })
            
            # Group by ICD codes
            icd_counts = df[df['icd11_code'].notna()]['icd11_code'].value_counts().head(8)
            for code, count in icd_counts.items():
                codes_data.append({
                    'code': code,
                    'count': int(count),
                    'type': 'ICD-11'
                })
            
            return {
                'categories': categories_data,
                'codes': codes_data
            }
            
        except Exception:
            return {'categories': [], 'codes': []}
    
    def get_patient_demographics(self, doctor_id=None):
        """Get patient demographics data"""
        try:
            conn = sqlite3.connect(self.patients_db)
            
            # Filter by doctor if provided
            if doctor_id:
                query = """
                SELECT gender, age, created_at
                FROM patients 
                WHERE gender IS NOT NULL AND created_by = ?
                """
                df = pd.read_sql_query(query, conn, params=[doctor_id])
            else:
                query = """
                SELECT gender, age, created_at
                FROM patients 
                WHERE gender IS NOT NULL
                """
                df = pd.read_sql_query(query, conn)
            
            conn.close()
            
            if df.empty:
                return {'gender': [], 'age_groups': []}
            
            # Gender distribution
            gender_counts = df['gender'].value_counts()
            gender_data = []
            for gender, count in gender_counts.items():
                gender_data.append({
                    'gender': gender.title(),
                    'count': int(count)
                })
            
            # Age groups
            df['age'] = pd.to_numeric(df['age'], errors='coerce')
            df = df.dropna(subset=['age'])
            
            age_bins = [0, 18, 30, 45, 60, 100]
            age_labels = ['0-17', '18-29', '30-44', '45-59', '60+']
            df['age_group'] = pd.cut(df['age'], bins=age_bins, labels=age_labels, right=False)
            
            age_counts = df['age_group'].value_counts()
            age_data = []
            for age_group, count in age_counts.items():
                age_data.append({
                    'age_group': str(age_group),
                    'count': int(count)
                })
            
            return {
                'gender': gender_data,
                'age_groups': age_data
            }
            
        except Exception:
            return {'gender': [], 'age_groups': []}
    
    def get_comprehensive_analytics(self, doctor_id=None):
        """Get all analytics data in one call"""
        return {
            'registrations': self.get_patient_registration_data(doctor_id),
            'diagnoses': self.get_diagnosis_distribution(doctor_id),
            'demographics': self.get_patient_demographics(doctor_id),
            'timestamp': datetime.now().isoformat()
        }