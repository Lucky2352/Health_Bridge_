import uuid
from datetime import datetime

class FHIRService:
    @staticmethod
    def create_patient_resource(patient_data):
        """Create FHIR Patient resource from patient data"""
        patient = {
            "resourceType": "Patient",
            "id": patient_data['patient_id'],
            "identifier": [
                {
                    "use": "usual",
                    "system": "http://healthbridge.emr/patient-id",
                    "value": patient_data['patient_id']
                }
            ],
            "name": [
                {
                    "use": "official",
                    "text": patient_data.get('name', 'Unknown')
                }
            ],
            "active": True
        }
        
        # Add ABHA ID if available
        if patient_data.get('abha_id'):
            patient['identifier'].append({
                "use": "official",
                "system": "http://abdm.gov.in/abha-id",
                "value": patient_data['abha_id']
            })
        
        # Add gender if available
        if patient_data.get('gender'):
            gender_map = {'male': 'male', 'female': 'female', 'other': 'other'}
            patient['gender'] = gender_map.get(patient_data['gender'].lower(), 'unknown')
        
        # Add contact info if available
        if patient_data.get('contact'):
            patient['telecom'] = [
                {
                    "system": "phone",
                    "value": patient_data['contact'],
                    "use": "mobile"
                }
            ]
        
        # Add email if available
        if patient_data.get('email'):
            if 'telecom' not in patient:
                patient['telecom'] = []
            patient['telecom'].append({
                "system": "email",
                "value": patient_data['email']
            })
        
        # Add birth date if age is available
        if patient_data.get('age'):
            try:
                birth_year = datetime.now().year - int(patient_data['age'])
                patient['birthDate'] = f"{birth_year}-01-01"
            except (ValueError, TypeError):
                pass
        
        return patient
    
    @staticmethod
    def create_condition_resource(record):
        """Create FHIR Condition resource from diagnosis record"""
        condition_id = str(uuid.uuid4())
        
        # Build coding array with both NAMASTE and ICD-11 codes
        coding = []
        if record.get('namaste_code'):
            coding.append({
                "system": "http://namaste.gov.in/codes",
                "code": record['namaste_code'],
                "display": record.get('symptom', 'Unknown condition')
            })
        
        if record.get('icd11_code'):
            coding.append({
                "system": "http://id.who.int/icd/release/11/mms",
                "code": record['icd11_code'],
                "display": record.get('symptom', 'Unknown condition')
            })
        
        condition = {
            "resourceType": "Condition",
            "id": condition_id,
            "subject": {
                "reference": f"Patient/{record['patient_id']}"
            },
            "code": {
                "coding": coding,
                "text": record.get('symptom', 'Unknown condition')
            },
            "clinicalStatus": {
                "coding": [{
                    "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                    "code": "active"
                }]
            }
        }
        
        # Add recorded date if available
        if record.get('timestamp'):
            condition['recordedDate'] = record['timestamp']
        
        # Add notes if available
        if record.get('notes'):
            condition['note'] = [{
                "text": record['notes']
            }]
        
        return condition
    
    @staticmethod
    def create_bundle(patient_id, records, patient_data=None):
        """Create FHIR Bundle containing Patient and Condition resources"""
        bundle_id = str(uuid.uuid4())
        entries = []
        
        # Add Patient resource if patient data is provided
        if patient_data:
            patient_resource = FHIRService.create_patient_resource(patient_data)
            entries.append({
                "fullUrl": f"Patient/{patient_id}",
                "resource": patient_resource
            })
        
        # Add Condition resources
        for record in records:
            condition = FHIRService.create_condition_resource(record)
            entries.append({
                "fullUrl": f"Condition/{condition['id']}",
                "resource": condition
            })
        
        bundle = {
            "resourceType": "Bundle",
            "id": bundle_id,
            "type": "searchset",
            "timestamp": datetime.now().isoformat(),
            "total": len(entries),
            "entry": entries
        }
        
        return bundle