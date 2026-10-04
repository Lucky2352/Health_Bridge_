"""Patient portal.

A signed-in patient can review the diagnoses, prescriptions, treatments and
appointments recorded against their own patient record. Two things keep that
scoped to them:

* the patient_id used in every query is read from the session rather than the
  request, so no URL path, form field or query string can point the portal at
  somebody else's records; and
* the only rows a patient may write are their own appointment requests, and those
  can only be *withdrawn while still pending* - the acceptance that turns a request
  into a booking is the doctor's decision and lives in appointment_routes.py.

Every other record type is read-only here: every route in this blueprint that is not
one of those two appointment actions is GET-only, so Flask answers a POST with 405.

The "which doctor is treating me" question needs no extra table: each record
row already carries both sides of the relationship (diagnoses.doctor_id and
diagnoses.patient_id), so a patient sees every row whose patient_id is their
own, together with the name of the doctor who wrote it.

Appointments are the one place the relationship runs the other way. A patient asks
for a slot, which creates a 'pending' row, and the doctor named on it accepts,
declines or reschedules on /appointments. Until that acceptance lands, the patient
sees it as a request rather than a confirmed appointment.
"""

import logging
from datetime import datetime, timedelta
from functools import wraps

from flask import (
    Blueprint,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required

from diagnosis_models import DiagnosisDatabase

logger = logging.getLogger(__name__)

# Mounted at /patient because that is what every link and fetch() call in
# templates/patient_*.html already points at. The clinician-side patient CRUD
# lives on the separate /patients blueprint in patient_routes.py.
patient_portal_bp = Blueprint('patient_portal', __name__, url_prefix='/patient')

diagnosis_db = DiagnosisDatabase()

# Shown by the portal when the signed-in account has no patient record yet,
# so a brand new signup sees an explanation rather than a bare empty list.
NO_RECORD_MESSAGE = 'No patient record is linked to this account yet.'


def patient_required(view):
    """Restrict a view to signed-in patients.

    Anonymous visitors are bounced to the login page by login_required; a
    signed-in doctor or admin gets redirected to their own dashboard rather
    than a confusing 403 page.
    """

    @wraps(view)
    @login_required
    def wrapper(*args, **kwargs):
        if not current_user.is_patient():
            flash('Patient access required', 'error')
            return redirect(url_for('enhanced_auth.dashboard'))
        return view(*args, **kwargs)

    return wrapper


def session_patient_id():
    """The signed-in patient's own patient_id, or None if none was assigned.

    Deliberately takes no argument. Every query in this module is built from
    this value alone, which is what stops one patient reading another's records
    by editing a URL.
    """
    return getattr(current_user, 'patient_id', None)


def my_diagnoses():
    return diagnosis_db.get_patient_diagnoses(session_patient_id()) if session_patient_id() else []


def my_prescriptions():
    return diagnosis_db.get_patient_prescriptions(session_patient_id()) if session_patient_id() else []


def my_appointments():
    return diagnosis_db.get_patient_appointments(session_patient_id()) if session_patient_id() else []


def my_treatments():
    """Every treatment plan written for the signed-in patient, doctor details included."""
    return diagnosis_db.get_patient_treatments(session_patient_id()) if session_patient_id() else []


def my_doctors():
    """The distinct doctors who have treated the signed-in patient."""
    return diagnosis_db.get_patient_doctors(session_patient_id()) if session_patient_id() else []


THIRTY_DAYS = timedelta(days=30)


def _count_this_month(records, key):
    """How many of *records* were created within the last 30 days."""
    cutoff = datetime.now() - THIRTY_DAYS
    return sum(1 for r in records if r.get(key) and _as_datetime(r[key]) >= cutoff)


def _as_datetime(value):
    """Coerce a stored timestamp to a naive datetime for comparison.

    SQLite handed back strings and PostgreSQL hands back datetimes, so records
    read through the same helper can be sorted and compared either way.
    """
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    try:
        return datetime.fromisoformat(str(value).replace('Z', ''))
    except (TypeError, ValueError):
        return datetime.min


# --------------------------------------------------------------------------
# Diagnoses - the core of the request: see a doctor's diagnosis, never write it
# --------------------------------------------------------------------------

@patient_portal_bp.route('/records')
@patient_required
def records():
    """Render the read-only 'My Records' page."""
    return render_template('patient_records.html')


@patient_portal_bp.route('/api/diagnoses')
@patient_required
def api_diagnoses():
    """Every diagnosis recorded against the signed-in patient's own record."""
    if not session_patient_id():
        return jsonify({'success': True, 'diagnoses': [], 'message': NO_RECORD_MESSAGE})

    try:
        diagnoses = my_diagnoses()
    except Exception as exc:
        logger.error('Failed to load patient diagnoses: %s', exc)
        return jsonify({'success': False, 'diagnoses': [], 'error': str(exc)}), 500

    return jsonify({
        'success': True,
        'patient_id': session_patient_id(),
        'diagnoses': diagnoses,
        'read_only': True,
    })


@patient_portal_bp.route('/api/dashboard-stats')
@patient_required
def api_dashboard_stats():
    """Counts for the four cards at the top of the patient dashboard."""
    if not session_patient_id():
        return jsonify({
            'success': True,
            'records': 0,
            'prescriptions': 0,
            'appointments': 0,
            'visits': 0,
            'treatments': 0,
        })

    try:
        diagnoses = my_diagnoses()
        prescriptions = my_prescriptions()
        appointments = my_appointments()
        treatments = my_treatments()
    except Exception as exc:
        logger.error('Failed to load patient dashboard stats: %s', exc)
        return jsonify({
            'success': True,
            'records': 0,
            'prescriptions': 0,
            'appointments': 0,
            'visits': 0,
            'treatments': 0,
        })

    return jsonify({
        'success': True,
        'records': len(diagnoses),
        'prescriptions': len(prescriptions),
        'appointments': len(appointments),
        'visits': len(diagnoses),
        'treatments': len(treatments),
    })


# --------------------------------------------------------------------------
# Prescriptions
# --------------------------------------------------------------------------

@patient_portal_bp.route('/prescriptions')
@patient_required
def prescriptions():
    return render_template('patient_prescriptions.html')


@patient_portal_bp.route('/api/prescriptions')
@patient_required
def api_prescriptions():
    if not session_patient_id():
        return jsonify({'success': True, 'prescriptions': [], 'message': NO_RECORD_MESSAGE})

    try:
        items = my_prescriptions()
    except Exception as exc:
        logger.error('Failed to load patient prescriptions: %s', exc)
        return jsonify({'success': False, 'prescriptions': [], 'error': str(exc)}), 500

    return jsonify({
        'success': True,
        'prescriptions': items,
        'total': len(items),
        'this_month': _count_this_month(items, 'created_at'),
        'read_only': True,
    })


# --------------------------------------------------------------------------
# Treatments - the plan a doctor is treating the patient with, plus who wrote it
# --------------------------------------------------------------------------

@patient_portal_bp.route('/treatments')
@patient_required
def treatments():
    """Render the read-only 'My Treatment Plan' page."""
    return render_template('patient_treatments.html')


@patient_portal_bp.route('/api/treatments')
@patient_required
def api_treatments():
    """The signed-in patient's own treatment plans, with their doctors' details.

    Scoped by session patient_id like every other query here, so no URL can point
    it at another patient's plan, and GET-only like the rest of the blueprint.
    """
    if not session_patient_id():
        return jsonify({
            'success': True,
            'treatments': [],
            'doctors': [],
            'message': NO_RECORD_MESSAGE,
        })

    try:
        items = my_treatments()
        doctors = my_doctors()
    except Exception as exc:
        logger.error('Failed to load patient treatments: %s', exc)
        return jsonify({
            'success': False,
            'treatments': [],
            'doctors': [],
            'error': str(exc),
        }), 500

    active = [t for t in items if str(t.get('status', '')).lower() == 'active']

    return jsonify({
        'success': True,
        'patient_id': session_patient_id(),
        'treatments': items,
        'doctors': doctors,
        'total': len(items),
        'active': len(active),
        'this_month': _count_this_month(items, 'created_at'),
        'read_only': True,
    })


@patient_portal_bp.route('/api/my-doctors')
@patient_required
def api_my_doctors():
    """The clinicians currently treating the signed-in patient.

    Lets the dashboard show "who is looking after me" without making the patient
    read through every treatment to work that out.
    """
    if not session_patient_id():
        return jsonify({'success': True, 'doctors': [], 'message': NO_RECORD_MESSAGE})

    try:
        doctors = my_doctors()
    except Exception as exc:
        logger.error('Failed to load patient doctors: %s', exc)
        return jsonify({'success': False, 'doctors': [], 'error': str(exc)}), 500

    return jsonify({
        'success': True,
        'doctors': doctors,
        'total': len(doctors),
        'read_only': True,
    })


# --------------------------------------------------------------------------
# Appointments
#
# The only part of the portal a patient may write to, and only in two directions:
# ask for a slot, and withdraw that ask while it is still unanswered. Confirming it
# is the doctor's call and happens on /appointments.
# --------------------------------------------------------------------------

@patient_portal_bp.route('/appointments')
@patient_required
def appointments():
    return render_template('patient_appointments.html')


@patient_portal_bp.route('/api/appointments')
@patient_required
def api_appointments():
    if not session_patient_id():
        return jsonify({'success': True, 'appointments': [], 'message': NO_RECORD_MESSAGE})

    try:
        items = my_appointments()
    except Exception as exc:
        logger.error('Failed to load patient appointments: %s', exc)
        return jsonify({'success': False, 'appointments': [], 'error': str(exc)}), 500

    now = datetime.now()
    today = now.date()
    upcoming = completed = pending = declined = 0
    for item in items:
        status = str(item.get('status', '')).lower()
        if status == 'completed':
            completed += 1
        elif status == 'pending':
            # Not a booking, so it must not inflate "upcoming".
            pending += 1
        elif status == 'declined':
            declined += 1
        elif str(item.get('status', '')).lower() == 'scheduled' \
                and when_is_future(item.get('appointment_date'), today):
            upcoming += 1

    return jsonify({
        'success': True,
        'appointments': items,
        'upcoming': upcoming,
        'today': sum(
            1 for i in items
            if str(i.get('status', '')).lower() == 'scheduled'
            and _as_datetime(i.get('appointment_date')).date() == today
        ),
        'completed': completed,
        'pending': pending,
        'declined': declined,
        'read_only': True,
    })


def when_is_future(value, today):
    """Whether an appointment_date has not passed yet.

    Compared on the date alone: a morning slot does not become "upcoming" for only
    the first few hours of the day it was booked for.
    """
    try:
        return _as_datetime(value).date() >= today
    except (TypeError, ValueError):
        return False


@patient_portal_bp.route('/api/appointments/doctors')
@patient_required
def api_appointment_doctors():
    """The doctors this patient may request an appointment with.

    Their names and ids only - a patient is picking who to see, not reading anybody
    else's diary, so no schedule information is exposed here.
    """
    return jsonify({
        'success': True,
        'doctors': diagnosis_db.get_available_doctors(),
    })


@patient_portal_bp.route('/api/appointments', methods=['POST'])
@patient_required
def api_request_appointment():
    """Ask a doctor for a slot.

    Everything that decides the row comes from somewhere the patient cannot forge:
    patient_id from the session, and the doctor from get_available_doctors() rather
    than from the submitted doctor_id being trusted as-is. The row is created
    'pending'; it becomes an appointment only once the doctor accepts it.
    """
    patient_id = session_patient_id()
    if not patient_id:
        return jsonify({
            'success': False,
            'error': NO_RECORD_MESSAGE,
        }), 400

    doctor_id = (request.form.get('doctor_id') or '').strip()
    requested = _parse_requested_when(request.form.get('appointment_date'))
    reason = (request.form.get('reason') or '').strip()

    if not reason:
        return jsonify({
            'success': False,
            'error': 'Please tell the doctor why you would like to be seen.',
        }), 400

    doctor = next(
        (d for d in diagnosis_db.get_available_doctors() if d['doctor_id'] == doctor_id),
        None,
    )
    if not doctor:
        return jsonify({
            'success': False,
            'error': 'Please choose a doctor to request the appointment from.',
        }), 400

    if requested is None:
        return jsonify({
            'success': False,
            'error': 'Please choose a preferred date and time.',
        }), 400

    if requested <= datetime.now():
        return jsonify({
            'success': False,
            'error': 'Please choose a date and time in the future.',
        }), 400

    # One open request per doctor at a time. Without this the queue fills with
    # duplicates of the same ask and the doctor has no way to tell which one to
    # answer; cancelling or declining frees the slot up again.
    already_asked = any(
        a.get('doctor_id') == doctor_id and str(a.get('status', '')).lower() == 'pending'
        for a in my_appointments()
    )
    if already_asked:
        return jsonify({
            'success': False,
            'error': f'You already have a request waiting with Dr. {doctor["full_name"]}.',
        }), 409

    try:
        appointment_id = diagnosis_db.request_appointment(
            patient_id=patient_id,
            doctor_id=doctor_id,
            requested_date=requested,
            reason=reason,
        )
    except Exception as exc:
        logger.error('Failed to store appointment request: %s', exc)
        return jsonify({'success': False, 'error': str(exc)}), 500

    return jsonify({
        'success': True,
        'appointment_id': appointment_id,
        'status': 'pending',
        'message': (
            f'Request sent to Dr. {doctor["full_name"]}. It is not booked yet - '
            'they have to accept it first.'
        ),
    }), 201


def _parse_requested_when(value):
    """Read the requested slot from a datetime-local input, or None if unusable."""
    value = (value or '').strip()
    if not value:
        return None

    for fmt in ('%Y-%m-%dT%H:%M', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


@patient_portal_bp.route('/api/appointments/<int:appointment_id>/cancel', methods=['POST'])
@patient_required
def api_cancel_appointment(appointment_id):
    """Withdraw the patient's own request.

    Two checks make this safe to expose: the row has to carry this session's
    patient_id, so nobody can cancel another patient's request by guessing an id;
    and it has to still be pending, because once the doctor has accepted, cancelling
    is their decision, not the patient's.
    """
    patient_id = session_patient_id()
    if not patient_id:
        return jsonify({'success': False, 'error': NO_RECORD_MESSAGE}), 400

    appointment = diagnosis_db.get_appointment(appointment_id)
    if not appointment:
        return jsonify({'success': False, 'error': 'Appointment not found.'}), 404

    if appointment.get('patient_id') != patient_id:
        # Deliberately the same answer as "not found" so the response does not
        # confirm that somebody else's appointment id exists.
        return jsonify({'success': False, 'error': 'Appointment not found.'}), 404

    if str(appointment.get('status', '')).lower() != 'pending':
        return jsonify({
            'success': False,
            'error': (
                'This appointment has already been answered, so it can no longer '
                'be cancelled here. Please contact the doctor.'
            ),
        }), 409

    diagnosis_db.cancel_appointment(appointment_id)

    return jsonify({
        'success': True,
        'status': 'cancelled',
        'message': 'Your request has been withdrawn.',
    })


# --------------------------------------------------------------------------
# History - one merged timeline across all three record types
# --------------------------------------------------------------------------

@patient_portal_bp.route('/history')
@patient_required
def history():
    return render_template('patient_history.html')


@patient_portal_bp.route('/api/history')
@patient_required
def api_history():
    if not session_patient_id():
        return jsonify({'success': True, 'history': [], 'message': NO_RECORD_MESSAGE})

    try:
        diagnoses = my_diagnoses()
        prescriptions = my_prescriptions()
        appointments = my_appointments()
        treatments = my_treatments()
    except Exception as exc:
        logger.error('Failed to load patient history: %s', exc)
        return jsonify({'success': False, 'history': [], 'error': str(exc)}), 500

    entries = []
    for d in diagnoses:
        entries.append({
            'type': 'diagnosis',
            'title': d.get('condition_name'),
            'detail': d.get('notes'),
            'code': d.get('condition_code'),
            'doctor_name': d.get('doctor_name'),
            'doctor_id': d.get('doctor_id'),
            'date': d.get('created_at'),
        })
    for t in treatments:
        entries.append({
            'type': 'treatment',
            'title': t.get('title'),
            'detail': ' '.join(
                filter(None, [t.get('treatment_type'), t.get('dosage'),
                              t.get('frequency'), t.get('duration')])
            ),
            'code': t.get('status'),
            'doctor_name': t.get('doctor_name'),
            'doctor_id': t.get('doctor_id'),
            'date': t.get('created_at'),
        })
    for p in prescriptions:
        entries.append({
            'type': 'prescription',
            'title': p.get('medication_name'),
            'detail': ' '.join(
                filter(None, [p.get('dosage'), p.get('frequency'), p.get('duration')])
            ),
            'code': None,
            'doctor_name': p.get('doctor_name'),
            'doctor_id': p.get('doctor_id'),
            'date': p.get('created_at'),
        })
    for a in appointments:
        entries.append({
            'type': 'appointment',
            'title': f"Appointment ({a.get('status', 'scheduled')})",
            'detail': a.get('notes'),
            'code': None,
            'doctor_name': a.get('doctor_name'),
            'doctor_id': a.get('doctor_id'),
            'date': a.get('appointment_date'),
        })

    entries.sort(key=lambda e: _as_datetime(e['date']), reverse=True)

    providers = {e['doctor_name'] for e in entries if e.get('doctor_name')}
    dates = [_as_datetime(e['date']) for e in entries if e.get('date')]
    years = len({d.year for d in dates}) if dates else 0

    return jsonify({
        'success': True,
        'history': entries,
        'count': len(entries),
        'providers': len(providers),
        'years': years,
        'read_only': True,
    })


# --------------------------------------------------------------------------
# Profile
# --------------------------------------------------------------------------

@patient_portal_bp.route('/profile')
@patient_required
def profile():
    return render_template('patient_profile.html')