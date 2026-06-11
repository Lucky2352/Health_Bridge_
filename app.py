from flask import Flask, request, jsonify, render_template, redirect, url_for
from flask_login import LoginManager, login_required, current_user
from enhanced_routes import enhanced_auth_bp
from enhanced_auth import EnhancedAuthDB
from patient_routes import patient_bp
from fhir_routes import fhir_bp
from reports_routes import reports_bp
from utils.namaste_service import get_namaste_service
from database import Database
from fhir_service import FHIRService
from fhir_codesystem import FHIRCodeSystem
from fhir_conceptmap import ConceptMapper
from jwt_auth import jwt_required
from auth_service import AuthService
from icd11_api import search_icd11, configure_icd_api
import uuid
import re
import os
import logging

logger = logging.getLogger(__name__)

app = Flask(__name__)
app.static_folder = 'static'
app.template_folder = 'templates'
app.secret_key = os.getenv('SECRET_KEY', 'your-secret-key-change-in-production')

# Initialize Flask-Login
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'enhanced_auth.login'
login_manager.login_message = 'Please log in to access this page.'

# Register enhanced authentication blueprint
app.register_blueprint(enhanced_auth_bp)

# Register patient management blueprint
app.register_blueprint(patient_bp)

# Register FHIR interoperability blueprint
app.register_blueprint(fhir_bp)

# Register reports & analytics blueprint
app.register_blueprint(reports_bp)

# Initialize enhanced auth database
enhanced_db = EnhancedAuthDB()

@login_manager.user_loader
def load_user(user_id):
    try:
        return enhanced_db.get_user_by_id(int(user_id))
    except (ValueError, TypeError):
        # Handle old string-based user IDs
        return None

# Initialize services
namaste_service = get_namaste_service('namaste_codes.csv')
db = Database()
auth = AuthService()
concept_mapper = ConceptMapper(namaste_service, search_icd11)

# Configure ICD-11 API with your WHO credentials
configure_icd_api(
    client_id=os.getenv('ICD11_CLIENT_ID', 'your-client-id-here'),
    client_secret=os.getenv('ICD11_CLIENT_SECRET', 'your-client-secret-here')
)

@app.route('/icd11/search')
@login_required
def search_icd():
    query = request.args.get('q', '').strip()
    format_type = request.args.get('format', '').lower()
    
    if not query:
        return jsonify({'error': 'Query parameter q is required'}), 400
    
    if len(query) < 2:
        return jsonify({'error': 'Query must be at least 2 characters'}), 400
    
    results = search_icd11(query)
    
    if format_type == 'fhir':
        return jsonify(FHIRCodeSystem.create_icd11_codesystem(results))
    
    return jsonify(results)

@app.route('/namaste/status')
@login_required
def namaste_status():
    """Get NAMASTE service status and configuration"""
    api_key = os.getenv('NAMASTE_API_KEY')
    
    status = {
        'api_configured': bool(api_key),
        'api_key_preview': f"{api_key[:10]}..." if api_key else None,
        'csv_fallback_available': os.path.exists('namaste_codes.csv'),
        'service_ready': True
    }
    
    # Test a simple query to check service health
    try:
        test_response = namaste_service.get_namaste_codes('fever')
        status['last_test'] = {
            'query': 'fever',
            'source': test_response.get('source'),
            'results_count': len(test_response.get('results', [])),
            'message': test_response.get('message')
        }
    except Exception as e:
        status['last_test'] = {
            'error': str(e)
        }
        status['service_ready'] = False
    
    return jsonify(status)

@app.route('/translate_code')
@login_required
def translate_code():
    """Fast translate between ICD-11 and NAMASTE codes"""
    code = request.args.get('code', '').strip()
    system = request.args.get('system', '').strip().lower()
    
    if not code:
        return jsonify({'success': False, 'message': 'Code parameter is required'}), 400
    
    # Static mapping for fast translation
    namaste_to_icd = {
        'NAM-AYU-002': {'code': 'MD11.9', 'name': 'Fever, unspecified'},
        'NAM-AYU-008': {'code': 'MD11.9', 'name': 'Fever, unspecified'},
        'NAM-UNA-001': {'code': 'MD11.9', 'name': 'Fever, unspecified'},
        'NAM-SID-001': {'code': 'MD11.9', 'name': 'Fever, unspecified'},
        'NAM-HOM-001': {'code': 'MD11.9', 'name': 'Fever, unspecified'},
        'NAM-AYU-003': {'code': 'MD12.0', 'name': 'Cough'},
        'NAM-UNA-002': {'code': 'MD12.0', 'name': 'Cough'},
        'NAM-SID-002': {'code': 'MD12.0', 'name': 'Cough'},
        'NAM-HOM-002': {'code': 'MD12.0', 'name': 'Cough'},
        'NAM-AYU-004': {'code': '5A11', 'name': 'Type 2 diabetes mellitus'},
        'NAM-UNA-003': {'code': '5A11', 'name': 'Type 2 diabetes mellitus'},
        'NAM-SID-003': {'code': '5A11', 'name': 'Type 2 diabetes mellitus'},
        'NAM-HOM-003': {'code': '5A11', 'name': 'Type 2 diabetes mellitus'},
        'NAM-AYU-001': {'code': 'FA20.0', 'name': 'Rheumatoid arthritis'},
        'NAM-UNA-004': {'code': 'FA20.0', 'name': 'Rheumatoid arthritis'},
        'NAM-AYU-005': {'code': 'CA23.0', 'name': 'Asthma'},
    }
    
    # Reverse mapping
    icd_to_namaste = {v['code']: k for k, v in namaste_to_icd.items()}
    
    try:
        csv_data = getattr(namaste_service, 'csv_data', [])
        
        if system == 'namaste' or code.startswith('NAM-'):
            # NAMASTE to ICD-11
            source_concept = next((row for row in csv_data if row.get('code') == code), None)
            if not source_concept:
                return jsonify({'success': False, 'message': f'NAMASTE code {code} not found'})
            
            if code in namaste_to_icd:
                target = namaste_to_icd[code]
                return jsonify({
                    'success': True,
                    'source': {'code': code, 'name': source_concept['name'], 'system': 'NAMASTE'},
                    'target': {'code': target['code'], 'name': target['name'], 'system': 'ICD-11'}
                })
            else:
                return jsonify({'success': False, 'message': f'No ICD-11 mapping for {code}'})
        
        else:
            # ICD-11 to NAMASTE
            if code in icd_to_namaste:
                namaste_code = icd_to_namaste[code]
                namaste_concept = next((row for row in csv_data if row.get('code') == namaste_code), None)
                if namaste_concept:
                    return jsonify({
                        'success': True,
                        'source': {'code': code, 'name': namaste_to_icd[namaste_code]['name'], 'system': 'ICD-11'},
                        'target': {'code': namaste_code, 'name': namaste_concept['name'], 'system': 'NAMASTE'}
                    })
            
            # Try semantic matching for common terms
            code_lower = code.lower()
            if 'fever' in code_lower or 'pyrexia' in code_lower:
                fever_code = next((row for row in csv_data if 'jwara' in row.get('name', '').lower()), None)
                if fever_code:
                    return jsonify({
                        'success': True,
                        'source': {'code': code, 'name': 'Fever condition', 'system': 'ICD-11'},
                        'target': {'code': fever_code['code'], 'name': fever_code['name'], 'system': 'NAMASTE'}
                    })
            
            return jsonify({'success': False, 'message': f'No NAMASTE mapping for {code}'})
    
    except Exception as e:
        return jsonify({'success': False, 'message': f'Translation error: {str(e)}'}), 500

@app.route('/patient/api/dashboard-stats')
@login_required
def patient_dashboard_stats():
    """Get dashboard statistics for the logged-in patient"""
    if not hasattr(current_user, 'role') or current_user.role != 'patient':
        return jsonify({'error': 'Patient access required'}), 403
    
    if not current_user.patient_id:
        return jsonify({'error': 'Patient ID not found'}), 400
    
    try:
        from diagnosis_models import DiagnosisDatabase
        diagnosis_db = DiagnosisDatabase()
        
        # Get data for current patient using patient_id
        diagnoses = diagnosis_db.get_patient_diagnoses(current_user.patient_id)
        prescriptions = diagnosis_db.get_patient_prescriptions(current_user.patient_id)
        appointments = diagnosis_db.get_patient_appointments(current_user.patient_id)
        
        stats = {
            'records': len(diagnoses),
            'appointments': len(appointments),
            'prescriptions': len(prescriptions),
            'visits': len(diagnoses),
            'recent_records': [
                {
                    'date': d.get('created_at', 'Unknown')[:10] if d.get('created_at') else 'Unknown',
                    'condition': d.get('condition_name', 'General consultation'),
                    'doctor': d.get('doctor_name', 'Unknown Doctor')
                } for d in diagnoses[-3:]  # Last 3 records
            ]
        }
        
        return jsonify(stats)
        
    except Exception as e:
        return jsonify({
            'records': 0,
            'appointments': 0,
            'prescriptions': 0,
            'visits': 0,
            'recent_records': []
        })

@app.route('/patient/records')
@login_required
def patient_records():
    if not hasattr(current_user, 'role') or current_user.role != 'patient':
        return redirect(url_for('enhanced_auth.dashboard'))
    try:
        return render_template('patient_records.html')
    except Exception as e:
        return f"Error loading records: {str(e)}", 500

@app.route('/patient/api/diagnoses')
@login_required
def get_patient_diagnoses():
    """Get all diagnoses for the logged-in patient"""
    if not hasattr(current_user, 'role') or current_user.role != 'patient':
        return jsonify({'error': 'Patient access required'}), 403
    
    if not current_user.patient_id:
        return jsonify({'error': 'Patient ID not found'}), 400
    
    try:
        from diagnosis_models import DiagnosisDatabase
        diagnosis_db = DiagnosisDatabase()
        
        diagnoses = diagnosis_db.get_patient_diagnoses(current_user.patient_id)
        
        return jsonify({
            'success': True,
            'diagnoses': diagnoses
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@app.route('/patient/appointments')
@login_required
def patient_appointments():
    if not hasattr(current_user, 'role') or current_user.role != 'patient':
        return redirect(url_for('enhanced_auth.dashboard'))
    try:
        return render_template('patient_appointments.html')
    except Exception as e:
        return f"Error loading appointments: {str(e)}", 500

@app.route('/patient/prescriptions')
@login_required
def patient_prescriptions():
    if not hasattr(current_user, 'role') or current_user.role != 'patient':
        return redirect(url_for('enhanced_auth.dashboard'))
    try:
        return render_template('patient_prescriptions.html')
    except Exception as e:
        return f"Error loading prescriptions: {str(e)}", 500

@app.route('/patient/history')
@login_required
def patient_history():
    if not hasattr(current_user, 'role') or current_user.role != 'patient':
        return redirect(url_for('enhanced_auth.dashboard'))
    try:
        return render_template('patient_history.html')
    except Exception as e:
        return f"Error loading history: {str(e)}", 500

@app.route('/patient/profile')
@login_required
def patient_profile():
    if not hasattr(current_user, 'role') or current_user.role != 'patient':
        return redirect(url_for('enhanced_auth.dashboard'))
    try:
        return render_template('patient_profile.html')
    except Exception as e:
        return f"Error loading profile: {str(e)}", 500

@app.route('/search')
@login_required
def unified_search():
    query = request.args.get('q', '').strip()
    format_type = request.args.get('format', '').lower()
    
    if not query:
        return jsonify({'error': 'Query parameter q is required'}), 400
    
    # Log search operation
    user_id = getattr(current_user, 'username', None) or getattr(current_user, 'email', 'unknown')
    db.log_search_operation(user_id, query, 'unified_search')
    
    # Step 1: Search NAMASTE codes (API + CSV fallback)
    namaste_response = namaste_service.get_namaste_codes(query)
    namaste_results = namaste_response.get('results', [])
    
    # Step 2: Search ICD-11 via WHO API
    icd11_results = search_icd11(query)
    
    # Step 3: Return FHIR format if requested
    if format_type == 'fhir':
        return jsonify(FHIRCodeSystem.create_search_valueset(query, namaste_results, icd11_results))
    
    # Step 4: Default JSON format with source info
    return jsonify({
        'namaste': namaste_results,
        'namaste_source': namaste_response.get('source', 'unknown'),
        'namaste_message': namaste_response.get('message', ''),
        'icd11': icd11_results
    })

@app.route('/diagnosis', methods=['POST'])
@login_required
def add_diagnosis():
    """Add diagnosis with proper doctor-patient relationship"""
    if not hasattr(current_user, 'role') or current_user.role != 'doctor':
        current_role = getattr(current_user, 'role', 'unknown')
        return jsonify({
            'status': 'error', 
            'error': f'Only doctors can add diagnoses. You are logged in as: {current_role}. Please login with a doctor account.'
        }), 403
    
    if not current_user.doctor_id:
        return jsonify({
            'status': 'error',
            'error': 'Doctor ID not found. Please contact administrator to assign doctor ID.'
        }), 400
    
    try:
        from diagnosis_models import DiagnosisDatabase
        diagnosis_db = DiagnosisDatabase()
        
        data = request.get_json()
        if not data or not data.get('patient_id') or not data.get('condition_name'):
            return jsonify({
                'status': 'error',
                'error': 'patient_id and condition_name are required'
            }), 400
        
        # Get patient by patient_id, email, or username
        patient_identifier = data['patient_id']
        patient_user = None
        
        # Get list of available patients for debugging
        from diagnosis_models import DiagnosisDatabase
        diagnosis_db = DiagnosisDatabase()
        available_patients = diagnosis_db.get_all_patients()
        available_ids = [p['patient_id'] for p in available_patients]
        
        # Try different lookup methods
        if patient_identifier.startswith('P') and len(patient_identifier) == 5:
            # Patient ID format (P0001)
            patient_user = enhanced_db.get_user_by_patient_id(patient_identifier)
        elif '@' in patient_identifier:
            # Email
            patient_user = enhanced_db.get_user_by_email(patient_identifier)
        else:
            # Username
            patient_user = enhanced_db.get_user_by_username(patient_identifier)
        
        if not patient_user or patient_user.role != 'patient':
            return jsonify({
                'status': 'error',
                'error': f'Patient not found: "{patient_identifier}". Available patient IDs: {available_ids}'
            }), 400
        
        # Validate doctor can add diagnosis for this patient
        if not diagnosis_db.validate_doctor_patient_relationship(current_user.id, patient_user.patient_id):
            return jsonify({
                'status': 'error',
                'error': 'Not authorized to add diagnosis for this patient'
            }), 403
        
        # Prepare diagnosis data
        condition_code = data.get('namaste_code') or data.get('icd11_code')
        condition_name = data.get('condition_name') or data.get('symptom')
        notes = data.get('notes', '')
        
        # Add diagnosis using doctor_id and patient_id
        diagnosis_id = diagnosis_db.add_diagnosis(
            doctor_id=current_user.doctor_id,
            patient_id=patient_user.patient_id,
            condition_name=condition_name,
            condition_code=condition_code,
            notes=notes
        )
        
        return jsonify({
            'status': 'success',
            'message': f'Diagnosis saved successfully for {patient_user.full_name} ({patient_user.patient_id})',
            'diagnosis_id': diagnosis_id
        })
        
    except Exception as e:
        logger.error(f"Error adding diagnosis: {e}")
        return jsonify({
            'status': 'error',
            'error': f'Failed to save diagnosis: {str(e)}'
        }), 500

@app.route('/patients/<patient_id>/fhir')
@login_required
def get_patient_fhir(patient_id):
    try:
        from patient_models import PatientDatabase
        patient_db = PatientDatabase()
        
        # Get patient info
        patient = patient_db.get_patient(patient_id)
        if not patient:
            return jsonify({'error': 'Patient not found'}), 404
        
        # Convert to FHIR Patient resource
        fhir_patient = FHIRService.create_patient_resource(patient)
        
        return jsonify(fhir_patient)
        
    except Exception as e:
        return jsonify({'error': f'FHIR conversion failed: {str(e)}'}), 500

@app.route('/patient/<patient_id>/history')
@login_required
def get_patient_history(patient_id):
    try:
        from patient_models import PatientDatabase
        patient_db = PatientDatabase()
        
        # Get patient info first to verify it exists
        patient = patient_db.get_patient(patient_id)
        if not patient:
            return jsonify({'error': 'Patient not found'}), 404
        
        # Get diagnosis records from patient database
        patient_records = patient_db.get_patient_diagnoses(patient_id)
        
        # Also get records from the old diagnosis database for compatibility
        old_records = db.get_patient_history(patient_id)
        
        # Combine and format records
        all_records = []
        
        # Add patient database records
        for record in patient_records:
            all_records.append({
                'id': record.get('id'),
                'timestamp': record.get('diagnosis_date') or record.get('created_at'),
                'symptom': record.get('symptoms'),
                'namaste_code': record.get('namaste_code'),
                'icd11_code': record.get('icd11_code'),
                'notes': record.get('notes'),
                'source': 'patient_db'
            })
        
        # Add old database records
        for record in old_records:
            all_records.append({
                'id': record.get('id'),
                'timestamp': record.get('timestamp'),
                'symptom': record.get('symptom'),
                'namaste_code': record.get('namaste_code'),
                'icd11_code': record.get('icd11_code'),
                'notes': None,
                'source': 'diagnosis_db'
            })
        
        # Sort by timestamp (newest first)
        all_records.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        
        # Check if FHIR format is requested
        format_type = request.args.get('format', '').lower()
        
        if format_type == 'fhir':
            if len(all_records) == 0:
                return jsonify({
                    "resourceType": "Bundle",
                    "id": str(uuid.uuid4()),
                    "type": "searchset",
                    "timestamp": datetime.now().isoformat(),
                    "total": 0,
                    "entry": [],
                    "issue": {
                        "severity": "information",
                        "code": "not-found",
                        "details": {
                            "text": "No FHIR data available for this patient."
                        }
                    }
                })
            else:
                return jsonify(FHIRService.create_bundle(patient_id, all_records, patient))
        
        # Default: return plain JSON format
        return jsonify({
            'patient_id': patient_id,
            'patient_name': patient.get('name'),
            'records': all_records
        })
        
    except Exception as e:
        return jsonify({'error': f'Failed to load patient history: {str(e)}'}), 500

@app.route('/')
@login_required
def index():
    # Always redirect to enhanced dashboard for authenticated users
    if current_user.is_authenticated:
        return redirect(url_for('enhanced_auth.dashboard'))
    else:
        return redirect(url_for('enhanced_auth.login'))

@app.route('/search-page')
@login_required
def search_page():
    return render_template('search.html')

@app.route('/diagnosis-page')
@login_required
def diagnosis_page():
    return render_template('diagnosis.html')

@app.route('/history-page')
@login_required
def history_page():
    return render_template('history.html')

@app.route('/fhir/CodeSystem/namaste')
@login_required
def namaste_codesystem():
    """Return complete NAMASTE CodeSystem"""
    csv_data = getattr(namaste_service, 'csv_data', [])
    return jsonify(FHIRCodeSystem.create_namaste_codesystem(csv_data))

@app.route('/fhir/CodeSystem/icd11')
@login_required
def icd11_codesystem():
    """Return ICD-11 CodeSystem for a query"""
    query = request.args.get('q', 'fever')
    results = search_icd11(query)
    return jsonify(FHIRCodeSystem.create_icd11_codesystem(results))

@app.route('/fhir/ValueSet/<query>')
@login_required
def search_valueset(query):
    """Return ValueSet for search query"""
    namaste_results = namaste_service.search(query)
    icd11_results = search_icd11(query)
    return jsonify(FHIRCodeSystem.create_search_valueset(query, namaste_results, icd11_results))

@app.route('/fhir/ConceptMap')
@login_required
def get_conceptmap():
    """Return complete NAMASTE to ICD-11 ConceptMap"""
    mappings = concept_mapper.get_all_mappings()
    return jsonify(FHIRConceptMap.create_conceptmap(mappings))

@app.route('/conceptmap/translate')
@login_required
def translate_concept():
    """Translate NAMASTE code to ICD-11"""
    code = request.args.get('code', '').strip()
    
    if not code:
        return jsonify({'error': 'Code parameter is required'}), 400
    
    # Log translation operation
    user_id = getattr(current_user, 'username', None) or getattr(current_user, 'email', 'unknown')
    db.log_search_operation(user_id, code, 'code_translation')
    
    # Get source concept details
    source_concept = None
    csv_data = getattr(namaste_service, 'csv_data', [])
    for row in csv_data:
        if row.get('code') == code:
            source_concept = row
            break
    
    if not source_concept:
        return jsonify({'error': 'NAMASTE code not found'}), 404
    
    # Translate to ICD-11
    target_mappings = concept_mapper.translate_code(code)
    
    return jsonify(FHIRConceptMap.create_translation_response(
        code, 
        source_concept['name'], 
        target_mappings
    ))

@app.route('/valueset/lookup')
@login_required
def valueset_lookup():
    """FHIR ValueSet $lookup operation"""
    query = request.args.get('q', '').strip()
    
    if not query:
        return jsonify({'error': 'Query parameter q is required'}), 400
    
    # Search both NAMASTE and ICD-11
    namaste_results = namaste_service.search(query)
    icd11_results = search_icd11(query)
    
    # Create FHIR Parameters response
    parameters = [
        {
            "name": "result",
            "valueBoolean": len(namaste_results) > 0 or len(icd11_results) > 0
        },
        {
            "name": "display",
            "valueString": f"Lookup results for '{query}'"
        }
    ]
    
    # Add NAMASTE results
    for result in namaste_results:
        parameters.append({
            "name": "designation",
            "part": [
                {
                    "name": "language",
                    "valueCode": "en"
                },
                {
                    "name": "use",
                    "valueCoding": {
                        "system": "http://terminology.hl7.org/CodeSystem/designation-usage",
                        "code": "display"
                    }
                },
                {
                    "name": "value",
                    "valueString": result['name']
                }
            ]
        })
        
        parameters.append({
            "name": "property",
            "part": [
                {
                    "name": "code",
                    "valueCode": "concept"
                },
                {
                    "name": "valueCoding",
                    "valueCoding": {
                        "system": "http://namaste.gov.in/fhir/CodeSystem/ayush-codes",
                        "code": result['code'],
                        "display": result['name']
                    }
                }
            ]
        })
    
    # Add ICD-11 results
    for result in icd11_results:
        # Clean HTML tags from display name
        clean_name = re.sub(r'<[^>]+>', '', result['name'])
        
        parameters.append({
            "name": "designation",
            "part": [
                {
                    "name": "language",
                    "valueCode": "en"
                },
                {
                    "name": "use",
                    "valueCoding": {
                        "system": "http://terminology.hl7.org/CodeSystem/designation-usage",
                        "code": "display"
                    }
                },
                {
                    "name": "value",
                    "valueString": clean_name
                }
            ]
        })
        
        parameters.append({
            "name": "property",
            "part": [
                {
                    "name": "code",
                    "valueCode": "concept"
                },
                {
                    "name": "valueCoding",
                    "valueCoding": {
                        "system": "http://id.who.int/icd/release/11/mms",
                        "code": result['code'],
                        "display": clean_name
                    }
                }
            ]
        })
    
    return jsonify({
        "resourceType": "Parameters",
        "id": str(uuid.uuid4()),
        "parameter": parameters
    })

@app.route('/translate')
@login_required
def fhir_translate():
    """FHIR $translate operation for NAMASTE to ICD-11 TM2"""
    system = request.args.get('system', '').strip().lower()
    code = request.args.get('code', '').strip()
    
    if not system or not code:
        return jsonify({'error': 'Both system and code parameters are required'}), 400
    
    if system != 'namaste':
        return jsonify({'error': 'Only NAMASTE system is supported for translation'}), 400
    
    # Find NAMASTE code
    source_concept = None
    csv_data = getattr(namaste_service, 'csv_data', [])
    for row in csv_data:
        if row.get('code') == code:
            source_concept = row
            break
    
    if not source_concept:
        return jsonify({
            "resourceType": "Parameters",
            "id": str(uuid.uuid4()),
            "parameter": [
                {
                    "name": "result",
                    "valueBoolean": False
                },
                {
                    "name": "message",
                    "valueString": f"NAMASTE code '{code}' not found"
                }
            ]
        }), 404
    
    # Translate using ConceptMapper
    target_mappings = concept_mapper.translate_code(code)
    
    if not target_mappings:
        return jsonify({
            "resourceType": "Parameters",
            "id": str(uuid.uuid4()),
            "parameter": [
                {
                    "name": "result",
                    "valueBoolean": False
                },
                {
                    "name": "message",
                    "valueString": f"No ICD-11 TM2 mapping found for NAMASTE code '{code}'"
                }
            ]
        })
    
    # Create successful translation response
    parameters = [
        {
            "name": "result",
            "valueBoolean": True
        },
        {
            "name": "message",
            "valueString": "Translation successful"
        }
    ]
    
    # Add each mapping as a match
    for mapping in target_mappings:
        parameters.append({
            "name": "match",
            "part": [
                {
                    "name": "equivalence",
                    "valueCode": mapping['equivalence']
                },
                {
                    "name": "concept",
                    "valueCoding": {
                        "system": "http://id.who.int/icd/release/11/mms/tm2",
                        "code": mapping['target_code'],
                        "display": mapping['target_display']
                    }
                },
                {
                    "name": "source",
                    "valueCoding": {
                        "system": "http://namaste.gov.in/fhir/CodeSystem/ayush-codes",
                        "code": code,
                        "display": source_concept['name']
                    }
                }
            ]
        })
    
    return jsonify({
        "resourceType": "Parameters",
        "id": str(uuid.uuid4()),
        "parameter": parameters
    })

@app.route('/dashboard')
@login_required
def dashboard():
    """Redirect to enhanced dashboard"""
    return redirect(url_for('enhanced_auth.dashboard'))

@app.route('/login')
def login_redirect():
    """Redirect to enhanced login"""
    return redirect(url_for('enhanced_auth.login'))

@app.route('/auth/token', methods=['POST'])
def get_jwt_token():
    """Get JWT token for API access"""
    data = request.get_json()
    
    if not data or not data.get('username') or not data.get('password'):
        return jsonify({'error': 'Username and password required'}), 400
    
    # Validate credentials
    if auth.validate_user(data['username'], data['password']):
        token = JWTAuth.generate_token(data['username'])
        return jsonify({
            'access_token': token,
            'token_type': 'Bearer',
            'expires_in': 86400  # 24 hours
        })
    else:
        return jsonify({'error': 'Invalid credentials'}), 401

@app.route('/bundle/upload', methods=['POST'])
@jwt_required
def upload_bundle():
    """Upload and validate FHIR Bundle"""
    try:
        bundle_data = request.get_json()
        
        if not bundle_data:
            return jsonify(FHIROperationOutcome.create_error(
                ['Request body must contain valid JSON']
            )), 400
        
        # Validate bundle structure
        validation_errors = FHIRBundleValidator.validate_bundle(bundle_data)
        
        if validation_errors:
            return jsonify(FHIROperationOutcome.create_error(validation_errors)), 400
        
        # Store bundle
        bundle_id = bundle_storage.store_bundle(
            bundle_data, 
            uploaded_by=request.jwt_user,
            validation_status='valid'
        )
        
        return jsonify(FHIROperationOutcome.create_success(
            f"Bundle uploaded successfully with ID: {bundle_id}"
        )), 201
        
    except Exception as e:
        return jsonify(FHIROperationOutcome.create_error(
            [f"Internal server error: {str(e)}"]
        )), 500

if __name__ == '__main__':
    app.run(debug=True, port=8000)