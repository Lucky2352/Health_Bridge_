"""Doctor-facing appointment requests, mounted at /appointments.

A patient requests an appointment from /patient/treatments-adjacent pages; the row
is created 'pending' and nothing is booked until the doctor it was addressed to
answers. This blueprint is that answer: accept (optionally moving the slot),
decline with a reason, reschedule a confirmed booking, or cancel it.

Access rules, in one place:

* a before_request guard closes the whole blueprint to patients, so a route added
  later is covered without remembering to decorate it;
* doctor_id is never read from the submitted form - it comes from the session - so a
  doctor cannot answer somebody else's queue by editing the POST body; and
* answering a row requires that the signed-in clinician is the doctor the patient
  addressed (admins may act on anyone's), which is what stops two doctors from
  accepting each other's patients.

The patient's own two actions - requesting and cancelling a pending request - live
in patient_portal.py, not here.
"""

import logging
from datetime import datetime

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

from diagnosis_models import DiagnosisDatabase

logger = logging.getLogger(__name__)

appointment_bp = Blueprint('appointments', __name__, url_prefix='/appointments')

diagnosis_db = DiagnosisDatabase()


@appointment_bp.app_template_filter('when')
def format_when(value, fallback='no date set'):
    """Render an appointment timestamp for display.

    A timestamp reaches the template as either a datetime or an ISO string
    depending on whether the column is a real TIMESTAMP or was carried over as text
    from SQLite, so the template must not assume either. Slicing a datetime to get
    'YYYY-MM-DDTHH:MM' works on one and raises TypeError on the other, which would
    take the whole request queue down.
    """
    if not value:
        return fallback

    if isinstance(value, datetime):
        return value.strftime('%d %b %Y, %H:%M')

    text = str(value)
    try:
        return datetime.fromisoformat(text.replace('Z', '')).strftime('%d %b %Y, %H:%M')
    except (TypeError, ValueError):
        return text


def _current_doctor_id():
    """The signed-in clinician's immutable doctor_id, or None.

    This is the value stored in appointments.doctor_id and the one a request has to
    carry for this doctor to be allowed to answer it. Deliberately not the username,
    which a clinician can change.
    """
    return getattr(current_user, 'doctor_id', None)


def _may_respond(appointment):
    """Whether the signed-in user is allowed to answer *appointment*.

    Admins are allowed because they are the escalation path when a doctor is away;
    anyone else must be the doctor the patient addressed.
    """
    if current_user.is_admin():
        return True
    return appointment.get('doctor_id') == _current_doctor_id()


def _parse_datetime(value, field_label):
    """Turn a submitted date/time into a datetime, or return None.

    The value comes from an <input type="datetime-local">, so it arrives as
    'YYYY-MM-DDTHH:MM'. Accepting a date on its own as well is what lets the doctor
    accept without thinking about the time, which is the common case.
    """
    value = (value or '').strip()
    if not value:
        return None

    for fmt in ('%Y-%m-%dT%H:%M', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M', '%Y-%m-%d'):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue

    return f'__invalid__{field_label}'


def _valid_when(value):
    """The sentinel _parse_datetime returns for an unparseable date.

    Kept as a truthy string so callers test the result with `is None` for "not
    supplied" and `startswith('__invalid__')` for "supplied but nonsense", and the
    two mistakes cannot be confused.
    """
    return isinstance(value, str) and value.startswith('__invalid__')


@appointment_bp.before_request
def require_clinician():
    """Keep answering appointment requests to doctors and admins.

    The patient portal is the other half of this flow; it must never gain a way to
    confirm its own request, so the check lives on the blueprint rather than on each
    route.
    """
    if not current_user.is_authenticated:
        return redirect(url_for('enhanced_auth.login'))

    if not (current_user.is_doctor() or current_user.is_admin()):
        flash('Clinician access required', 'error')
        return redirect(url_for('enhanced_auth.dashboard'))


def _queue():
    """The appointments this clinician is responsible for.

    Admins have no doctor_id of their own, so they get the whole list across every
    doctor - useful precisely because they are the escalation path.
    """
    if current_user.is_admin():
        merged = []
        for doctor in diagnosis_db.get_available_doctors():
            merged.extend(diagnosis_db.get_doctor_appointments(doctor['doctor_id']))
        return merged

    return diagnosis_db.get_doctor_appointments(_current_doctor_id())


# --------------------------------------------------------------------------
# Read - the doctor's request queue
# --------------------------------------------------------------------------

@appointment_bp.route('/')
@login_required
def appointment_list():
    """Every appointment addressed to the signed-in doctor, requests first.

    ?status=pending narrows it to the inbox, which is what the "Requests Waiting"
    card on the dashboard links to. The stat cards are always computed over the
    whole queue, so the numbers do not move when the view is filtered.
    """
    everything = _queue()
    wanted = request.args.getlist('status')
    items = [a for a in everything if a.get('status') in wanted] if wanted else everything

    return render_template(
        'appointments/list.html',
        appointments=items,
        filtered=bool(wanted),
        is_admin_view=current_user.is_admin(),
        pending_count=sum(1 for a in everything if a.get('status') == 'pending'),
        scheduled_count=sum(1 for a in everything if a.get('status') == 'scheduled'),
        today_count=sum(
            1 for a in everything
            if a.get('status') == 'scheduled' and _is_today(a.get('appointment_date'))
        ),
    )


def _is_today(value):
    """Whether an appointment_date falls on today, tolerating either backend's type."""
    if not value:
        return False
    if isinstance(value, datetime):
        return value.date() == datetime.now().date()
    try:
        return datetime.fromisoformat(str(value).replace('Z', '')).date() == datetime.now().date()
    except (TypeError, ValueError):
        return False


@appointment_bp.route('/api/list')
@login_required
def api_list():
    """The request queue as JSON, optionally narrowed to one status."""
    statuses = request.args.getlist('status') or None
    if current_user.is_admin():
        items = _queue()
        if statuses:
            items = [a for a in items if a.get('status') in statuses]
    else:
        items = diagnosis_db.get_doctor_appointments(_current_doctor_id(), statuses)

    return jsonify({
        'success': True,
        'appointments': items,
        'total': len(items),
        'pending': sum(1 for a in items if a.get('status') == 'pending'),
        'scheduled': sum(1 for a in items if a.get('status') == 'scheduled'),
    })


# --------------------------------------------------------------------------
# Accept / decline / reschedule / cancel
# --------------------------------------------------------------------------

def _load_for_response(appointment_id):
    """Fetch an appointment this clinician is allowed to answer.

    Returns (appointment, None) on success or (None, response) with a flash already
    set and the redirect to send the caller to, so every transition route below can
    do the same two lines of guard.
    """
    appointment = diagnosis_db.get_appointment(appointment_id)
    if not appointment:
        flash('Appointment not found', 'error')
        return None, redirect(url_for('appointments.appointment_list'))

    if not _may_respond(appointment):
        flash('Access denied: this appointment was requested from another doctor', 'error')
        return None, redirect(url_for('appointments.appointment_list'))

    return appointment, None


@appointment_bp.route('/<int:appointment_id>/accept', methods=['POST'])
@login_required
def accept_appointment(appointment_id):
    """Confirm a request. The doctor may move it to a different slot while accepting.

    This is the transition that makes an appointment real: until it happens the row
    is only a request, and the patient sees it as waiting.
    """
    appointment, refusal = _load_for_response(appointment_id)
    if refusal is not None:
        return refusal

    when = _parse_datetime(request.form.get('appointment_date'), 'Appointment date')
    if _valid_when(when):
        flash('That appointment date could not be read', 'error')
        return redirect(url_for('appointments.appointment_list'))

    note = request.form.get('doctor_note', '').strip()

    # No date in the POST means "the slot the patient asked for is fine", so the
    # stored requested value stands rather than being blanked.
    diagnosis_db.accept_appointment(appointment_id, when, note or None)

    who = appointment.get('patient_name') or appointment.get('patient_id')
    session['appointment_success'] = (
        f"Appointment with {who} confirmed for "
        f"{when.strftime('%d %b %Y, %H:%M') if when else 'the requested time'}."
    )
    return redirect(url_for('appointments.appointment_list'))


@appointment_bp.route('/<int:appointment_id>/decline', methods=['POST'])
@login_required
def decline_appointment(appointment_id):
    """Turn a request down. The patient can read the reason and book again."""
    appointment, refusal = _load_for_response(appointment_id)
    if refusal is not None:
        return refusal

    note = request.form.get('doctor_note', '').strip()
    diagnosis_db.decline_appointment(appointment_id, note or None)

    who = appointment.get('patient_name') or appointment.get('patient_id')
    session['appointment_success'] = f'Appointment request from {who} declined.'
    return redirect(url_for('appointments.appointment_list'))


@appointment_bp.route('/<int:appointment_id>/reschedule', methods=['POST'])
@login_required
def reschedule_appointment(appointment_id):
    """Move a confirmed appointment to a new date.

    Only meaningful once the booking exists, so a request that has not been accepted
    is sent to accept instead of being quietly rescheduled into existence.
    """
    appointment, refusal = _load_for_response(appointment_id)
    if refusal is not None:
        return refusal

    when = _parse_datetime(request.form.get('appointment_date'), 'New appointment date')
    if when is None or _valid_when(when):
        flash('Pick a new date and time for the appointment', 'error')
        return redirect(url_for('appointments.appointment_list'))

    if appointment.get('status') == 'pending':
        # Not booked yet, so this is an accept that also moves the slot. Doing it as
        # an accept keeps the patient from seeing a "rescheduled" request they never
        # had confirmed in the first place.
        diagnosis_db.accept_appointment(appointment_id, when, None)
    else:
        diagnosis_db.reschedule_appointment(appointment_id, when)

    who = appointment.get('patient_name') or appointment.get('patient_id')
    session['appointment_success'] = (
        f'Appointment with {who} moved to {when.strftime("%d %b %Y, %H:%M")}.'
    )
    return redirect(url_for('appointments.appointment_list'))


@appointment_bp.route('/<int:appointment_id>/cancel', methods=['POST'])
@login_required
def cancel_appointment(appointment_id):
    """Cancel a booking on the doctor's own side.

    Kept separate from the patient's cancel route in patient_portal.py, which is
    limited to requests that have not been accepted yet.
    """
    appointment, refusal = _load_for_response(appointment_id)
    if refusal is not None:
        return refusal

    if appointment.get('status') == 'pending':
        flash(
            'This is still a request - decline it instead of cancelling it.',
            'error',
        )
        return redirect(url_for('appointments.appointment_list'))

    diagnosis_db.cancel_appointment(appointment_id)

    who = appointment.get('patient_name') or appointment.get('patient_id')
    session['appointment_success'] = f'Appointment with {who} cancelled.'
    return redirect(url_for('appointments.appointment_list'))