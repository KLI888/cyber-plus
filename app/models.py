from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    # Principle of least privilege: role gates every endpoint
    role = db.Column(db.String(20), nullable=False, default="staff")  # admin | doctor | staff
    full_name = db.Column(db.String(120))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Any access/refresh token issued *before* this timestamp is treated as
    # revoked (see token_in_blocklist_loader in app/__init__.py). This is
    # what lets the ML engine or an admin kill every live session for a
    # user instantly, without needing to know that session's specific JWT ID.
    sessions_revoked_at = db.Column(db.DateTime, nullable=True)

    # Separate from is_active (which an admin uses for routine
    # deactivation): is_blocked is specifically the anomaly-engine's
    # kill switch. A blocked user cannot even reach /auth/login again --
    # not just "logged out" -- until an admin explicitly unblocks them.
    is_blocked = db.Column(db.Boolean, default=False)
    blocked_reason = db.Column(db.String(255), nullable=True)
    blocked_at = db.Column(db.DateTime, nullable=True)

    doctor_profile = db.relationship("DoctorProfile", backref="user", uselist=False,
                                      cascade="all, delete-orphan")

    def set_password(self, raw_password):
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        return check_password_hash(self.password_hash, raw_password)

    def to_dict(self):
        data = {
            "id": self.id,
            "username": self.username,
            "role": self.role,
            "full_name": self.full_name,
            "is_active": self.is_active,
            "is_blocked": self.is_blocked,
            "blocked_reason": self.blocked_reason,
            "blocked_at": self.blocked_at.isoformat() if self.blocked_at else None,
        }
        if self.doctor_profile:
            data["doctor_profile"] = self.doctor_profile.to_dict()
        return data


class Department(db.Model):
    """A clinical department (Cardiology, Pediatrics, ...). Public-facing --
    listed on the hospital homepage with no auth required."""

    __tablename__ = "departments"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    description = db.Column(db.Text)
    icon = db.Column(db.String(10), default="🩺")  # small emoji glyph for the homepage strip
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    doctors = db.relationship("DoctorProfile", backref="department", lazy=True)

    def to_dict(self, include_doctor_count=False):
        data = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "icon": self.icon,
        }
        if include_doctor_count:
            data["doctor_count"] = len(self.doctors)
        return data


class DoctorProfile(db.Model):
    """Extra clinical-facing info for a User with role='doctor'. Kept
    separate from User so the public site can show name/specialization
    without exposing account internals."""

    __tablename__ = "doctor_profiles"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey("departments.id"), nullable=True)
    specialization = db.Column(db.String(120))
    qualification = db.Column(db.String(120))
    years_experience = db.Column(db.Integer, default=0)
    bio = db.Column(db.Text)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "doctor_name": self.user.full_name or self.user.username if self.user else None,
            "department_id": self.department_id,
            "department_name": self.department.name if self.department else None,
            "specialization": self.specialization,
            "qualification": self.qualification,
            "years_experience": self.years_experience,
            "bio": self.bio,
        }


class Patient(db.Model):
    """Core patient registry. Registered by staff or admin; clinical detail
    (diagnoses, prescriptions) lives in MedicalRecord, not here -- this
    table is demographic/administrative data, not PHI in the clinical sense."""

    __tablename__ = "patients"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    date_of_birth = db.Column(db.Date, nullable=True)
    gender = db.Column(db.String(20))
    phone = db.Column(db.String(20))
    email = db.Column(db.String(120))
    address = db.Column(db.String(255))
    blood_group = db.Column(db.String(5))
    emergency_contact_name = db.Column(db.String(120))
    emergency_contact_phone = db.Column(db.String(20))
    known_allergies = db.Column(db.String(255))
    notes = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    appointments = db.relationship("Appointment", backref="patient", lazy=True,
                                    cascade="all, delete-orphan")
    medical_records = db.relationship("MedicalRecord", backref="patient", lazy=True,
                                       cascade="all, delete-orphan")

    def to_dict(self, include_clinical_summary=False):
        data = {
            "id": self.id,
            "name": self.name,
            "date_of_birth": self.date_of_birth.isoformat() if self.date_of_birth else None,
            "gender": self.gender,
            "phone": self.phone,
            "email": self.email,
            "address": self.address,
            "blood_group": self.blood_group,
            "emergency_contact_name": self.emergency_contact_name,
            "emergency_contact_phone": self.emergency_contact_phone,
            "known_allergies": self.known_allergies,
            "notes": self.notes,
            "created_at": self.created_at.isoformat(),
        }
        if include_clinical_summary:
            data["appointment_count"] = len(self.appointments)
            data["record_count"] = len(self.medical_records)
        return data


class Appointment(db.Model):
    """Scheduling data -- who is booked to see whom, when. Staff and admin
    create these; doctors and admin see their own queue."""

    __tablename__ = "appointments"

    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey("departments.id"), nullable=True)
    scheduled_at = db.Column(db.DateTime, nullable=False)
    reason = db.Column(db.String(255))
    status = db.Column(db.String(20), default="scheduled")  # scheduled|completed|cancelled|no_show
    created_by = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    doctor = db.relationship("User", foreign_keys=[doctor_id])
    department = db.relationship("Department", foreign_keys=[department_id])

    def to_dict(self):
        return {
            "id": self.id,
            "patient_id": self.patient_id,
            "patient_name": self.patient.name if self.patient else None,
            "doctor_id": self.doctor_id,
            "doctor_name": self.doctor.full_name or self.doctor.username if self.doctor else None,
            "department_id": self.department_id,
            "department_name": self.department.name if self.department else None,
            "scheduled_at": self.scheduled_at.isoformat(),
            "reason": self.reason,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
        }


class MedicalRecord(db.Model):
    """A single clinical visit note: vitals, diagnosis, prescription.
    Doctor-authored only -- this is the one table staff cannot write to,
    matching the least-privilege split the paper argues for."""

    __tablename__ = "medical_records"

    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    appointment_id = db.Column(db.Integer, db.ForeignKey("appointments.id"), nullable=True)
    visit_date = db.Column(db.DateTime, default=datetime.utcnow)

    # Vitals
    blood_pressure = db.Column(db.String(20))
    heart_rate_bpm = db.Column(db.Integer)
    temperature_c = db.Column(db.Float)
    weight_kg = db.Column(db.Float)

    diagnosis = db.Column(db.Text)
    prescription = db.Column(db.Text)
    notes = db.Column(db.Text)

    doctor = db.relationship("User", foreign_keys=[doctor_id])

    def to_dict(self):
        return {
            "id": self.id,
            "patient_id": self.patient_id,
            "patient_name": self.patient.name if self.patient else None,
            "doctor_id": self.doctor_id,
            "doctor_name": self.doctor.full_name or self.doctor.username if self.doctor else None,
            "appointment_id": self.appointment_id,
            "visit_date": self.visit_date.isoformat(),
            "blood_pressure": self.blood_pressure,
            "heart_rate_bpm": self.heart_rate_bpm,
            "temperature_c": self.temperature_c,
            "weight_kg": self.weight_kg,
            "diagnosis": self.diagnosis,
            "prescription": self.prescription,
            "notes": self.notes,
        }


class ActivityLog(db.Model):
    """Continuous Data Collection and Logging layer (Section VI-C of the paper).

    Every authenticated request is written here. This table is what the
    ML engine scores in real time for anomalous behaviour.
    """

    __tablename__ = "activity_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    username = db.Column(db.String(80))
    role = db.Column(db.String(20))
    endpoint = db.Column(db.String(255))
    method = db.Column(db.String(10))
    ip_address = db.Column(db.String(45))
    status_code = db.Column(db.Integer)
    patient_id_accessed = db.Column(db.Integer, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    # Filled in by the ML engine after scoring
    anomaly_score = db.Column(db.Float, nullable=True)
    risk_level = db.Column(db.String(20), default="unscored")  # unscored|normal|suspicious|critical

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "role": self.role,
            "endpoint": self.endpoint,
            "method": self.method,
            "ip_address": self.ip_address,
            "status_code": self.status_code,
            "patient_id_accessed": self.patient_id_accessed,
            "timestamp": self.timestamp.isoformat(),
            "anomaly_score": self.anomaly_score,
            "risk_level": self.risk_level,
        }


class RevokedSession(db.Model):
    """Automated Threat Mitigation (Section VI-E). JTI of any token killed
    by the ML engine gets stored here; the JWT loader checks this table
    on every request to enforce the revocation instantly."""

    __tablename__ = "revoked_sessions"

    id = db.Column(db.Integer, primary_key=True)
    jti = db.Column(db.String(64), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    reason = db.Column(db.String(255))
    revoked_at = db.Column(db.DateTime, default=datetime.utcnow)


class PublicInquiry(db.Model):
    """Non-clinical inquiry submitted by public website visitors.
    Never stores medical records or diagnosis information.
    """
    __tablename__ = "public_inquiries"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(160), nullable=False)
    phone = db.Column(db.String(30), nullable=False)
    department = db.Column(db.String(100), nullable=False)
    message = db.Column(db.String(1000), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    status = db.Column(db.String(20), default="new")
