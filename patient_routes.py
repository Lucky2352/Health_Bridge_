from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, make_response, session
from flask_login import login_required, current_user
from patient_models import PatientDatabase
from abha_validator import ABHAValidator
import csv
import io
from datetime import datetime

# Create Blueprint
patient_bp = Blueprint('patients', __name__, url_prefix='/patients')

# Initialize database
patient_db = PatientDatabase()

@patient_bp.route('/')
@login_required
def patient_list():
    return render_template('patients/list.html')

@patient_bp.route('/add')
@login_required
def add_patient_form():
    return render_template('patients/add.html')

@patient_bp.route('/add', methods=['POST'])
@login_required
def add_patient():
    try:
        abha_id = request.form.get('abha_id', '').strip()
        
        # Validate ABHA ID if provided
        if abha_id:
            is_valid, error_msg = ABHAValidator.validate_abha_id(abha_id)
            if not is_valid:
                flash(f'ABHA ID Error: {error_msg}', 'error')
                return render_template('patients/add.html')
            abha_id = ABHAValidator.clean_abha_id(abha_id)
        
        # Get and validate form data
        name = request.form.get('name', '').strip()
        contact = request.form.get('contact', '').strip()
        age_str = request.form.get('age', '').strip()
        
        # Validation
        if not name:
            flash('Patient name is required', 'error')
            return render_template('patients/add.html')
        
        if not contact:
            flash('Contact number is required', 'error')
            return render_template('patients/add.html')
        
        try:
            age = int(age_str) if age_str else 0
            if age < 0 or age > 150:
                flash('Please enter a valid age between 0 and 150', 'error')
                return render_template('patients/add.html')
        except ValueError:
            flash('Please enter a valid age', 'error')
            return render_template('patients/add.html')
        
        data = {
            'name': name,
            'age': age,
            'gender': request.form.get('gender', ''),
            'contact': contact,
            'email': request.form.get('email', '').strip(),
            'address': request.form.get('address', '').strip(),
            'medical_history': request.form.get('medical_history', '').strip(),
            'allergies': request.form.get('allergies', '').strip(),
            'abha_id': abha_id
        }
        
        # Use username or email as created_by identifier
        created_by = getattr(current_user, 'username', None) or getattr(current_user, 'email', 'unknown')
        patient_id = patient_db.create_patient(data, created_by)
        
        # Store success message in session for patient list display
        session['patient_success'] = f'Patient {patient_id} ({name}) created successfully! You can now manage their records.'
        return redirect(url_for('patients.patient_list'))
        
    except ValueError as ve:
        flash(f'Validation Error: {str(ve)}', 'error')
        return render_template('patients/add.html')
    except Exception as e:
        flash(f'Error creating patient: {str(e)}', 'error')
        return render_template('patients/add.html')

@patient_bp.route('/<patient_id>')
@login_required
def patient_detail(patient_id):
    patient = patient_db.get_patient(patient_id)
    if not patient:
        flash('Patient not found', 'error')
        return redirect(url_for('patients.patient_list'))
    
    # Check if patient belongs to current doctor
    doctor_id = getattr(current_user, 'username', None) or getattr(current_user, 'email', 'unknown')
    if patient.get('created_by') != doctor_id:
        flash('Access denied: This patient does not belong to your account', 'error')
        return redirect(url_for('patients.patient_list'))
    
    diagnoses = patient_db.get_patient_diagnoses(patient_id)
    return render_template('patients/detail.html', patient=patient, diagnoses=diagnoses)

@patient_bp.route('/<patient_id>/edit')
@login_required
def edit_patient_form(patient_id):
    patient = patient_db.get_patient(patient_id)
    if not patient:
        flash('Patient not found', 'error')
        return redirect(url_for('patients.patient_list'))
    
    # Check if patient belongs to current doctor
    doctor_id = getattr(current_user, 'username', None) or getattr(current_user, 'email', 'unknown')
    if patient.get('created_by') != doctor_id:
        flash('Access denied: This patient does not belong to your account', 'error')
        return redirect(url_for('patients.patient_list'))
    
    return render_template('patients/edit.html', patient=patient)

@patient_bp.route('/<patient_id>/edit', methods=['POST'])
@login_required
def edit_patient(patient_id):
    try:
        abha_id = request.form.get('abha_id', '').strip()
        
        # Validate ABHA ID if provided
        if abha_id:
            is_valid, error_msg = ABHAValidator.validate_abha_id(abha_id)
            if not is_valid:
                flash(f'ABHA ID Error: {error_msg}', 'error')
                return redirect(url_for('patients.edit_patient_form', patient_id=patient_id))
            abha_id = ABHAValidator.clean_abha_id(abha_id)
        
        data = {
            'name': request.form.get('name', '').strip(),
            'age': int(request.form.get('age', 0)),
            'gender': request.form.get('gender', ''),
            'contact': request.form.get('contact', '').strip(),
            'email': request.form.get('email', '').strip(),
            'address': request.form.get('address', '').strip(),
            'medical_history': request.form.get('medical_history', '').strip(),
            'allergies': request.form.get('allergies', '').strip(),
            'abha_id': abha_id
        }
        
        patient_db.update_patient(patient_id, data)
        session['patient_success'] = f'Patient {data["name"]} updated successfully!'
        return redirect(url_for('patients.patient_detail', patient_id=patient_id))
        
    except Exception as e:
        flash(f'Error updating patient: {str(e)}', 'error')
        return redirect(url_for('patients.edit_patient_form', patient_id=patient_id))

@patient_bp.route('/<patient_id>/delete', methods=['POST'])
@login_required
def delete_patient(patient_id):
    try:
        patient = patient_db.get_patient(patient_id)
        if not patient:
            flash('Patient not found', 'error')
            return redirect(url_for('patients.patient_list'))
        
        # Check if patient belongs to current doctor
        doctor_id = getattr(current_user, 'username', None) or getattr(current_user, 'email', 'unknown')
        if patient.get('created_by') != doctor_id:
            flash('Access denied: This patient does not belong to your account', 'error')
            return redirect(url_for('patients.patient_list'))
        
        patient_name = patient.get('name', patient_id)
        patient_db.delete_patient(patient_id)
        session['patient_success'] = f'Patient {patient_name} deleted successfully!'
        return redirect(url_for('patients.patient_list'))
    except Exception as e:
        flash(f'Error deleting patient: {str(e)}', 'error')
        return redirect(url_for('patients.patient_list'))

@patient_bp.route('/<patient_id>/diagnosis', methods=['POST'])
@login_required
def add_diagnosis(patient_id):
    try:
        diagnosis_data = {
            'date': request.form.get('date') or datetime.now().date(),
            'symptoms': request.form.get('symptoms', '').strip(),
            'namaste_code': request.form.get('namaste_code', '').strip(),
            'namaste_name': request.form.get('namaste_name', '').strip(),
            'icd11_code': request.form.get('icd11_code', '').strip(),
            'icd11_name': request.form.get('icd11_name', '').strip(),
            'notes': request.form.get('notes', '').strip()
        }
        
        if not diagnosis_data['symptoms']:
            flash('Symptoms are required', 'error')
            return redirect(url_for('patients.patient_detail', patient_id=patient_id))
        
        # Use username or email as created_by identifier
        created_by = getattr(current_user, 'username', None) or getattr(current_user, 'email', 'unknown')
        patient_db.add_diagnosis(patient_id, diagnosis_data, created_by)
        session['patient_success'] = 'Diagnosis added successfully!'
        return redirect(url_for('patients.patient_detail', patient_id=patient_id))
        
    except Exception as e:
        flash(f'Error adding diagnosis: {str(e)}', 'error')
        return redirect(url_for('patients.patient_detail', patient_id=patient_id))

# API Routes
@patient_bp.route('/api/search')
@login_required
def api_search_patients():
    query = request.args.get('q', '')
    filters = {
        'gender': request.args.get('gender'),
        'age_min': request.args.get('age_min', type=int),
        'age_max': request.args.get('age_max', type=int)
    }
    
    # Get doctor identifier
    doctor_id = getattr(current_user, 'username', None) or getattr(current_user, 'email', 'unknown')
    
    # Get all patients and filter by doctor
    all_patients = patient_db.search_patients(query, filters)
    my_patients = [p for p in all_patients if p.get('created_by') == doctor_id]
    
    return jsonify(my_patients)

@patient_bp.route('/api/export/csv')
@login_required
def export_csv():
    # Get doctor identifier
    doctor_id = getattr(current_user, 'username', None) or getattr(current_user, 'email', 'unknown')
    
    # Get only doctor's patients
    all_patients = patient_db.get_all_patients()
    my_patients = [p for p in all_patients if p.get('created_by') == doctor_id]
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Header
    writer.writerow(['Patient ID', 'Name', 'Age', 'Gender', 'Contact', 'Email', 'ABHA ID', 'Medical History', 'Allergies', 'Created Date'])
    
    # Data
    for patient in my_patients:
        writer.writerow([
            patient['patient_id'], patient['name'], patient['age'], patient['gender'],
            patient['contact'], patient['email'], patient.get('abha_id', ''),
            patient['medical_history'], patient['allergies'], patient['created_at']
        ])
    
    output.seek(0)
    
    response = make_response(output.getvalue())
    response.headers['Content-Type'] = 'text/csv'
    response.headers['Content-Disposition'] = f'attachment; filename=my_patients_{datetime.now().strftime("%Y%m%d")}.csv'
    
    return response