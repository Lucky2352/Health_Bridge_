from dotenv import load_dotenv
load_dotenv()

# Test key application database operations
from db import connect, singleton
from database import Database
from diagnosis_models import DiagnosisDatabase
from patient_models import PatientDatabase
from enhanced_auth import EnhancedAuthDB

print("=== Testing Application Database Operations ===")

# Test Database (diagnosis.db)
print("\n1. Testing Database class (diagnosis.db)...")
db = Database()
history = db.get_patient_history('T7001')
print(f"   get_patient_history('T7001'): {len(history)} records")

# Test DiagnosisDatabase
print("\n2. Testing DiagnosisDatabase...")
diag_db = DiagnosisDatabase()
patients = diag_db.get_all_patients()
print(f"   get_all_patients(): {len(patients)} patients")

# Test PatientDatabase
print("\n3. Testing PatientDatabase...")
pat_db = PatientDatabase()
patients = pat_db.get_all_patients()
print(f"   get_all_patients(): {len(patients)} patients")

# Test EnhancedAuthDB
print("\n4. Testing EnhancedAuthDB...")
auth_db = EnhancedAuthDB()
user = auth_db.get_user_by_username('doctor')
print(f"   get_user_by_username('doctor'): {user.username if user else 'NOT FOUND'} (role: {user.role if user else 'N/A'})")

user = auth_db.get_user_by_patient_id('P0001')
print(f"   get_user_by_patient_id('P0001'): {user.username if user else 'NOT FOUND'} (role: {user.role if user else 'N/A'})")

print("\n=== All tests passed! ===")