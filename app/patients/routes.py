from datetime import datetime
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt
from app.models import db, Patient
from app.auth.rbac import role_required

patients_bp = Blueprint("patients", __name__)


@patients_bp.route("", methods=["GET"])
@role_required("admin", "doctor", "staff")
def list_patients():
    search = request.args.get("q", "").strip()
    query = Patient.query
    if search:
        query = query.filter(Patient.name.ilike(f"%{search}%"))
    patients = query.order_by(Patient.created_at.desc()).all()
    return jsonify([p.to_dict(include_clinical_summary=True) for p in patients]), 200


@patients_bp.route("/<int:patient_id>", methods=["GET"])
@role_required("admin", "doctor", "staff")
def get_patient(patient_id):
    # Demographic/administrative record -- staff needs this to register
    # visits and schedule appointments. Clinical detail (diagnosis,
    # prescription) lives in /api/medical-records, which staff cannot reach.
    patient = Patient.query.get_or_404(patient_id)
    return jsonify(patient.to_dict(include_clinical_summary=True)), 200


@patients_bp.route("", methods=["POST"])
@role_required("admin", "doctor", "staff")
def create_patient():
    data = request.get_json(force=True) or {}
    claims = get_jwt()

    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400

    dob = None
    if data.get("date_of_birth"):
        try:
            dob = datetime.strptime(data["date_of_birth"], "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"error": "date_of_birth must be YYYY-MM-DD"}), 400

    patient = Patient(
        name=name,
        date_of_birth=dob,
        gender=data.get("gender", ""),
        phone=data.get("phone", ""),
        email=data.get("email", ""),
        address=data.get("address", ""),
        blood_group=data.get("blood_group", ""),
        emergency_contact_name=data.get("emergency_contact_name", ""),
        emergency_contact_phone=data.get("emergency_contact_phone", ""),
        known_allergies=data.get("known_allergies", ""),
        notes=data.get("notes", ""),
        created_by=int(claims.get("sub", 0)) if claims.get("sub") else None,
    )
    db.session.add(patient)
    db.session.commit()
    return jsonify(patient.to_dict()), 201


@patients_bp.route("/<int:patient_id>", methods=["PATCH"])
@role_required("admin", "doctor", "staff")
def update_patient(patient_id):
    patient = Patient.query.get_or_404(patient_id)
    data = request.get_json(force=True) or {}

    editable = ("name", "gender", "phone", "email", "address", "blood_group",
                "emergency_contact_name", "emergency_contact_phone",
                "known_allergies", "notes")
    for field in editable:
        if field in data:
            setattr(patient, field, data[field])

    if "date_of_birth" in data and data["date_of_birth"]:
        try:
            patient.date_of_birth = datetime.strptime(data["date_of_birth"], "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"error": "date_of_birth must be YYYY-MM-DD"}), 400

    db.session.commit()
    return jsonify(patient.to_dict()), 200


@patients_bp.route("/<int:patient_id>", methods=["DELETE"])
@role_required("admin")  # only admins can delete patient records
def delete_patient(patient_id):
    patient = Patient.query.get_or_404(patient_id)
    db.session.delete(patient)
    db.session.commit()
    return jsonify({"message": "deleted"}), 200
