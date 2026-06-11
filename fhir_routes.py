from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from fhir_interop import FHIRInteroperability
import json

# Create Blueprint
fhir_bp = Blueprint('fhir', __name__, url_prefix='/fhir')

# Initialize FHIR system
fhir_system = FHIRInteroperability()

@fhir_bp.route('/')
@login_required
def fhir_dashboard():
    bundles = fhir_system.get_all_bundles()
    return render_template('fhir/dashboard.html', bundles=bundles)

@fhir_bp.route('/upload')
@login_required
def upload_form():
    return render_template('fhir/upload.html')

@fhir_bp.route('/upload', methods=['POST'])
@login_required
def upload_bundle():
    try:
        # Handle JSON API request
        if request.is_json:
            data = request.get_json()
            bundle_data = data.get('bundle_data')
            
            if not bundle_data:
                return jsonify({
                    'status': 'error',
                    'error': 'No bundle data provided'
                }), 400
        
        # Handle form-based upload (legacy support)
        elif 'fhir_file' in request.files:
            file = request.files['fhir_file']
            if file.filename == '':
                return jsonify({
                    'status': 'error',
                    'error': 'No file selected'
                }), 400
            
            try:
                bundle_data = json.load(file)
            except json.JSONDecodeError:
                return jsonify({
                    'status': 'error',
                    'error': 'Invalid JSON file'
                }), 400
        
        elif request.form.get('fhir_json'):
            try:
                bundle_data = json.loads(request.form.get('fhir_json'))
            except json.JSONDecodeError:
                return jsonify({
                    'status': 'error',
                    'error': 'Invalid JSON format'
                }), 400
        
        else:
            return jsonify({
                'status': 'error',
                'error': 'No FHIR data provided'
            }), 400
        
        # Validate FHIR bundle
        validation_errors = fhir_system.validate_fhir_bundle(bundle_data)
        if validation_errors:
            return jsonify({
                'status': 'error',
                'error': 'Validation failed: ' + ', '.join(validation_errors)
            }), 400
        
        # Process bundle
        uploaded_by = getattr(current_user, 'username', None) or getattr(current_user, 'email', 'unknown')
        bundle_id = fhir_system.process_fhir_bundle(bundle_data, uploaded_by)
        
        return jsonify({
            'status': 'success',
            'message': f'FHIR Bundle uploaded successfully! Bundle ID: {bundle_id}',
            'bundle_id': bundle_id
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': f'Error processing FHIR bundle: {str(e)}'
        }), 500

@fhir_bp.route('/bundle/<bundle_id>')
@login_required
def view_bundle(bundle_id):
    summary = fhir_system.get_bundle_summary(bundle_id)
    if not summary['bundle']:
        flash('Bundle not found', 'error')
        return redirect(url_for('fhir.fhir_dashboard'))
    
    return render_template('fhir/bundle_detail.html', summary=summary, bundle_id=bundle_id)

@fhir_bp.route('/sample')
@login_required
def get_sample_bundle():
    sample = fhir_system.get_sample_fhir_bundle()
    return jsonify(sample)

@fhir_bp.route('/map-condition', methods=['POST'])
@login_required
def map_condition():
    try:
        resource_id = request.form.get('resource_id')
        icd11_code = request.form.get('icd11_code', '').strip()
        namaste_code = request.form.get('namaste_code', '').strip()
        
        if not resource_id:
            return jsonify({'error': 'Resource ID required'}), 400
        
        fhir_system.map_condition_to_codes(
            resource_id, 
            icd11_code if icd11_code else None,
            namaste_code if namaste_code else None
        )
        
        return jsonify({'success': True, 'message': 'Condition mapped successfully'})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@fhir_bp.route('/history')
@login_required
def get_upload_history():
    try:
        bundles = fhir_system.get_all_bundles()
        
        # Format bundles for frontend
        formatted_bundles = []
        for bundle in bundles:
            formatted_bundles.append({
                'id': bundle.get('id', 'N/A'),
                'type': bundle.get('type', 'N/A'),
                'entries': bundle.get('entry_count', 0),
                'upload_date': bundle.get('created_at', ''),
                'uploaded_by': bundle.get('uploaded_by', 'Unknown'),
                'status': bundle.get('status', 'unknown')
            })
        
        return jsonify({
            'status': 'success',
            'bundles': formatted_bundles
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'error': str(e)
        }), 500

@fhir_bp.route('/validate', methods=['POST'])
@login_required
def validate_fhir():
    try:
        fhir_data = request.get_json()
        if not fhir_data:
            return jsonify({'valid': False, 'errors': ['No JSON data provided']})
        
        errors = fhir_system.validate_fhir_bundle(fhir_data)
        
        return jsonify({
            'valid': len(errors) == 0,
            'errors': errors
        })
        
    except Exception as e:
        return jsonify({'valid': False, 'errors': [str(e)]})