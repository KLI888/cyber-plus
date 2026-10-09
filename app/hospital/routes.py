from datetime import datetime, timedelta
from threading import Lock
from flask import Blueprint, request, jsonify
from flask_jwt_extended import get_jwt, get_jwt_identity

from app.models import db, Department, DoctorProfile, User, Appointment, MedicalRecord, Patient, PublicInquiry
from app.auth.rbac import role_required

hospital_bp = Blueprint("hospital", __name__)
public_bp = Blueprint("public", __name__)

_INQUIRY_GUARD = {}
_INQUIRY_LOCK = Lock()

def _inquiry_limited(ip):
    now = datetime.utcnow()
    with _INQUIRY_LOCK:
        bucket = _INQUIRY_GUARD.setdefault(ip, [])
        bucket[:] = [t for t in bucket if t > now - timedelta(minutes=15)]
        if len(bucket) >= 4:
            return True
        bucket.append(now)
        return False


# ---------------------------------------------------------------------------
# Public endpoints -- no auth. This is what the homepage renders for a
# visitor who hasn't logged in at all.
# ---------------------------------------------------------------------------

@public_bp.route("/departments", methods=["GET"])
def public_departments():
    depts = Department.query.order_by(Department.name).all()
    return jsonify([d.to_dict(include_doctor_count=True) for d in depts]), 200


@public_bp.route("/doctors", methods=["GET"])
def public_doctors():
    profiles = DoctorProfile.query.join(User).filter(User.is_active.is_(True)).all()
    out = []
    for p in profiles:
        out.append({
            "name": p.user.full_name or p.user.username,
            "specialization": p.specialization,
            "qualification": p.qualification,
            "years_experience": p.years_experience,
            "department": p.department.name if p.department else None,
            "bio": p.bio,
        })
    return jsonify(out), 200




@public_bp.route("/inquiries", methods=["POST"])
def public_inquiry():
    """Accept a non-clinical appointment/contact request from the public site.
    No authentication is required, but input is strictly bounded and rate-limited.
    The endpoint must never accept diagnosis, prescription, or medical-record fields.
    """
    if _inquiry_limited(request.remote_addr or "unknown"):
        return jsonify({"error": "rate_limited", "message": "Too many requests. Please try again later."}), 429
    data = request.get_json(silent=True) or {}
    allowed = {"name", "email", "phone", "department", "message"}
    if set(data) - allowed:
        return jsonify({"error": "invalid_fields", "message": "Only public inquiry fields are accepted."}), 400
    name = str(data.get("name", "")).strip()
    email = str(data.get("email", "")).strip().lower()
    phone = str(data.get("phone", "")).strip()
    department = str(data.get("department", "")).strip()
    message = str(data.get("message", "")).strip()
    if not all((name, email, phone, department, message)):
        return jsonify({"error": "validation", "message": "All fields are required."}), 400
    if len(name) > 120 or len(email) > 160 or len(phone) > 30 or len(department) > 100 or len(message) > 1000:
        return jsonify({"error": "validation", "message": "One or more fields exceed the allowed length."}), 400
    import re
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        return jsonify({"error": "validation", "message": "Enter a valid email address."}), 400
    if not re.fullmatch(r"[0-9+() .-]{7,30}", phone):
        return jsonify({"error": "validation", "message": "Enter a valid phone number."}), 400
    if not Department.query.filter_by(name=department).first():
        return jsonify({"error": "validation", "message": "Please select a valid department."}), 400
    inquiry = PublicInquiry(name=name, email=email, phone=phone, department=department, message=message)
    db.session.add(inquiry)
    db.session.commit()
    return jsonify({"message": "Your request has been received. The hospital team will contact you."}), 201

# ---------------------------------------------------------------------------
# Departments (admin manages, everyone authenticated can read)
# ---------------------------------------------------------------------------

@hospital_bp.route("/departments", methods=["GET"])
@role_required("admin", "doctor", "staff")
def list_departments():
    return jsonify([d.to_dict(include_doctor_count=True) for d in Department.query.order_by(Department.name)]), 200


@hospital_bp.route("/departments", methods=["POST"])
@role_required("admin")
def create_department():
    data = request.get_json(force=True) or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    if Department.query.filter_by(name=name).first():
        return jsonify({"error": "department already exists"}), 409
    dept = Department(name=name, description=data.get("description", ""), icon=data.get("icon", "🩺"))
    db.session.add(dept)
    db.session.commit()
    return jsonify(dept.to_dict()), 201


@hospital_bp.route("/departments/<int:dept_id>", methods=["PATCH"])
@role_required("admin")
def update_department(dept_id):
    dept = Department.query.get_or_404(dept_id)
    data = request.get_json(force=True) or {}
    if "name" in data:
        name = str(data["name"]).strip()
        if not name:
            return jsonify({"error": "name cannot be empty"}), 400
        clash = Department.query.filter(Department.name == name, Department.id != dept_id).first()
        if clash:
            return jsonify({"error": "department already exists"}), 409
        dept.name = name
    for field in ("description", "icon"):
        if field in data:
            setattr(dept, field, data[field])
    db.session.commit()
    return jsonify(dept.to_dict()), 200


@hospital_bp.route("/departments/<int:dept_id>", methods=["DELETE"])
@role_required("admin")
def delete_department(dept_id):
    dept = Department.query.get_or_404(dept_id)
    db.session.delete(dept)
    db.session.commit()
    return jsonify({"message": "deleted"}), 200


# ---------------------------------------------------------------------------
# Doctor profiles (clinical-facing detail for a role='doctor' user)
# ---------------------------------------------------------------------------

@hospital_bp.route("/doctors", methods=["GET"])
@role_required("admin", "doctor", "staff")
def list_doctors():
    doctors = User.query.filter(
        User.role == "doctor",
        User.is_active.is_(True),
        User.is_blocked.is_(False),
    ).order_by(User.full_name, User.username).all()
    return jsonify([{
        "id": doctor.id,
        "full_name": doctor.full_name or doctor.username,
        "username": doctor.username,
        "department_id": doctor.doctor_profile.department_id if doctor.doctor_profile else None,
        "department_name": doctor.doctor_profile.department.name if doctor.doctor_profile and doctor.doctor_profile.department else None,
        "specialization": doctor.doctor_profile.specialization if doctor.doctor_profile else None,
        "qualification": doctor.doctor_profile.qualification if doctor.doctor_profile else None,
        "years_experience": doctor.doctor_profile.years_experience if doctor.doctor_profile else None,
    } for doctor in doctors]), 200


@hospital_bp.route("/doctors/<int:user_id>/profile", methods=["PUT"])
@role_required("admin")
def upsert_doctor_profile(user_id):
    """Admin sets/updates a doctor's public-facing clinical profile.
    Called right after creating a user with role='doctor'."""
    user = User.query.get_or_404(user_id)
    if user.role != "doctor":
        return jsonify({"error": "user is not a doctor"}), 400

    data = request.get_json(force=True) or {}
    profile = DoctorProfile.query.filter_by(user_id=user_id).first()
    if not profile:
        profile = DoctorProfile(user_id=user_id)
        db.session.add(profile)

    profile.department_id = data.get("department_id", profile.department_id)
    profile.specialization = data.get("specialization", profile.specialization)
    profile.qualification = data.get("qualification", profile.qualification)
    profile.years_experience = data.get("years_experience", profile.years_experience)
    profile.bio = data.get("bio", profile.bio)
    db.session.commit()
    return jsonify(profile.to_dict()), 200


# ---------------------------------------------------------------------------
# Appointments -- staff schedules, doctor works their queue, admin sees all
# ---------------------------------------------------------------------------

@hospital_bp.route("/appointments", methods=["GET"])
@role_required("admin", "doctor", "staff")
def list_appointments():
    claims = get_jwt()
    role = claims.get("role")
    identity = get_jwt_identity()

    query = Appointment.query
    if role == "doctor":
        # Doctors only see their own queue, not the whole hospital's
        query = query.filter_by(doctor_id=int(identity))

    patient_id = request.args.get("patient_id", type=int)
    if patient_id:
        query = query.filter_by(patient_id=patient_id)

    status = request.args.get("status")
    if status:
        query = query.filter_by(status=status)

    appts = query.order_by(Appointment.scheduled_at.desc()).limit(200).all()
    return jsonify([a.to_dict() for a in appts]), 200


@hospital_bp.route("/appointments", methods=["POST"])
@role_required("admin", "staff", "doctor")
def create_appointment():
    data = request.get_json(force=True) or {}
    claims = get_jwt()

    required = ("patient_id", "doctor_id", "scheduled_at")
    if not all(data.get(f) for f in required):
        return jsonify({"error": f"required fields: {required}"}), 400

    doctor = User.query.get(data["doctor_id"])
    if not doctor or doctor.role != "doctor" or not doctor.is_active or doctor.is_blocked:
        return jsonify({"error": "doctor_id must reference an active doctor"}), 400
    if claims.get("role") == "doctor" and int(get_jwt_identity()) != doctor.id:
        return jsonify({"error": "forbidden", "message": "doctors can only create appointments for themselves"}), 403
    if not Patient.query.get(data["patient_id"]):
        return jsonify({"error": "patient not found"}), 404
    if data.get("department_id") and not Department.query.get(data["department_id"]):
        return jsonify({"error": "department not found"}), 404

    try:
        scheduled_at = datetime.fromisoformat(data["scheduled_at"])
    except ValueError:
        return jsonify({"error": "scheduled_at must be ISO 8601, e.g. 2026-10-01T10:30:00"}), 400

    appt = Appointment(
        patient_id=data["patient_id"],
        doctor_id=data["doctor_id"],
        department_id=data.get("department_id"),
        scheduled_at=scheduled_at,
        reason=data.get("reason", ""),
        created_by=int(claims.get("sub", 0)) if claims.get("sub") else None,
    )
    db.session.add(appt)
    db.session.commit()
    return jsonify(appt.to_dict()), 201


@hospital_bp.route("/appointments/<int:appt_id>", methods=["PATCH"])
@role_required("admin", "staff", "doctor")
def update_appointment(appt_id):
    appt = Appointment.query.get_or_404(appt_id)
    claims = get_jwt()
    identity = get_jwt_identity()

    if claims.get("role") == "doctor" and appt.doctor_id != int(identity):
        return jsonify({"error": "forbidden", "message": "not your appointment"}), 403

    data = request.get_json(force=True) or {}
    if "status" in data:
        if data["status"] not in ("scheduled", "completed", "cancelled", "no_show"):
            return jsonify({"error": "invalid status"}), 400
        appt.status = data["status"]
    if "reason" in data:
        appt.reason = data["reason"]
    if "scheduled_at" in data:
        try:
            appt.scheduled_at = datetime.fromisoformat(data["scheduled_at"])
        except ValueError:
            return jsonify({"error": "scheduled_at must be ISO 8601"}), 400

    db.session.commit()
    return jsonify(appt.to_dict()), 200


# ---------------------------------------------------------------------------
# Medical Records -- the sensitive clinical layer. Doctor-authored only;
# staff has NO access here at all, by design (least privilege).
# ---------------------------------------------------------------------------

@hospital_bp.route("/medical-records", methods=["GET"])
@role_required("admin", "doctor")
def list_medical_records():
    claims = get_jwt()
    identity = get_jwt_identity()

    query = MedicalRecord.query
    if claims.get("role") == "doctor":
        query = query.filter_by(doctor_id=int(identity))

    patient_id = request.args.get("patient_id", type=int)
    if patient_id:
        query = query.filter_by(patient_id=patient_id)

    records = query.order_by(MedicalRecord.visit_date.desc()).limit(200).all()
    return jsonify([r.to_dict() for r in records]), 200


@hospital_bp.route("/medical-records", methods=["POST"])
@role_required("admin", "doctor")
def create_medical_record():
    data = request.get_json(force=True) or {}
    claims = get_jwt()
    identity = get_jwt_identity()

    if not data.get("patient_id"):
        return jsonify({"error": "patient_id is required"}), 400
    if not Patient.query.get(data["patient_id"]):
        return jsonify({"error": "patient not found"}), 404

    # Doctors author records as themselves; an admin filling in on their
    # behalf must say whose record it is
    if claims.get("role") == "doctor":
        doctor_id = int(identity)
    else:
        if not data.get("doctor_id"):
            return jsonify({"error": "doctor_id is required when an administrator creates a record"}), 400
        try:
            doctor_id = int(data["doctor_id"])
        except (TypeError, ValueError):
            return jsonify({"error": "doctor_id must be an integer"}), 400
    doctor = User.query.get(doctor_id)
    if not doctor or doctor.role != "doctor" or not doctor.is_active or doctor.is_blocked:
        return jsonify({"error": "doctor_id must reference an active doctor"}), 400
    if data.get("appointment_id"):
        appt = Appointment.query.get(data["appointment_id"])
        if not appt:
            return jsonify({"error": "appointment not found"}), 404
        if appt.patient_id != int(data["patient_id"]):
            return jsonify({"error": "appointment does not belong to this patient"}), 400
        if claims.get("role") == "doctor" and appt.doctor_id != int(identity):
            return jsonify({"error": "forbidden", "message": "appointment belongs to another doctor"}), 403
        if appt.doctor_id != doctor_id:
            return jsonify({"error": "appointment doctor does not match record doctor"}), 400

    visit_date = datetime.utcnow()
    if data.get("visit_date"):
        try:
            visit_date = datetime.fromisoformat(data["visit_date"])
        except ValueError:
            return jsonify({"error": "visit_date must be ISO 8601"}), 400

    record = MedicalRecord(
        patient_id=data["patient_id"],
        doctor_id=doctor_id,
        appointment_id=data.get("appointment_id"),
        visit_date=visit_date,
        blood_pressure=data.get("blood_pressure"),
        heart_rate_bpm=data.get("heart_rate_bpm"),
        temperature_c=data.get("temperature_c"),
        weight_kg=data.get("weight_kg"),
        diagnosis=data.get("diagnosis", ""),
        prescription=data.get("prescription", ""),
        notes=data.get("notes", ""),
    )
    db.session.add(record)

    # If this record closes out an appointment, mark it completed
    if data.get("appointment_id"):
        appt = Appointment.query.get(data["appointment_id"])
        if appt:
            appt.status = "completed"

    db.session.commit()
    return jsonify(record.to_dict()), 201
