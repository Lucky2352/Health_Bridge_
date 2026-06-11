import json
import sqlite3
from datetime import datetime
from flask import jsonify
import uuid
import re
from fhir_bundle import FHIRBundleStorage, FHIRBundleValidator

class FHIRInteroperability:
    def __init__(self, db_file='fhir_data.db'):
        self.db_file = db_file
        self.bundle_storage = FHIRBundleStorage()
        self.init_database()
    
    def init_database(self):
        conn = sqlite3.connect(self.db_file)
        
        # FHIR Bundles table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS fhir_bundles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bundle_id TEXT UNIQUE NOT NULL,
                bundle_type TEXT,
                total_entries INTEGER,
                upload_date DATETIME DEFAULT CURRENT_TIMESTAMP,
                uploaded_by TEXT,
                status TEXT DEFAULT 'processed',
                raw_data TEXT
            )
        ''')
        
        # Add upload_date column if it doesn't exist (for existing databases)
        try:
            conn.execute('ALTER TABLE fhir_bundles ADD COLUMN upload_date DATETIME DEFAULT CURRENT_TIMESTAMP')
        except sqlite3.OperationalError:
            pass  # Column already exists
        
        # FHIR Resources table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS fhir_resources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bundle_id TEXT,
                resource_type TEXT,
                resource_id TEXT,
                patient_reference TEXT,
                code_system TEXT,
                code_value TEXT,
                display_name TEXT,
                mapped_icd11 TEXT,
                mapped_namaste TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (bundle_id) REFERENCES fhir_bundles (bundle_id)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def validate_fhir_bundle(self, bundle_data):
        """Validate FHIR R4 Bundle structure"""
        return FHIRBundleValidator.validate_bundle(bundle_data)
    
    def process_fhir_bundle(self, bundle_data, uploaded_by):
        """Process and store FHIR Bundle"""
        # Store in new bundle storage system
        bundle_id = self.bundle_storage.store_bundle(bundle_data, uploaded_by, 'valid')
        
        # Also store in legacy system for compatibility
        bundle_type = bundle_data.get('type', 'collection')
        entries = bundle_data.get('entry', [])
        
        conn = sqlite3.connect(self.db_file)
        
        # Store bundle metadata
        conn.execute('''
            INSERT OR REPLACE INTO fhir_bundles (bundle_id, bundle_type, total_entries, uploaded_by, raw_data)
            VALUES (?, ?, ?, ?, ?)
        ''', (bundle_id, bundle_type, len(entries), uploaded_by, json.dumps(bundle_data)))
        
        # Process each resource
        for entry in entries:
            resource = entry.get('resource', {})
            self._process_resource(conn, bundle_id, resource)
        
        conn.commit()
        conn.close()
        
        return bundle_id
    
    def _process_resource(self, conn, bundle_id, resource):
        """Process individual FHIR resource"""
        resource_type = resource.get('resourceType')
        resource_id = resource.get('id', str(uuid.uuid4()))
        
        # Extract patient reference and ABHA ID
        patient_ref = self._extract_patient_reference(resource)
        abha_id = self._extract_abha_id(resource)
        
        # Add ABHA ID column if it doesn't exist
        try:
            conn.execute('ALTER TABLE fhir_resources ADD COLUMN patient_abha_id TEXT')
        except sqlite3.OperationalError:
            pass  # Column already exists
        
        # Extract condition codes for mapping
        if resource_type == 'Condition':
            codes = self._extract_condition_codes(resource)
            for code in codes:
                conn.execute('''
                    INSERT INTO fhir_resources (bundle_id, resource_type, resource_id, patient_reference, 
                                              code_system, code_value, display_name, patient_abha_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (bundle_id, resource_type, resource_id, patient_ref, 
                      code.get('system'), code.get('code'), code.get('display'), abha_id))
        else:
            # Store other resource types
            conn.execute('''
                INSERT INTO fhir_resources (bundle_id, resource_type, resource_id, patient_reference, patient_abha_id)
                VALUES (?, ?, ?, ?, ?)
            ''', (bundle_id, resource_type, resource_id, patient_ref, abha_id))
    
    def _extract_patient_reference(self, resource):
        """Extract patient reference from resource"""
        if resource.get('resourceType') == 'Patient':
            return f"Patient/{resource.get('id')}"
        
        # Check common patient reference fields
        subject = resource.get('subject', {})
        if subject.get('reference'):
            return subject['reference']
        
        patient = resource.get('patient', {})
        if patient.get('reference'):
            return patient['reference']
        
        return None
    
    def _extract_condition_codes(self, condition_resource):
        """Extract codes from Condition resource"""
        codes = []
        
        # Primary code
        code_obj = condition_resource.get('code', {})
        codings = code_obj.get('coding', [])
        
        for coding in codings:
            codes.append({
                'system': coding.get('system'),
                'code': coding.get('code'),
                'display': coding.get('display')
            })
        
        return codes
    
    def _extract_abha_id(self, resource):
        """Extract ABHA ID from FHIR resource"""
        if resource.get('resourceType') == 'Patient':
            identifiers = resource.get('identifier', [])
            for identifier in identifiers:
                if 'healthid.ndhm.gov.in/ABHA' in identifier.get('system', ''):
                    return identifier.get('value')
        return None
    
    def get_bundle_summary(self, bundle_id):
        """Get summary of processed bundle"""
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        
        # Get bundle info
        bundle_cursor = conn.execute('''
            SELECT * FROM fhir_bundles WHERE bundle_id = ?
        ''', (bundle_id,))
        bundle = bundle_cursor.fetchone()
        
        # Get resources summary
        resources_cursor = conn.execute('''
            SELECT resource_type, COUNT(*) as count 
            FROM fhir_resources 
            WHERE bundle_id = ? 
            GROUP BY resource_type
        ''', (bundle_id,))
        resources = resources_cursor.fetchall()
        
        # Get conditions for mapping
        conditions_cursor = conn.execute('''
            SELECT * FROM fhir_resources 
            WHERE bundle_id = ? AND resource_type = 'Condition'
        ''', (bundle_id,))
        conditions = conditions_cursor.fetchall()
        
        conn.close()
        
        return {
            'bundle': dict(bundle) if bundle else None,
            'resources': [dict(r) for r in resources],
            'conditions': [dict(c) for c in conditions]
        }
    
    def map_condition_to_codes(self, resource_id, icd11_code=None, namaste_code=None):
        """Map FHIR condition to ICD-11/NAMASTE codes"""
        conn = sqlite3.connect(self.db_file)
        conn.execute('''
            UPDATE fhir_resources 
            SET mapped_icd11 = ?, mapped_namaste = ?
            WHERE id = ?
        ''', (icd11_code, namaste_code, resource_id))
        conn.commit()
        conn.close()
    
    def get_all_bundles(self):
        """Get all uploaded bundles"""
        # Get from new storage system
        new_bundles = self.bundle_storage.get_all_bundles()
        
        # Also get from legacy system and merge
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        cursor = conn.execute('''
            SELECT bundle_id, bundle_type, total_entries, 
                   COALESCE(upload_date, '2024-01-01 00:00:00') as upload_date, 
                   uploaded_by, status
            FROM fhir_bundles 
            ORDER BY upload_date DESC
        ''')
        legacy_bundles = [dict(row) for row in cursor.fetchall()]
        conn.close()
        
        # Format dates for legacy bundles
        for bundle in legacy_bundles:
            if bundle.get('upload_date'):
                try:
                    from datetime import datetime
                    dt = datetime.strptime(bundle['upload_date'], '%Y-%m-%d %H:%M:%S')
                    bundle['upload_date'] = dt.strftime('%Y-%m-%d %H:%M')
                except:
                    bundle['upload_date'] = 'N/A'
        
        # Merge and deduplicate
        all_bundles = {}
        for bundle in new_bundles + legacy_bundles:
            bundle_id = bundle.get('id') or bundle.get('bundle_id')
            if bundle_id:
                all_bundles[bundle_id] = bundle
        
        return list(all_bundles.values())

    @staticmethod
    def get_sample_fhir_bundle():
        """Generate sample FHIR R4 Bundle for testing"""
        return {
            "resourceType": "Bundle",
            "id": "sample-bundle-001",
            "type": "collection",
            "timestamp": datetime.now().isoformat(),
            "entry": [
                {
                    "resource": {
                        "resourceType": "Patient",
                        "id": "patient-001",
                        "identifier": [
                            {
                                "system": "https://ndhm.gov.in/SwasthID",
                                "value": "1234567890123456"
                            },
                            {
                                "system": "https://healthid.ndhm.gov.in/ABHA",
                                "value": "12345678901234"
                            }
                        ],
                        "name": [
                            {
                                "family": "Sharma",
                                "given": ["Rajesh", "Kumar"]
                            }
                        ],
                        "gender": "male",
                        "birthDate": "1985-06-15",
                        "address": [
                            {
                                "line": ["123 MG Road"],
                                "city": "Mumbai",
                                "state": "Maharashtra",
                                "postalCode": "400001",
                                "country": "IN"
                            }
                        ]
                    }
                },
                {
                    "resource": {
                        "resourceType": "Condition",
                        "id": "condition-001",
                        "subject": {
                            "reference": "Patient/patient-001"
                        },
                        "code": {
                            "coding": [
                                {
                                    "system": "http://snomed.info/sct",
                                    "code": "386661006",
                                    "display": "Fever"
                                },
                                {
                                    "system": "http://hl7.org/fhir/sid/icd-10",
                                    "code": "R50.9",
                                    "display": "Fever, unspecified"
                                }
                            ]
                        },
                        "clinicalStatus": {
                            "coding": [
                                {
                                    "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                                    "code": "active"
                                }
                            ]
                        },
                        "recordedDate": "2024-01-15"
                    }
                },
                {
                    "resource": {
                        "resourceType": "Condition",
                        "id": "condition-002",
                        "subject": {
                            "reference": "Patient/patient-001"
                        },
                        "code": {
                            "coding": [
                                {
                                    "system": "http://snomed.info/sct",
                                    "code": "49727002",
                                    "display": "Cough"
                                }
                            ]
                        },
                        "clinicalStatus": {
                            "coding": [
                                {
                                    "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                                    "code": "active"
                                }
                            ]
                        },
                        "recordedDate": "2024-01-15"
                    }
                },
                {
                    "resource": {
                        "resourceType": "Observation",
                        "id": "observation-001",
                        "status": "final",
                        "category": [
                            {
                                "coding": [
                                    {
                                        "system": "http://terminology.hl7.org/CodeSystem/observation-category",
                                        "code": "vital-signs"
                                    }
                                ]
                            }
                        ],
                        "code": {
                            "coding": [
                                {
                                    "system": "http://loinc.org",
                                    "code": "8310-5",
                                    "display": "Body temperature"
                                }
                            ]
                        },
                        "subject": {
                            "reference": "Patient/patient-001"
                        },
                        "valueQuantity": {
                            "value": 101.5,
                            "unit": "degF",
                            "system": "http://unitsofmeasure.org",
                            "code": "[degF]"
                        }
                    }
                }
            ]
        }