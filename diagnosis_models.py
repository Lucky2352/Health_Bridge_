import db
import os
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Treatment vocabulary. Kept as module-level tuples so the create/edit form, the
# validation in treatment_routes.py and the badge rendering in the templates all
# agree on the same allowed values.
TREATMENT_TYPES = ('medication', 'procedure', 'therapy', 'lifestyle', 'follow_up')
TREATMENT_STATUSES = ('active', 'completed', 'discontinued', 'on_hold')

# Appointment lifecycle. An appointment does not exist as a confirmed booking the
# moment a patient submits a request: the row is created as 'pending' and only
# becomes 'scheduled' once the addressed doctor accepts it. The patient can cancel
# while it is still pending; after that only the doctor can move it.
#
#   pending  -> scheduled (accepted) | declined | cancelled (by the patient)
#   scheduled -> scheduled (rescheduled, new date) | cancelled (by the doctor)
#   declined  -> terminal; the patient books again as a new 'pending' request
#
# 'completed' is deliberately not here: nothing in this codebase marks an
# appointment as having happened, and offering a status with no route to set it
# would only let it drift.
APPOINTMENT_STATUSES = ('pending', 'scheduled', 'declined', 'cancelled')

#: The statuses a doctor may move a row to from their own request queue.
APPOINTMENT_DOCTOR_STATUSES = ('scheduled', 'declined', 'cancelled')

class DiagnosisDatabase:
    def __init__(self, db_file='enhanced_auth.db'):
        self.db_file = os.path.abspath(db_file)
        self.init_database()
    
    def init_database(self):
        """Initialize diagnosis database with proper foreign key relationships"""
        conn = db.connect(self.db_file)
        conn.execute('PRAGMA foreign_keys = ON')
        
        # Create diagnosis table with proper relationships
        conn.execute('''
            CREATE TABLE IF NOT EXISTS diagnoses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doctor_id TEXT NOT NULL,
                patient_id TEXT NOT NULL,
                condition_code TEXT,
                condition_name TEXT NOT NULL,
                notes TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # An appointment begins as a *request*, not a confirmed booking: the patient
        # names a doctor and a preferred slot, and the row stays 'pending' until that
        # doctor accepts it. requested_date keeps what the patient originally asked
        # for even after a reschedule, so a doctor can see what was requested against
        # what they actually agreed to. doctor_note and responded_at are the reply.
        conn.execute('''
            CREATE TABLE IF NOT EXISTS appointments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doctor_id TEXT NOT NULL,
                patient_id TEXT NOT NULL,
                appointment_date DATETIME NOT NULL,
                status TEXT DEFAULT 'pending',
                reason TEXT,
                requested_date DATETIME,
                doctor_note TEXT,
                responded_at DATETIME,
                notes TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Bring databases created before the request/accept flow up to date. db.py
        # rewrites these to ADD COLUMN IF NOT EXISTS on PostgreSQL; on SQLite the
        # duplicate-column error is what tells us the column is already there.
        for column, column_type in (
            ('reason', 'TEXT'),
            ('requested_date', 'DATETIME'),
            ('doctor_note', 'TEXT'),
            ('responded_at', 'DATETIME'),
        ):
            try:
                conn.execute(f'ALTER TABLE appointments ADD COLUMN {column} {column_type}')
            except Exception:
                pass

        # A doctor answers by looking for what is waiting, and a patient by looking
        # for what has been decided. Without these the queue is a full scan and
        # older requests sit at the end of it.
        for index in (
            'CREATE INDEX IF NOT EXISTS idx_appointments_doctor ON appointments(doctor_id, status)',
            'CREATE INDEX IF NOT EXISTS idx_appointments_patient ON appointments(patient_id, status)',
        ):
            try:
                conn.execute(index)
            except Exception:
                pass
        
        conn.execute('''
            CREATE TABLE IF NOT EXISTS prescriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doctor_id TEXT NOT NULL,
                patient_id TEXT NOT NULL,
                medication_name TEXT NOT NULL,
                dosage TEXT,
                frequency TEXT,
                duration TEXT,
                notes TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.execute('''
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id TEXT NOT NULL,
                report_type TEXT,
                file_path TEXT,
                uploaded_by INTEGER,
                uploaded_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # A treatment plan is the doctor's side of the doctor/patient relationship:
        # doctor_id says who prescribed it, patient_id says who it is for. Those two
        # columns are the whole contract between the clinician write routes in
        # treatment_routes.py and the read-only view in patient_portal.py.
        conn.execute('''
            CREATE TABLE IF NOT EXISTS treatments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                doctor_id TEXT NOT NULL,
                patient_id TEXT NOT NULL,
                diagnosis_id INTEGER,
                title TEXT NOT NULL,
                treatment_type TEXT DEFAULT 'medication',
                description TEXT,
                medication_name TEXT,
                dosage TEXT,
                frequency TEXT,
                duration TEXT,
                instructions TEXT,
                status TEXT DEFAULT 'active',
                start_date DATE,
                end_date DATE,
                follow_up_date DATE,
                notes TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def add_diagnosis(self, doctor_id, patient_id, condition_name, condition_code=None, notes=None):
        """Add a new diagnosis with proper validation"""
        try:
            conn = db.connect(self.db_file)
            conn.execute('PRAGMA foreign_keys = OFF')
            
            cursor = conn.execute('''
                INSERT INTO diagnoses (doctor_id, patient_id, condition_code, condition_name, notes)
                VALUES (?, ?, ?, ?, ?)
            ''', (doctor_id, patient_id, condition_code, condition_name, notes))
            
            diagnosis_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            logger.info(f"Diagnosis added: ID {diagnosis_id}, Doctor {doctor_id}, Patient {patient_id}")
            return diagnosis_id
            
        except Exception as e:
            logger.error(f"Error adding diagnosis: {e}")
            raise
    
    def add_prescription(self, doctor_id, patient_id, medication_name, dosage=None, frequency=None, duration=None, notes=None):
        """Add a new prescription"""
        try:
            conn = db.connect(self.db_file)
            conn.execute('PRAGMA foreign_keys = ON')
            
            cursor = conn.execute('''
                INSERT INTO prescriptions (doctor_id, patient_id, medication_name, dosage, frequency, duration, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (doctor_id, patient_id, medication_name, dosage, frequency, duration, notes))
            
            prescription_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            return prescription_id
            
        except Exception as e:
            logger.error(f"Error adding prescription: {e}")
            raise

    # ------------------------------------------------------------------
    # Treatments
    #
    # Column names that add_treatment()/update_treatment() are allowed to write.
    # doctor_id, patient_id and id are deliberately absent: those decide who owns
    # the row, so they are set once on insert and never taken from user input on
    # update. Listed here so the insert and the update cannot drift apart.
    # ------------------------------------------------------------------
    TREATMENT_FIELDS = (
        'title',
        'treatment_type',
        'description',
        'medication_name',
        'dosage',
        'frequency',
        'duration',
        'instructions',
        'status',
        'start_date',
        'end_date',
        'follow_up_date',
        'notes',
    )

    # Columns typed DATE. SQLite would happily store an empty string here, but
    # PostgreSQL rejects '' with "invalid input syntax for type date", so an
    # untouched date input has to become NULL on the way in.
    TREATMENT_DATE_FIELDS = ('start_date', 'end_date', 'follow_up_date')

    @classmethod
    def _clean_treatment_values(cls, values):
        """Turn blank date inputs into None so both backends accept them."""
        cleaned = dict(values)
        for field in cls.TREATMENT_DATE_FIELDS:
            value = cleaned.get(field)
            if isinstance(value, str) and not value.strip():
                cleaned[field] = None
        return cleaned

    def add_treatment(self, doctor_id, patient_id, title, **fields):
        """Start a treatment plan for *patient_id* on behalf of *doctor_id*.

        Only keys named in TREATMENT_FIELDS are persisted; anything else in
        **fields is ignored rather than interpolated into SQL. title is an explicit
        parameter because it is required, so it has to be folded back into the
        field dict before the column list is derived from it.
        """
        fields = self._clean_treatment_values({**fields, 'title': title})
        columns = ['doctor_id', 'patient_id'] + [f for f in self.TREATMENT_FIELDS if f in fields]
        values = [doctor_id, patient_id] + [fields[f] for f in columns[2:]]

        placeholders = ', '.join('?' for _ in columns)
        column_list = ', '.join(columns)

        try:
            conn = db.connect(self.db_file)
            cursor = conn.execute(
                f'INSERT INTO treatments ({column_list}) VALUES ({placeholders})',
                tuple(values),
            )
            treatment_id = cursor.lastrowid
            conn.commit()
            conn.close()

            logger.info(
                f"Treatment added: ID {treatment_id}, Doctor {doctor_id}, Patient {patient_id}"
            )
            return treatment_id

        except Exception as e:
            logger.error(f"Error adding treatment: {e}")
            raise

    def update_treatment(self, treatment_id, data):
        """Change the clinical content of an existing treatment plan.

        Returns True when a row was updated, False when treatment_id does not
        exist. Ownership is *not* checked here: callers must verify that the
        signed-in clinician wrote this row (treatment_routes.py does), so that
        the rule stays visible at the route boundary rather than hidden here.
        """
        updates = self._clean_treatment_values(
            {k: v for k, v in data.items() if k in self.TREATMENT_FIELDS}
        )
        if not updates:
            return False

        assignments = ', '.join(f'{col} = ?' for col in updates)
        params = tuple(updates.values()) + (treatment_id,)

        try:
            conn = db.connect(self.db_file)
            cursor = conn.execute(
                f'UPDATE treatments SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
                params,
            )
            changed = cursor.rowcount
            conn.commit()
            conn.close()

            return bool(changed)

        except Exception as e:
            logger.error(f"Error updating treatment {treatment_id}: {e}")
            raise

    def delete_treatment(self, treatment_id):
        """Remove a treatment plan. Returns True when a row was deleted."""
        try:
            conn = db.connect(self.db_file)
            cursor = conn.execute('DELETE FROM treatments WHERE id = ?', (treatment_id,))
            changed = cursor.rowcount
            conn.commit()
            conn.close()

            return bool(changed)

        except Exception as e:
            logger.error(f"Error deleting treatment {treatment_id}: {e}")
            raise

    def get_treatment(self, treatment_id):
        """One treatment plan by primary key, or None."""
        try:
            conn = db.connect(self.db_file)
            conn.row_factory = db.Row

            cursor = conn.execute(
                'SELECT * FROM treatments WHERE id = ?', (treatment_id,)
            )
            row = cursor.fetchone()
            conn.close()

            return dict(row) if row else None

        except Exception as e:
            logger.error(f"Error fetching treatment {treatment_id}: {e}")
            return None

    def get_patient_treatments(self, patient_id):
        """Every treatment plan written for *patient_id*, newest first.

        This is the query behind the patient's dashboard, so it LEFT JOINs the
        doctor: a treatment whose doctor account was later removed must still be
        shown to the patient (with the author marked unavailable) rather than
        silently disappearing from their medical history.
        """
        if not patient_id:
            return []

        try:
            conn = db.connect(self.db_file)
            conn.row_factory = db.Row

            cursor = conn.execute('''
                SELECT t.*,
                       u.full_name as doctor_name,
                       u.email as doctor_email,
                       u.username as doctor_username
                FROM treatments t
                LEFT JOIN enhanced_users u ON t.doctor_id = u.doctor_id
                WHERE t.patient_id = ?
                ORDER BY t.created_at DESC, t.id DESC
            ''', (patient_id,))

            treatments = [dict(row) for row in cursor.fetchall()]
            conn.close()

            return treatments

        except Exception as e:
            logger.error(f"Error fetching treatments for patient {patient_id}: {e}")
            return []

    def get_doctor_treatments(self, doctor_id, patient_id=None):
        """Treatment plans written by *doctor_id*, optionally for one patient.

        patient_id scopes the result further but never widens it: a doctor only
        ever sees rows carrying their own doctor_id.
        """
        if not doctor_id:
            return []

        try:
            conn = db.connect(self.db_file)
            conn.row_factory = db.Row

            sql = '''
                SELECT t.*,
                       u.full_name as patient_name,
                       u.email as patient_email
                FROM treatments t
                LEFT JOIN enhanced_users u ON t.patient_id = u.patient_id
                WHERE t.doctor_id = ?
            '''
            params = [doctor_id]

            if patient_id:
                sql += ' AND t.patient_id = ?'
                params.append(patient_id)

            sql += ' ORDER BY t.created_at DESC, t.id DESC'

            cursor = conn.execute(sql, tuple(params))
            treatments = [dict(row) for row in cursor.fetchall()]
            conn.close()

            return treatments

        except Exception as e:
            logger.error(f"Error fetching treatments for doctor {doctor_id}: {e}")
            return []

    def get_patient_doctors(self, patient_id):
        """The distinct doctors who have written a treatment for *patient_id*.

        Returns one row per doctor with their contact details and how much of
        their treatment plan is still active. LEFT JOIN on doctor_id for the same
        reason as get_patient_treatments: an unrecognised author shows up as
        unavailable instead of dropping the treatment from the count.
        """
        if not patient_id:
            return []

        try:
            conn = db.connect(self.db_file)
            conn.row_factory = db.Row

            cursor = conn.execute('''
                SELECT t.doctor_id AS doctor_id,
                       u.full_name AS doctor_name,
                       u.email AS doctor_email,
                       u.username AS doctor_username,
                       COUNT(t.id) AS treatment_count,
                       SUM(CASE WHEN t.status = 'active' THEN 1 ELSE 0 END) AS active_count,
                       MAX(t.created_at) AS last_treatment_at
                FROM treatments t
                LEFT JOIN enhanced_users u ON t.doctor_id = u.doctor_id
                WHERE t.patient_id = ?
                GROUP BY t.doctor_id, u.full_name, u.email, u.username
                ORDER BY last_treatment_at DESC
            ''', (patient_id,))

            doctors = [dict(row) for row in cursor.fetchall()]
            conn.close()

            return doctors

        except Exception as e:
            logger.error(f"Error fetching doctors treating patient {patient_id}: {e}")
            return []

    def count_patient_active_treatments(self, patient_id):
        """How many of *patient_id*'s treatments are still active."""
        if not patient_id:
            return 0

        try:
            conn = db.connect(self.db_file)

            cursor = conn.execute(
                "SELECT COUNT(*) FROM treatments WHERE patient_id = ? AND status = 'active'",
                (patient_id,),
            )
            total = cursor.fetchone()[0]
            conn.close()

            return total

        except Exception as e:
            logger.error(f"Error counting active treatments for {patient_id}: {e}")
            return 0
    
    def add_appointment(self, doctor_id, patient_id, appointment_date, notes=None):
        """Record an appointment a clinician booked directly, already confirmed.

        This bypasses the request/accept flow on purpose: it is the "the patient is
        standing in front of me and I am booking them in now" path, so the status is
        spelled out rather than left to the column default, which is 'pending'.
        Patients booking for themselves go through request_appointment() instead.
        """
        try:
            conn = db.connect(self.db_file)
            conn.execute('PRAGMA foreign_keys = ON')
            
            cursor = conn.execute('''
                INSERT INTO appointments (doctor_id, patient_id, appointment_date, status, notes)
                VALUES (?, ?, ?, 'scheduled', ?)
            ''', (doctor_id, patient_id, appointment_date, notes))
            
            appointment_id = cursor.lastrowid
            conn.commit()
            conn.close()
            
            return appointment_id
            
        except Exception as e:
            logger.error(f"Error adding appointment: {e}")
            raise

    # ------------------------------------------------------------------
    # Appointments - the request/accept state machine
    #
    # The columns a caller may write are listed rather than taken from **kwargs so
    # a hand-crafted POST cannot reach a column it has no business touching.
    # doctor_id, patient_id and id are excluded on purpose: they decide who the
    # appointment is between, and who is allowed to answer it, so they are set once
    # on insert and never taken from the request.
    # ------------------------------------------------------------------

    #: Free-text the caller supplied. Validated by the routes, not here.
    APPOINTMENT_NOTE_FIELDS = ('reason', 'doctor_note', 'notes')

    @classmethod
    def _clean_appointment_values(cls, values):
        """Turn blank text inputs into None so both backends accept them.

        SQLite would store an empty string in a DATETIME column; PostgreSQL rejects
        '' with "invalid input syntax for type timestamp", so an untouched optional
        field has to become NULL on the way in.
        """
        cleaned = dict(values)
        for field in cls.APPOINTMENT_NOTE_FIELDS:
            value = cleaned.get(field)
            if isinstance(value, str) and not value.strip():
                cleaned[field] = None
        return cleaned

    def request_appointment(self, patient_id, doctor_id, requested_date,
                            reason=None, notes=None):
        """A patient asks *doctor_id* for an appointment on *requested_date*.

        The row lands as 'pending', which is the whole point: it is not yet an
        appointment, it is a request for one, and the doctor queue is what promotes
        it to 'scheduled'. requested_date is stored twice on purpose - once in
        appointment_date, which is what every date filter and sort reads, and once
        in requested_date, which survives a later reschedule.

        Returns the new row's id. Raises if the dates are unusable.
        """
        data = self._clean_appointment_values({'reason': reason, 'notes': notes})

        try:
            conn = db.connect(self.db_file)
            cursor = conn.execute('''
                INSERT INTO appointments
                    (doctor_id, patient_id, appointment_date, requested_date,
                     status, reason, notes)
                VALUES (?, ?, ?, ?, 'pending', ?, ?)
            ''', (
                doctor_id, patient_id, requested_date, requested_date,
                data['reason'], data['notes'],
            ))
            appointment_id = cursor.lastrowid
            conn.commit()
            conn.close()

            logger.info(
                f'Appointment requested: ID {appointment_id}, '
                f'Doctor {doctor_id}, Patient {patient_id}'
            )
            return appointment_id

        except Exception as e:
            logger.error(f'Error requesting appointment: {e}')
            raise

    def _update_appointment(self, appointment_id, assignments, params):
        """Shared UPDATE for the appointment transitions.

        Responded_at is stamped here so no caller can forget it, and the caller
        supplies the full set of assignments it wants written in one statement so a
        reschedule cannot half-apply. Returns True when a row changed.
        """
        if not assignments:
            return False

        sql = (
            f"UPDATE appointments SET {', '.join(assignments)}, "
            'responded_at = CURRENT_TIMESTAMP WHERE id = ?'
        )

        try:
            conn = db.connect(self.db_file)
            cursor = conn.execute(sql, tuple(params) + (appointment_id,))
            changed = cursor.rowcount
            conn.commit()
            conn.close()

            return bool(changed)

        except Exception as e:
            logger.error(f'Error updating appointment {appointment_id}: {e}')
            raise

    def accept_appointment(self, appointment_id, appointment_date=None, doctor_note=None):
        """The doctor confirms a request, optionally moving it to a different slot.

        appointment_date is what the doctor agreed to, so it is stored in
        appointment_date and the patient's original wish stays readable in
        requested_date. Passing None accepts the slot the patient asked for.
        """
        note = self._clean_appointment_values({'doctor_note': doctor_note})['doctor_note']

        assignments = ['status = ?']
        params = ['scheduled']
        if appointment_date is not None:
            assignments.append('appointment_date = ?')
            params.append(appointment_date)

        assignments.append('doctor_note = ?')
        params.append(note)

        return self._update_appointment(appointment_id, assignments, params)

    def decline_appointment(self, appointment_id, doctor_note=None):
        """The doctor turns a request down. terminal for this row."""
        note = self._clean_appointment_values({'doctor_note': doctor_note})['doctor_note']
        return self._update_appointment(
            appointment_id, ['status = ?', 'doctor_note = ?'], ['declined', note]
        )

    def reschedule_appointment(self, appointment_id, appointment_date, doctor_note=None):
        """Move an already-confirmed appointment to a new date.

        Keeps the status as 'scheduled' - the booking is still on, just at a
        different time - and leaves requested_date alone so the change is visible as
        the gap between what was asked for and what was agreed.
        """
        note = self._clean_appointment_values({'doctor_note': doctor_note})['doctor_note']
        return self._update_appointment(
            appointment_id,
            ['appointment_date = ?', 'doctor_note = ?'],
            [appointment_date, note],
        )

    def cancel_appointment(self, appointment_id):
        """Withdraw a booking. Used by the patient on their own pending request and
        by the doctor on one of their own confirmed appointments."""
        return self._update_appointment(appointment_id, ['status = ?'], ['cancelled'])

    #: Shared SELECT for every appointment read, so the two sides of the relationship
    #: are resolved the same way everywhere. Both JOINs are LEFT: an appointment whose
    #: patient or doctor account was later removed has to stay visible to whoever
    #: still holds it, marked unavailable, rather than vanish from their history.
    _APPOINTMENT_SELECT = '''
                SELECT a.*,
                       d.full_name AS doctor_name,
                       d.email AS doctor_email,
                       d.username AS doctor_username,
                       p.full_name AS patient_name,
                       p.email AS patient_email
                FROM appointments a
                LEFT JOIN enhanced_users d ON a.doctor_id = d.doctor_id
                LEFT JOIN enhanced_users p ON a.patient_id = p.patient_id
    '''

    #: Pending first, then everything still live, then the decided-and-dead. A patient
    #: should never have to scroll past a year of history to find a request they made
    #: this morning.
    _APPOINTMENT_ORDER = '''
                ORDER BY CASE a.status
                            WHEN 'pending' THEN 0
                            WHEN 'scheduled' THEN 1
                            WHEN 'cancelled' THEN 2
                            ELSE 3
                         END,
                         a.appointment_date DESC, a.id DESC
    '''

    def get_appointment(self, appointment_id):
        """One appointment by primary key, with both parties' names resolved."""
        if not appointment_id:
            return None

        try:
            conn = db.connect(self.db_file)
            conn.row_factory = db.Row

            cursor = conn.execute(f'''
                {self._APPOINTMENT_SELECT}
                WHERE a.id = ?
            ''', (appointment_id,))
            row = cursor.fetchone()
            conn.close()

            return dict(row) if row else None

        except Exception as e:
            logger.error(f'Error fetching appointment {appointment_id}: {e}')
            return None

    def get_patient_appointments(self, patient_id):
        """Every appointment *patient_id* has requested or been booked into.

        Reads only the session's own patient_id (see patient_portal.py), so this is
        the patient's whole appointment history and nothing else. Pending requests
        sort to the top for the same reason as on the doctor side.
        """
        if not patient_id:
            return []

        try:
            conn = db.connect(self.db_file)
            conn.row_factory = db.Row

            cursor = conn.execute(f'''
                {self._APPOINTMENT_SELECT}
                WHERE a.patient_id = ?
                {self._APPOINTMENT_ORDER}
            ''', (patient_id,))

            appointments = [dict(row) for row in cursor.fetchall()]
            conn.close()

            return appointments

        except Exception as e:
            logger.error(f'Error fetching appointments for patient {patient_id}: {e}')
            return []

    def get_doctor_appointments(self, doctor_id, statuses=None):
        """Appointments addressed to *doctor_id*, waiting ones first.

        This is the doctor's request queue, so statuses filters it down to what is
        still open ('pending') when they only want to work through their inbox.
        patient_id would only narrow an already doctor-scoped result.
        """
        if not doctor_id:
            return []

        try:
            conn = db.connect(self.db_file)
            conn.row_factory = db.Row

            sql = f'{self._APPOINTMENT_SELECT} WHERE a.doctor_id = ?'
            params = [doctor_id]

            if statuses:
                statuses = [s for s in statuses if s in APPOINTMENT_STATUSES]
                if statuses:
                    sql += f" AND a.status IN ({', '.join('?' for _ in statuses)})"
                    params.extend(statuses)

            sql += self._APPOINTMENT_ORDER

            cursor = conn.execute(sql, tuple(params))
            appointments = [dict(row) for row in cursor.fetchall()]
            conn.close()

            return appointments

        except Exception as e:
            logger.error(f'Error fetching appointments for doctor {doctor_id}: {e}')
            return []

    def count_doctor_appointments(self, doctor_id, statuses=None):
        """How many appointments a doctor has in the given states. Defaults to the
        ones still waiting on them."""
        if not doctor_id:
            return 0

        statuses = statuses or ('pending',)

        try:
            conn = db.connect(self.db_file)
            statuses = [s for s in statuses if s in APPOINTMENT_STATUSES]
            placeholders = ', '.join('?' for _ in statuses)
            cursor = conn.execute(
                f'SELECT COUNT(*) AS total FROM appointments '
                f'WHERE doctor_id = ? AND status IN ({placeholders})',
                (doctor_id, *statuses),
            )
            row = cursor.fetchone()
            total = row['total'] if hasattr(row, 'keys') else row[0]
            conn.close()

            return int(total or 0)

        except Exception as e:
            logger.error(f'Error counting appointments for doctor {doctor_id}: {e}')
            return 0

    def get_available_doctors(self):
        """The doctors a patient is allowed to request an appointment with.

        Every active account carrying a doctor_id. doctor_id rather than username,
        because that is what appointments store and it does not change when a
        clinician renames their account.
        """
        try:
            conn = db.connect(self.db_file)
            conn.row_factory = db.Row

            cursor = conn.execute('''
                SELECT doctor_id, full_name, email, username
                FROM enhanced_users
                WHERE role = 'doctor' AND is_active = 1 AND doctor_id IS NOT NULL
                ORDER BY full_name ASC
            ''')

            doctors = [dict(row) for row in cursor.fetchall()]
            conn.close()

            return doctors

        except Exception as e:
            logger.error(f'Error fetching available doctors: {e}')
            return []
    
    def get_patient_diagnoses(self, patient_id):
        """Get all diagnoses for a specific patient with doctor information"""
        try:
            conn = db.connect(self.db_file)
            conn.row_factory = db.Row
            
            cursor = conn.execute('''
                SELECT d.*, u.full_name as doctor_name, u.email as doctor_email, d.doctor_id
                FROM diagnoses d
                JOIN enhanced_users u ON d.doctor_id = u.doctor_id
                WHERE d.patient_id = ?
                ORDER BY d.created_at DESC
            ''', (patient_id,))
            
            diagnoses = [dict(row) for row in cursor.fetchall()]
            conn.close()
            
            return diagnoses
            
        except Exception as e:
            logger.error(f"Error fetching patient diagnoses: {e}")
            return []
    
    def get_patient_prescriptions(self, patient_id):
        """Get all prescriptions for a specific patient"""
        try:
            conn = db.connect(self.db_file)
            conn.row_factory = db.Row
            
            cursor = conn.execute('''
                SELECT p.*, u.full_name as doctor_name
                FROM prescriptions p
                JOIN enhanced_users u ON p.doctor_id = u.doctor_id
                WHERE p.patient_id = ?
                ORDER BY p.created_at DESC
            ''', (patient_id,))
            
            prescriptions = [dict(row) for row in cursor.fetchall()]
            conn.close()
            
            return prescriptions
            
        except Exception as e:
            logger.error(f"Error fetching patient prescriptions: {e}")
            return []
    
    def get_doctor_diagnoses(self, doctor_id):
        """Get all diagnoses created by a specific doctor"""
        try:
            conn = db.connect(self.db_file)
            conn.row_factory = db.Row
            
            cursor = conn.execute('''
                SELECT d.*, p.full_name as patient_name, p.email as patient_email
                FROM diagnoses d
                JOIN enhanced_users p ON d.patient_id = p.patient_id
                WHERE d.doctor_id = ?
                ORDER BY d.created_at DESC
            ''', (doctor_id,))
            
            diagnoses = [dict(row) for row in cursor.fetchall()]
            conn.close()
            
            return diagnoses
            
        except Exception as e:
            logger.error(f"Error fetching doctor diagnoses: {e}")
            return []
    
    def validate_doctor_patient_relationship(self, doctor_id, patient_id):
        """Validate that doctor can add diagnosis for this patient"""
        # For now, allow any doctor to add diagnosis for any patient
        # In a real system, you'd check if patient is assigned to doctor
        return True
    
    def get_all_patients(self):
        """Get all patients for doctor dashboard"""
        try:
            conn = db.connect(self.db_file)
            conn.row_factory = db.Row
            
            cursor = conn.execute('''
                SELECT patient_id, full_name, email, created_at
                FROM enhanced_users
                WHERE role = 'patient' AND is_active = 1
                ORDER BY created_at DESC
            ''')
            
            patients = [dict(row) for row in cursor.fetchall()]
            conn.close()
            
            return patients
            
        except Exception as e:
            logger.error(f"Error fetching patients: {e}")
            return []