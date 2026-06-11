import uuid
import json
import sqlite3
from datetime import datetime

class FHIRBundleValidator:
    @staticmethod
    def validate_bundle(bundle_data):
        """Validate FHIR Bundle structure"""
        errors = []
        
        # Check resourceType
        if bundle_data.get('resourceType') != 'Bundle':
            errors.append("Resource must be of type 'Bundle'")
            return errors
        
        # Check required fields
        if 'id' not in bundle_data:
            errors.append("Bundle must have an 'id' field")
        
        if 'type' not in bundle_data:
            errors.append("Bundle must have a 'type' field")
        
        # Check entry array
        entries = bundle_data.get('entry', [])
        if not isinstance(entries, list):
            errors.append("Bundle 'entry' must be an array")
            return errors
        
        # Validate each entry
        for i, entry in enumerate(entries):
            resource = entry.get('resource', {})
            
            # Check if it's a Condition resource
            if resource.get('resourceType') == 'Condition':
                condition_errors = FHIRBundleValidator._validate_condition(resource, i)
                errors.extend(condition_errors)
        
        return errors
    
    @staticmethod
    def _validate_condition(condition, index):
        """Validate Condition resource"""
        errors = []
        prefix = f"Entry[{index}].resource"
        
        # Check required fields
        if 'id' not in condition:
            errors.append(f"{prefix}: Condition must have an 'id'")
        
        if 'subject' not in condition:
            errors.append(f"{prefix}: Condition must have a 'subject'")
        
        # Check code field
        code = condition.get('code', {})
        if not code:
            errors.append(f"{prefix}: Condition must have a 'code'")
        else:
            codings = code.get('coding', [])
            if not codings:
                errors.append(f"{prefix}: Condition.code must have 'coding' array")
            else:
                # Check for NAMASTE or ICD-11 codes
                has_namaste = False
                has_icd11 = False
                
                for coding in codings:
                    system = coding.get('system', '')
                    if 'namaste' in system.lower():
                        has_namaste = True
                    elif 'icd' in system.lower():
                        has_icd11 = True
                
                if not (has_namaste or has_icd11):
                    errors.append(f"{prefix}: Condition must have NAMASTE or ICD-11 coding")
        
        return errors

class FHIRBundleStorage:
    def __init__(self, db_file='fhir_bundles.db'):
        self.db_file = db_file
        self._init_db()
    
    def _init_db(self):
        """Initialize bundle storage database"""
        conn = sqlite3.connect(self.db_file)
        conn.execute('''
            CREATE TABLE IF NOT EXISTS fhir_bundles (
                id TEXT PRIMARY KEY,
                bundle_data TEXT NOT NULL,
                bundle_type TEXT,
                entry_count INTEGER DEFAULT 0,
                uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                uploaded_by TEXT,
                validation_status TEXT DEFAULT 'valid'
            )
        ''')
        
        # Add new columns if they don't exist (for existing databases)
        try:
            conn.execute('ALTER TABLE fhir_bundles ADD COLUMN bundle_type TEXT')
        except sqlite3.OperationalError:
            pass
        
        try:
            conn.execute('ALTER TABLE fhir_bundles ADD COLUMN entry_count INTEGER DEFAULT 0')
        except sqlite3.OperationalError:
            pass
        
        conn.commit()
        conn.close()
    
    def store_bundle(self, bundle_data, uploaded_by='system', validation_status='valid'):
        """Store FHIR Bundle"""
        bundle_id = bundle_data.get('id', str(uuid.uuid4()))
        bundle_type = bundle_data.get('type', 'unknown')
        entry_count = len(bundle_data.get('entry', []))
        
        conn = sqlite3.connect(self.db_file)
        conn.execute('''
            INSERT OR REPLACE INTO fhir_bundles 
            (id, bundle_data, bundle_type, entry_count, uploaded_by, validation_status) 
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (bundle_id, json.dumps(bundle_data), bundle_type, entry_count, uploaded_by, validation_status))
        conn.commit()
        conn.close()
        
        return bundle_id
    
    def get_all_bundles(self):
        """Get all stored bundles with metadata"""
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        
        cursor = conn.execute('''
            SELECT id, bundle_type, entry_count, uploaded_at, uploaded_by, validation_status
            FROM fhir_bundles 
            ORDER BY uploaded_at DESC
        ''')
        
        bundles = []
        for row in cursor.fetchall():
            # Format upload date
            upload_date = 'N/A'
            if row['uploaded_at']:
                try:
                    from datetime import datetime
                    dt = datetime.fromisoformat(row['uploaded_at'].replace('Z', '+00:00'))
                    upload_date = dt.strftime('%Y-%m-%d %H:%M')
                except:
                    upload_date = str(row['uploaded_at'])[:16]
            
            bundles.append({
                'id': row['id'],
                'bundle_id': row['id'],  # For compatibility
                'type': row['bundle_type'],
                'bundle_type': row['bundle_type'],  # For compatibility
                'entry_count': row['entry_count'],
                'total_entries': row['entry_count'],  # For compatibility
                'created_at': row['uploaded_at'],
                'upload_date': upload_date,
                'uploaded_by': row['uploaded_by'],
                'status': row['validation_status']
            })
        
        conn.close()
        return bundles
    
    def get_bundle(self, bundle_id):
        """Get specific bundle by ID"""
        conn = sqlite3.connect(self.db_file)
        conn.row_factory = sqlite3.Row
        
        cursor = conn.execute('''
            SELECT * FROM fhir_bundles WHERE id = ?
        ''', (bundle_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {
                'id': row['id'],
                'bundle_data': json.loads(row['bundle_data']),
                'type': row['bundle_type'],
                'entry_count': row['entry_count'],
                'uploaded_at': row['uploaded_at'],
                'uploaded_by': row['uploaded_by'],
                'status': row['validation_status']
            }
        return None

class FHIROperationOutcome:
    @staticmethod
    def create_success(message="Bundle processed successfully"):
        """Create success OperationOutcome"""
        return {
            "resourceType": "OperationOutcome",
            "id": str(uuid.uuid4()),
            "issue": [
                {
                    "severity": "information",
                    "code": "informational",
                    "details": {
                        "text": message
                    }
                }
            ]
        }
    
    @staticmethod
    def create_error(errors):
        """Create error OperationOutcome"""
        issues = []
        
        for error in errors:
            issues.append({
                "severity": "error",
                "code": "invalid",
                "details": {
                    "text": error
                }
            })
        
        return {
            "resourceType": "OperationOutcome",
            "id": str(uuid.uuid4()),
            "issue": issues
        }