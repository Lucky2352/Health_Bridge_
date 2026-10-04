"""Doctor-facing treatment plan management, mounted at /treatments.

This is the only place a treatment is written. A doctor opens a patient's plan,
records what the treatment is, and later revises or closes it out. The patient
then sees the same rows at GET /patient/api/treatments, together with the name
and contact details of the doctor who wrote each one, but has no route here and
so no way to change any of it.

Access rules, in one place:

* a before_request guard closes the whole blueprint to patients, so a route added
  later is covered without remembering to decorate it;
* doctor_id and patient_id are never read from the submitted form. doctor_id comes
  from the session and patient_id is resolved against enhanced_users, so a doctor
  cannot forge a treatment for somebody else by editing the POST body; and
* editing and deleting require that the signed-in clinician is the row's author
  (admins may act on anyone's), which is what stops one doctor from rewriting
  another doctor's plan.
"""

import logging

from flask import (
    Blueprint,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_required

from diagnosis_models import (
    DiagnosisDatabase,
    TREATMENT_STATUSES,
    TREATMENT_TYPES,
)

logger = logging.getLogger(__name__)

treatment_bp = Blueprint('treatments', __name__, url_prefix='/treatments')

diagnosis_db = DiagnosisDatabase()


def _current_doctor_id():
    """The signed-in clinician's immutable doctor_id, or None.

    This is the value stored in treatments.doctor_id. It is deliberately not the
    username, which a clinician can change and which would orphan their plan.
    """
    return getattr(current_user, 'doctor_id', None)


def _may_modify(treatment):
    """Whether the signed-in user is allowed to edit/delete *treatment*.

    Admins are allowed because they are the escalation path for a doctor who has
    left; anyone else must be the author of the row.
    """
    if current_user.is_admin():
        return True
    return treatment.get('doctor_id') == _current_doctor_id()


def _resolve_patient(identifier):
    """Look up an enhanced_users patient by patient_id or email.

    Accepts both so a doctor can paste whichever they have to hand. Returns the
    patient dict or None.
    """
    identifier = (identifier or '').strip()
    if not identifier:
        return None

    for patient in diagnosis_db.get_all_patients():
        if identifier in (patient.get('patient_id'), patient.get('email')):
            return patient
    return None


def _treatment_form_payload():
    """Pull the treatment fields out of a submitted form into a clean dict.

    Unknown keys are dropped and the enum fields are checked against the allowed
    values here rather than in SQL, so a hand-crafted POST cannot store a status
    the dashboard has no badge for.
    """
    data = {
        'title': request.form.get('title', '').strip(),
        'treatment_type': request.form.get('treatment_type', 'medication').strip().lower(),
        'description': request.form.get('description', '').strip(),
        'medication_name': request.form.get('medication_name', '').strip(),
        'dosage': request.form.get('dosage', '').strip(),
        'frequency': request.form.get('frequency', '').strip(),
        'duration': request.form.get('duration', '').strip(),
        'instructions': request.form.get('instructions', '').strip(),
        'status': request.form.get('status', 'active').strip().lower(),
        'start_date': request.form.get('start_date', '').strip(),
        'end_date': request.form.get('end_date', '').strip(),
        'follow_up_date': request.form.get('follow_up_date', '').strip(),
        'notes': request.form.get('notes', '').strip(),
    }

    if data['treatment_type'] not in TREATMENT_TYPES:
        data['treatment_type'] = TREATMENT_TYPES[0]
    if data['status'] not in TREATMENT_STATUSES:
        data['status'] = TREATMENT_STATUSES[0]

    return data


@treatment_bp.before_request
def require_clinician():
    """Keep treatment authoring to doctors and admins.

    The patient portal (/patient) is the read side of the same rows; it must
    never gain a write path, so the check lives on the blueprint rather than on
    each route.
    """
    if not current_user.is_authenticated:
        return redirect(url_for('enhanced_auth.login'))

    if not (current_user.is_doctor() or current_user.is_admin()):
        flash('Clinician access required', 'error')
        return redirect(url_for('enhanced_auth.dashboard'))


# --------------------------------------------------------------------------
# Read - the doctor's own view of the plans they are responsible for
# --------------------------------------------------------------------------

@treatment_bp.route('/')
@login_required
def treatment_list():
    """Every treatment plan the signed-in doctor is responsible for, newest first."""
    if current_user.is_admin():
        # Admins have no doctor_id of their own, so there is nothing of theirs to
        # list; they reach a plan through the doctor who wrote it.
        return render_template(
            'treatments/list.html',
            treatments=[],
            is_admin_view=True,
        )

    return render_template(
        'treatments/list.html',
        treatments=diagnosis_db.get_doctor_treatments(_current_doctor_id()),
        is_admin_view=False,
    )


@treatment_bp.route('/api/list')
@login_required
def api_list():
    """The signed-in doctor's treatment plans as JSON, optionally per patient."""
    if current_user.is_admin():
        items = []
        for patient in diagnosis_db.get_all_patients():
            items.extend(diagnosis_db.get_patient_treatments(patient['patient_id']))
    else:
        items = diagnosis_db.get_doctor_treatments(
            _current_doctor_id(), request.args.get('patient_id')
        )

    return jsonify({
        'success': True,
        'treatments': items,
        'total': len(items),
        'active': sum(1 for t in items if t.get('status') == 'active'),
    })


@treatment_bp.route('/api/patients')
@login_required
def api_patients():
    """Patients a clinician can start a treatment for."""
    return jsonify({'success': True, 'patients': diagnosis_db.get_all_patients()})


# --------------------------------------------------------------------------
# Create
# --------------------------------------------------------------------------

def _render_form(treatment=None, form_data=None, selected_patient=''):
    """Render the create/edit form.

    Wrapped in one helper because a rejected POST has to come back to the same
    form with the doctor's input still in it, and that call appears on every
    validation branch. form_data wins over treatment when both are present so a
    rejected edit shows what was submitted, not what is stored.
    """
    return render_template(
        'treatments/form.html',
        treatment=treatment,
        form_data=form_data,
        patients=diagnosis_db.get_all_patients(),
        selected_patient=selected_patient or (treatment or {}).get('patient_id', ''),
        treatment_types=TREATMENT_TYPES,
        treatment_statuses=TREATMENT_STATUSES,
    )


@treatment_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create_treatment():
    """Blank treatment form, and the POST that saves it."""
    if request.method == 'GET':
        return _render_form(selected_patient=request.args.get('patient_id', ''))

    submitted_patient = request.form.get('patient_id', '')

    if not _current_doctor_id():
        flash(
            'Your account has no doctor ID assigned, so a treatment cannot be '
            'recorded against it. Please contact an administrator.',
            'error',
        )
        return _render_form(selected_patient=submitted_patient)

    data = _treatment_form_payload()
    if not data['title']:
        flash('Treatment title is required', 'error')
        return _render_form(form_data=data, selected_patient=submitted_patient)

    patient = _resolve_patient(submitted_patient)
    if not patient:
        flash('Select a valid patient before saving the treatment', 'error')
        return _render_form(form_data=data, selected_patient=submitted_patient)

    diagnosis_db.add_treatment(
        doctor_id=_current_doctor_id(),
        patient_id=patient['patient_id'],
        **data,
    )

    session['treatment_success'] = (
        f"Treatment '{data['title']}' started for {patient['full_name']} "
        f"({patient['patient_id']})."
    )

    return redirect(url_for('treatments.treatment_list'))


# --------------------------------------------------------------------------
# Update / delete
# --------------------------------------------------------------------------

@treatment_bp.route('/<int:treatment_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_treatment(treatment_id):
    """Revise an existing plan. Only its author (or an admin) gets here."""
    treatment = diagnosis_db.get_treatment(treatment_id)
    if not treatment:
        flash('Treatment not found', 'error')
        return redirect(url_for('treatments.treatment_list'))

    if not _may_modify(treatment):
        flash('Access denied: this treatment belongs to another doctor', 'error')
        return redirect(url_for('treatments.treatment_list'))

    if request.method == 'GET':
        return _render_form(treatment=treatment)

    data = _treatment_form_payload()
    if not data['title']:
        flash('Treatment title is required', 'error')
        return _render_form(treatment=treatment, form_data=data)

    diagnosis_db.update_treatment(treatment_id, data)
    session['treatment_success'] = f"Treatment '{data['title']}' updated."
    return redirect(url_for('treatments.treatment_list'))


@treatment_bp.route('/<int:treatment_id>/delete', methods=['POST'])
@login_required
def delete_treatment(treatment_id):
    """Stop a treatment. Same authorship rule as editing."""
    treatment = diagnosis_db.get_treatment(treatment_id)
    if not treatment:
        flash('Treatment not found', 'error')
        return redirect(url_for('treatments.treatment_list'))

    if not _may_modify(treatment):
        flash('Access denied: this treatment belongs to another doctor', 'error')
        return redirect(url_for('treatments.treatment_list'))

    diagnosis_db.delete_treatment(treatment_id)
    session['treatment_success'] = (
        f"Treatment '{treatment.get('title')}' removed from "
        f"{treatment.get('patient_name') or treatment.get('patient_id')}'s plan."
    )
    return redirect(url_for('treatments.treatment_list'))