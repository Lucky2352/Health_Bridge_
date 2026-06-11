from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, make_response, send_file
from flask_login import login_required, current_user
from analytics_engine import AnalyticsEngine
from pandas_analytics import PandasAnalytics
from datetime import datetime
import json
from io import BytesIO
from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors

# Create Blueprint
reports_bp = Blueprint('reports', __name__, url_prefix='/reports')

# Initialize analytics engines
analytics = AnalyticsEngine()
pandas_analytics = PandasAnalytics()

@reports_bp.route('/')
@login_required
def reports_dashboard():
    """Main reports dashboard"""
    user_role = getattr(current_user, 'role', 'doctor')
    doctor_id = getattr(current_user, 'username', None) or getattr(current_user, 'email', 'unknown')
    
    # Fallback for missing role
    if not user_role or user_role == 'patient':
        user_role = 'doctor'
    
    # Get analytics data filtered by doctor
    dashboard_data = analytics.get_dashboard_analytics(user_role, doctor_id)
    fhir_data = analytics.get_fhir_analytics(user_role, doctor_id)
    
    return render_template('reports/dashboard.html', 
                         analytics=dashboard_data, 
                         fhir_analytics=fhir_data,
                         user_role=user_role)

@reports_bp.route('/api/analytics')
@login_required
def api_analytics():
    """API endpoint for analytics data"""
    user_role = getattr(current_user, 'role', 'patient')
    user_id = getattr(current_user, 'id', None)
    
    dashboard_data = analytics.get_dashboard_analytics(user_role, user_id)
    fhir_data = analytics.get_fhir_analytics(user_role, user_id)
    
    return jsonify({
        'dashboard': dashboard_data,
        'fhir': fhir_data,
        'user_role': user_role
    })

@reports_bp.route('/export/excel')
@login_required
def export_excel():
    """Export analytics to Excel"""
    user_role = getattr(current_user, 'role', 'patient')
    user_id = getattr(current_user, 'id', None)
    
    try:
        excel_file = analytics.generate_excel_report(user_role, user_id)
        
        response = make_response(excel_file.getvalue())
        response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        response.headers['Content-Disposition'] = f'attachment; filename=analytics_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'
        
        return response
        
    except Exception as e:
        flash(f'Error generating Excel report: {str(e)}', 'error')
        return redirect(url_for('reports.reports_dashboard'))

@reports_bp.route('/export/pdf')
@login_required
def export_pdf():
    """Export analytics to PDF"""
    user_role = getattr(current_user, 'role', 'patient')
    user_id = getattr(current_user, 'id', None)
    
    try:
        # Get analytics data
        dashboard_data = analytics.get_dashboard_analytics(user_role, user_id)
        fhir_data = analytics.get_fhir_analytics(user_role, user_id)
        
        # Create PDF
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        styles = getSampleStyleSheet()
        story = []
        
        # Title
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            spaceAfter=30,
            textColor=colors.HexColor('#2c3e50')
        )
        story.append(Paragraph("NAMASTE + ICD EMR Analytics Report", title_style))
        story.append(Spacer(1, 20))
        
        # Report info
        info_style = styles['Normal']
        story.append(Paragraph(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", info_style))
        story.append(Paragraph(f"User Role: {user_role.title()}", info_style))
        story.append(Spacer(1, 20))
        
        # Patient Statistics
        story.append(Paragraph("Patient Statistics", styles['Heading2']))
        patient_data = [
            ['Metric', 'Value'],
            ['Total Patients', str(dashboard_data['patient_stats']['total'])],
            ['New This Month', str(dashboard_data['patient_stats']['new_this_month'])]
        ]
        
        patient_table = Table(patient_data)
        patient_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 14),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(patient_table)
        story.append(Spacer(1, 20))
        
        # Disease Statistics
        if dashboard_data['disease_stats']:
            story.append(Paragraph("Most Common Diseases", styles['Heading2']))
            disease_data = [['Disease', 'Code', 'Count']]
            for disease in dashboard_data['disease_stats'][:10]:
                disease_data.append([
                    disease['display_name'][:30],
                    disease['namaste_code'] or disease['icd11_code'] or 'N/A',
                    str(disease['count'])
                ])
            
            disease_table = Table(disease_data)
            disease_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            story.append(disease_table)
            story.append(Spacer(1, 20))
        
        # Demographics
        if dashboard_data['demographics']['gender']:
            story.append(Paragraph("Gender Demographics", styles['Heading2']))
            gender_data = [['Gender', 'Count']]
            for gender, count in dashboard_data['demographics']['gender'].items():
                gender_data.append([gender.title(), str(count)])
            
            gender_table = Table(gender_data)
            gender_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 12),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            story.append(gender_table)
            story.append(Spacer(1, 20))
        
        # FHIR Statistics
        story.append(Paragraph("FHIR Interoperability", styles['Heading2']))
        fhir_stats = [
            ['Metric', 'Value'],
            ['Total FHIR Bundles', str(fhir_data['total_bundles'])],
            ['Mapped Conditions', str(fhir_data['mapped_conditions'])]
        ]
        
        fhir_table = Table(fhir_stats)
        fhir_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 14),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
            ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(fhir_table)
        
        # Build PDF
        doc.build(story)
        buffer.seek(0)
        
        response = make_response(buffer.getvalue())
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename=analytics_report_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'
        
        return response
        
    except Exception as e:
        flash(f'Error generating PDF report: {str(e)}', 'error')
        return redirect(url_for('reports.reports_dashboard'))

@reports_bp.route('/api/patient-reports')
@login_required
def get_patient_reports():
    """API endpoint for patient reports data"""
    try:
        from patient_models import PatientDatabase
        
        patient_db = PatientDatabase()
        doctor_id = getattr(current_user, 'username', None) or getattr(current_user, 'email', 'unknown')
        
        # Get only doctor's patients and their diagnoses
        all_patients = patient_db.get_all_patients()
        my_patients = [p for p in all_patients if p.get('created_by') == doctor_id]
        reports = []
        
        for patient in my_patients:
            diagnoses = patient_db.get_patient_diagnoses(patient['patient_id'])
            
            if diagnoses:
                for diagnosis in diagnoses:
                    reports.append({
                        'patient_id': patient['patient_id'],
                        'patient_name': patient['name'],
                        'diagnosis_date': diagnosis.get('diagnosis_date'),
                        'created_at': diagnosis.get('created_at'),
                        'symptoms': diagnosis.get('symptoms'),
                        'namaste_code': diagnosis.get('namaste_code'),
                        'icd11_code': diagnosis.get('icd11_code'),
                        'notes': diagnosis.get('notes')
                    })
            else:
                # Include patients without diagnoses
                reports.append({
                    'patient_id': patient['patient_id'],
                    'patient_name': patient['name'],
                    'diagnosis_date': None,
                    'created_at': patient.get('created_at'),
                    'symptoms': None,
                    'namaste_code': None,
                    'icd11_code': None,
                    'notes': 'No diagnoses recorded'
                })
        
        # Sort by date (newest first)
        reports.sort(key=lambda x: x.get('diagnosis_date') or x.get('created_at') or '', reverse=True)
        
        return jsonify({
            'success': True,
            'reports': reports,
            'total': len(reports)
        })
        
    except Exception as e:
        return jsonify({
            'error': f'Failed to load patient reports: {str(e)}'
        }), 500

@reports_bp.route('/patient/<patient_id>/pdf')
@login_required
def export_patient_pdf(patient_id):
    """Export individual patient report to PDF"""
    try:
        from patient_models import PatientDatabase
        
        patient_db = PatientDatabase()
        patient = patient_db.get_patient(patient_id)
        
        if not patient:
            flash('Patient not found', 'error')
            return redirect(url_for('reports.reports_dashboard'))
        
        # Check if patient belongs to current doctor
        doctor_id = getattr(current_user, 'username', None) or getattr(current_user, 'email', 'unknown')
        if patient.get('created_by') != doctor_id:
            flash('Access denied: This patient does not belong to your account', 'error')
            return redirect(url_for('reports.reports_dashboard'))
        
        diagnoses = patient_db.get_patient_diagnoses(patient_id)
        
        # Create PDF
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        styles = getSampleStyleSheet()
        story = []
        
        # Title
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=20,
            spaceAfter=20,
            textColor=colors.HexColor('#2c3e50')
        )
        story.append(Paragraph(f"Patient Report - {patient['name']}", title_style))
        story.append(Spacer(1, 12))
        
        # Patient Info
        story.append(Paragraph("Patient Information", styles['Heading2']))
        patient_info = [
            ['Patient ID', patient['patient_id']],
            ['Name', patient['name']],
            ['Age', str(patient.get('age', 'N/A'))],
            ['Gender', patient.get('gender', 'N/A')],
            ['Contact', patient.get('contact', 'N/A')],
            ['ABHA ID', patient.get('abha_id', 'N/A')]
        ]
        
        patient_table = Table(patient_info)
        patient_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.grey),
            ('TEXTCOLOR', (0, 0), (0, -1), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('BACKGROUND', (1, 0), (1, -1), colors.beige),
            ('GRID', (0, 0), (-1, -1), 1, colors.black)
        ]))
        story.append(patient_table)
        story.append(Spacer(1, 20))
        
        # Diagnoses
        if diagnoses:
            story.append(Paragraph("Diagnosis History", styles['Heading2']))
            diagnosis_data = [['Date', 'Symptoms', 'NAMASTE Code', 'ICD-11 Code', 'Notes']]
            
            for diagnosis in diagnoses:
                diagnosis_data.append([
                    diagnosis.get('diagnosis_date', 'N/A'),
                    diagnosis.get('symptoms', 'N/A')[:50],
                    diagnosis.get('namaste_code', 'N/A'),
                    diagnosis.get('icd11_code', 'N/A'),
                    diagnosis.get('notes', 'N/A')[:30]
                ])
            
            diagnosis_table = Table(diagnosis_data)
            diagnosis_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 8),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black)
            ]))
            story.append(diagnosis_table)
        else:
            story.append(Paragraph("No diagnoses recorded for this patient.", styles['Normal']))
        
        # Build PDF
        doc.build(story)
        buffer.seek(0)
        
        response = make_response(buffer.getvalue())
        response.headers['Content-Type'] = 'application/pdf'
        response.headers['Content-Disposition'] = f'attachment; filename=patient_{patient_id}_report_{datetime.now().strftime("%Y%m%d")}.pdf'
        
        return response
        
    except Exception as e:
        flash(f'Error generating patient PDF: {str(e)}', 'error')
        return redirect(url_for('reports.reports_dashboard'))

@reports_bp.route('/api/pandas-analytics')
@login_required
def get_pandas_analytics():
    """API endpoint for Pandas-processed analytics data"""
    try:
        # Get doctor identifier for filtering
        doctor_id = getattr(current_user, 'username', None) or getattr(current_user, 'email', 'unknown')
        
        # Get analytics data filtered by doctor
        analytics_data = pandas_analytics.get_comprehensive_analytics(doctor_id)
        return jsonify({
            'success': True,
            'data': analytics_data
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500

@reports_bp.route('/api/refresh-analytics')
@login_required
def refresh_analytics():
    """API endpoint to refresh analytics data"""
    try:
        # Get doctor identifier for filtering
        doctor_id = getattr(current_user, 'username', None) or getattr(current_user, 'email', 'unknown')
        
        # Get refreshed analytics data filtered by doctor
        analytics_data = pandas_analytics.get_comprehensive_analytics(doctor_id)
        return jsonify({
            'success': True,
            'message': 'Analytics data refreshed',
            'timestamp': analytics_data['timestamp']
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500