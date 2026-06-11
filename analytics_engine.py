import sqlite3
from datetime import datetime, timedelta
import json
from collections import Counter
import pandas as pd
from io import BytesIO
import base64

class AnalyticsEngine:
    def __init__(self):
        self.patient_db = 'patients.db'
        self.auth_db = 'enhanced_auth.db'
        self.fhir_db = 'fhir_data.db'
    
    def get_dashboard_analytics(self, user_role, doctor_id=None):
        """Get dashboard analytics based on user role"""
        analytics = {
            'patient_stats': self.get_patient_statistics(user_role, doctor_id),
            'disease_stats': self.get_disease_statistics(user_role, doctor_id),
            'demographics': self.get_demographics(user_role, doctor_id),
            'recent_activities': self.get_recent_activities(user_role, doctor_id),
            'monthly_trends': self.get_monthly_trends(user_role, doctor_id)
        }
        return analytics
    
    def get_patient_statistics(self, user_role, doctor_id=None):
        """Get patient count statistics"""
        conn = sqlite3.connect(self.patient_db)
        
        if user_role == 'admin':
            # Admin sees all patients
            cursor = conn.execute('SELECT COUNT(*) FROM patients')
            total_patients = cursor.fetchone()[0]
            
            cursor = conn.execute('''
                SELECT COUNT(*) FROM patients 
                WHERE created_at >= date('now', '-30 days')
            ''')
            new_patients = cursor.fetchone()[0]
        else:
            # Doctor sees only their patients
            cursor = conn.execute('SELECT COUNT(*) FROM patients WHERE created_by = ?', (doctor_id,))
            total_patients = cursor.fetchone()[0]
            
            cursor = conn.execute('''
                SELECT COUNT(*) FROM patients 
                WHERE created_by = ? AND created_at >= date('now', '-30 days')
            ''', (doctor_id,))
            new_patients = cursor.fetchone()[0]
        
        conn.close()
        return {
            'total': total_patients,
            'new_this_month': new_patients
        }
    
    def get_disease_statistics(self, user_role, doctor_id=None):
        """Get most common diseases"""
        conn = sqlite3.connect(self.patient_db)
        
        if user_role == 'admin':
            cursor = conn.execute('''
                SELECT namaste_code, namaste_name, icd11_code, icd11_name, COUNT(*) as count
                FROM patient_diagnoses 
                WHERE namaste_code IS NOT NULL OR icd11_code IS NOT NULL
                GROUP BY COALESCE(namaste_code, icd11_code)
                ORDER BY count DESC
                LIMIT 10
            ''')
        else:
            cursor = conn.execute('''
                SELECT namaste_code, namaste_name, icd11_code, icd11_name, COUNT(*) as count
                FROM patient_diagnoses 
                WHERE (namaste_code IS NOT NULL OR icd11_code IS NOT NULL)
                AND created_by = ?
                GROUP BY COALESCE(namaste_code, icd11_code)
                ORDER BY count DESC
                LIMIT 10
            ''', (doctor_id,))
        
        diseases = []
        for row in cursor.fetchall():
            diseases.append({
                'namaste_code': row[0],
                'namaste_name': row[1],
                'icd11_code': row[2],
                'icd11_name': row[3],
                'count': row[4],
                'display_name': row[1] or row[3] or row[0] or row[2]
            })
        
        conn.close()
        return diseases
    
    def get_demographics(self, user_role, doctor_id=None):
        """Get patient demographics"""
        conn = sqlite3.connect(self.patient_db)
        
        if user_role == 'admin':
            # Gender distribution
            cursor = conn.execute('''
                SELECT gender, COUNT(*) as count 
                FROM patients 
                GROUP BY gender
            ''')
            gender_data = dict(cursor.fetchall())
            
            # Age distribution
            cursor = conn.execute('''
                SELECT 
                    CASE 
                        WHEN age < 18 THEN 'Under 18'
                        WHEN age BETWEEN 18 AND 30 THEN '18-30'
                        WHEN age BETWEEN 31 AND 50 THEN '31-50'
                        WHEN age BETWEEN 51 AND 70 THEN '51-70'
                        ELSE 'Over 70'
                    END as age_group,
                    COUNT(*) as count
                FROM patients
                GROUP BY age_group
            ''')
            age_data = dict(cursor.fetchall())
        else:
            # Doctor sees only their patients
            cursor = conn.execute('''
                SELECT gender, COUNT(*) as count 
                FROM patients 
                WHERE created_by = ?
                GROUP BY gender
            ''', (doctor_id,))
            gender_data = dict(cursor.fetchall())
            
            cursor = conn.execute('''
                SELECT 
                    CASE 
                        WHEN age < 18 THEN 'Under 18'
                        WHEN age BETWEEN 18 AND 30 THEN '18-30'
                        WHEN age BETWEEN 31 AND 50 THEN '31-50'
                        WHEN age BETWEEN 51 AND 70 THEN '51-70'
                        ELSE 'Over 70'
                    END as age_group,
                    COUNT(*) as count
                FROM patients
                WHERE created_by = ?
                GROUP BY age_group
            ''', (doctor_id,))
            age_data = dict(cursor.fetchall())
        
        conn.close()
        return {
            'gender': gender_data,
            'age_groups': age_data
        }
    
    def get_recent_activities(self, user_role, doctor_id=None):
        """Get recent activities"""
        conn = sqlite3.connect(self.patient_db)
        
        if user_role == 'admin':
            # Recent patients
            cursor = conn.execute('''
                SELECT name, created_at, 'Patient Added' as activity_type
                FROM patients 
                ORDER BY created_at DESC 
                LIMIT 5
            ''')
            patient_activities = cursor.fetchall()
            
            # Recent diagnoses
            cursor = conn.execute('''
                SELECT p.name, pd.diagnosis_date, 'Diagnosis Added' as activity_type
                FROM patient_diagnoses pd
                JOIN patients p ON pd.patient_id = p.patient_id
                ORDER BY pd.created_at DESC 
                LIMIT 5
            ''')
            diagnosis_activities = cursor.fetchall()
        else:
            # Doctor sees only their activities
            cursor = conn.execute('''
                SELECT name, created_at, 'Patient Added' as activity_type
                FROM patients 
                WHERE created_by = ?
                ORDER BY created_at DESC 
                LIMIT 5
            ''', (doctor_id,))
            patient_activities = cursor.fetchall()
            
            cursor = conn.execute('''
                SELECT p.name, pd.diagnosis_date, 'Diagnosis Added' as activity_type
                FROM patient_diagnoses pd
                JOIN patients p ON pd.patient_id = p.patient_id
                WHERE pd.created_by = ?
                ORDER BY pd.created_at DESC 
                LIMIT 5
            ''', (doctor_id,))
            diagnosis_activities = cursor.fetchall()
        
        # Combine and sort activities
        all_activities = []
        for activity in patient_activities + diagnosis_activities:
            all_activities.append({
                'name': activity[0],
                'date': activity[1],
                'type': activity[2]
            })
        
        # Sort by date
        all_activities.sort(key=lambda x: x['date'], reverse=True)
        
        conn.close()
        return all_activities[:10]
    
    def get_monthly_trends(self, user_role, doctor_id=None):
        """Get monthly patient registration trends"""
        conn = sqlite3.connect(self.patient_db)
        
        if user_role == 'admin':
            cursor = conn.execute('''
                SELECT 
                    strftime('%Y-%m', created_at) as month,
                    COUNT(*) as count
                FROM patients
                WHERE created_at >= date('now', '-12 months')
                GROUP BY month
                ORDER BY month
            ''')
        else:
            cursor = conn.execute('''
                SELECT 
                    strftime('%Y-%m', created_at) as month,
                    COUNT(*) as count
                FROM patients
                WHERE created_by = ? AND created_at >= date('now', '-12 months')
                GROUP BY month
                ORDER BY month
            ''', (doctor_id,))
        
        trends = []
        for row in cursor.fetchall():
            trends.append({
                'month': row[0],
                'count': row[1]
            })
        
        conn.close()
        return trends
    
    def generate_excel_report(self, user_role, doctor_id=None):
        """Generate Excel report"""
        analytics = self.get_dashboard_analytics(user_role, doctor_id)
        
        # Create Excel file in memory
        output = BytesIO()
        
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            # Patient statistics
            patient_stats_df = pd.DataFrame([analytics['patient_stats']])
            patient_stats_df.to_excel(writer, sheet_name='Patient Statistics', index=False)
            
            # Disease statistics
            if analytics['disease_stats']:
                disease_df = pd.DataFrame(analytics['disease_stats'])
                disease_df.to_excel(writer, sheet_name='Disease Statistics', index=False)
            
            # Demographics
            if analytics['demographics']['gender']:
                gender_df = pd.DataFrame(list(analytics['demographics']['gender'].items()), 
                                       columns=['Gender', 'Count'])
                gender_df.to_excel(writer, sheet_name='Gender Demographics', index=False)
            
            if analytics['demographics']['age_groups']:
                age_df = pd.DataFrame(list(analytics['demographics']['age_groups'].items()), 
                                    columns=['Age Group', 'Count'])
                age_df.to_excel(writer, sheet_name='Age Demographics', index=False)
            
            # Recent activities
            if analytics['recent_activities']:
                activities_df = pd.DataFrame(analytics['recent_activities'])
                activities_df.to_excel(writer, sheet_name='Recent Activities', index=False)
            
            # Monthly trends
            if analytics['monthly_trends']:
                trends_df = pd.DataFrame(analytics['monthly_trends'])
                trends_df.to_excel(writer, sheet_name='Monthly Trends', index=False)
        
        output.seek(0)
        return output
    
    def get_fhir_analytics(self, user_role, doctor_id=None):
        """Get FHIR bundle analytics"""
        conn = sqlite3.connect(self.fhir_db)
        
        if user_role == 'admin':
            # Total bundles
            cursor = conn.execute('SELECT COUNT(*) FROM fhir_bundles')
            total_bundles = cursor.fetchone()[0]
            
            # Resource types
            cursor = conn.execute('''
                SELECT resource_type, COUNT(*) as count
                FROM fhir_resources
                GROUP BY resource_type
                ORDER BY count DESC
            ''')
            resource_types = dict(cursor.fetchall())
            
            # Mapped conditions
            cursor = conn.execute('''
                SELECT COUNT(*) FROM fhir_resources 
                WHERE mapped_icd11 IS NOT NULL OR mapped_namaste IS NOT NULL
            ''')
            mapped_conditions = cursor.fetchone()[0]
        else:
            # Doctor sees only their FHIR data
            cursor = conn.execute('SELECT COUNT(*) FROM fhir_bundles WHERE uploaded_by = ?', (doctor_id,))
            total_bundles = cursor.fetchone()[0]
            
            cursor = conn.execute('''
                SELECT fr.resource_type, COUNT(*) as count
                FROM fhir_resources fr
                JOIN fhir_bundles fb ON fr.bundle_id = fb.bundle_id
                WHERE fb.uploaded_by = ?
                GROUP BY fr.resource_type
                ORDER BY count DESC
            ''', (doctor_id,))
            resource_types = dict(cursor.fetchall())
            
            cursor = conn.execute('''
                SELECT COUNT(*) FROM fhir_resources fr
                JOIN fhir_bundles fb ON fr.bundle_id = fb.bundle_id
                WHERE fb.uploaded_by = ? 
                AND (fr.mapped_icd11 IS NOT NULL OR fr.mapped_namaste IS NOT NULL)
            ''', (doctor_id,))
            mapped_conditions = cursor.fetchone()[0]
        
        conn.close()
        return {
            'total_bundles': total_bundles,
            'resource_types': resource_types,
            'mapped_conditions': mapped_conditions
        }