from datetime import datetime
from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt, get_jwt_identity
from sqlalchemy.exc import IntegrityError
from app.models import db, User, ActivityLog, RevokedSession, DoctorProfile, Patient, Appointment, Department, MedicalRecord
from app.auth.rbac import role_required

admin_bp = Blueprint("admin", __name__)


ALLOWED_ROLES = {"admin", "doctor", "staff"}


@admin_bp.route("/users", methods=["GET"])
@role_required("admin")
def list_users():
    role = request.args.get("role")
    query = User.query
    if role:
        query = query.filter_by(role=role)
    return jsonify([u.to_dict() for u in query.all()]), 200


@admin_bp.route("/users", methods=["POST"])
@role_required("admin")
def create_user():
    """Admin-created account -- separate from the public /auth/register
    (which you may want to remove entirely in a real deployment; admins
    provisioning every login is the more realistic HIS workflow).

    If role='doctor', you can optionally pass department_id/specialization/
    qualification/years_experience/bio and the doctor's public profile is
    created in the same call (otherwise use PUT /doctors/<id>/profile later)."""
    data = request.get_json(force=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")
    role = data.get("role", "staff")
    full_name = data.get("full_name", "").strip()

    if not username or not password:
        return jsonify({"error": "username and password are required"}), 400
    if role not in ALLOWED_ROLES:
        return jsonify({"error": f"role must be one of {sorted(ALLOWED_ROLES)}"}), 400
    if len(password) < 6:
        return jsonify({"error": "password must be at least 6 characters"}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({"error": "username already exists"}), 409

    user = User(username=username, role=role, full_name=full_name or username)
    user.set_password(password)
    db.session.add(user)
    db.session.flush()  # get user.id before commit, for the doctor profile below

    if role == "doctor" and any(k in data for k in
                                 ("department_id", "specialization", "qualification",
                                  "years_experience", "bio")):
        db.session.add(DoctorProfile(
            user_id=user.id,
            department_id=data.get("department_id"),
            specialization=data.get("specialization", ""),
            qualification=data.get("qualification", ""),
            years_experience=data.get("years_experience", 0),
            bio=data.get("bio", ""),
        ))

    db.session.commit()
    return jsonify({"message": "user created", "user": user.to_dict()}), 201


@admin_bp.route("/users/<int:user_id>", methods=["PATCH"])
@role_required("admin")
def update_user(user_id):
    """Partial update: any of username, full_name, role, password, is_active.
    (Blocking/unblocking has its own dedicated endpoints below, since
    that's a security action worth its own audit trail rather than a
    silent field flip.)"""
    user = User.query.get_or_404(user_id)
    data = request.get_json(force=True) or {}

    if "full_name" in data:
        user.full_name = data["full_name"]
    if "username" in data:
        new_username = data["username"].strip()
        if not new_username:
            return jsonify({"error": "username cannot be empty"}), 400
        clash = User.query.filter_by(username=new_username).first()
        if clash and clash.id != user.id:
            return jsonify({"error": "username already exists"}), 409
        user.username = new_username

    if "role" in data:
        if data["role"] not in ALLOWED_ROLES:
            return jsonify({"error": f"role must be one of {sorted(ALLOWED_ROLES)}"}), 400
        if data["role"] != user.role:
            user.role = data["role"]
            user.sessions_revoked_at = datetime.utcnow()

    if "password" in data and data["password"]:
        if len(data["password"]) < 6:
            return jsonify({"error": "password must be at least 6 characters"}), 400
        user.set_password(data["password"])
        # Changing the password is itself a good moment to invalidate any
        # old sessions, independent of the ML engine.
        user.sessions_revoked_at = datetime.utcnow()

    if "is_active" in data:
        value = data["is_active"]
        if not isinstance(value, bool):
            return jsonify({"error": "is_active must be a boolean"}), 400
        user.is_active = value
        if not value:
            user.sessions_revoked_at = datetime.utcnow()

    db.session.commit()
    return jsonify({"message": "user updated", "user": user.to_dict()}), 200


@admin_bp.route("/users/<int:user_id>/block", methods=["POST"])
@role_required("admin")
def block_user(user_id):
    """Manual equivalent of what the ML engine does automatically:
    lock the account and kill every live session for it."""
    user = User.query.get_or_404(user_id)
    if user.id == int(get_jwt_identity()):
        return jsonify({"error": "cannot block the currently signed-in administrator"}), 400
    data = request.get_json(silent=True) or {}
    reason = str(data.get("reason", "manually blocked by admin")).strip()[:255] or "manually blocked by admin"

    user.is_blocked = True
    user.blocked_reason = reason
    user.blocked_at = datetime.utcnow()
    user.sessions_revoked_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"message": "user blocked", "user": user.to_dict()}), 200


@admin_bp.route("/users/<int:user_id>/unblock", methods=["POST"])
@role_required("admin")
def unblock_user(user_id):
    """The only way a blocked account (auto-blocked by the ML engine, or
    manually blocked above) becomes loggable-in again. Deliberately not
    automatic -- a human reviews the alert history for this user first."""
    user = User.query.get_or_404(user_id)
    user.is_blocked = False
    user.blocked_reason = None
    user.blocked_at = None
    # Sessions stay revoked -- the user must log in fresh, they don't get
    # their old (potentially compromised) token back.
    db.session.commit()
    return jsonify({"message": "user unblocked", "user": user.to_dict()}), 200


@admin_bp.route("/users/<int:user_id>", methods=["DELETE"])
@role_required("admin")
def delete_user(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == int(get_jwt_identity()):
        return jsonify({"error": "cannot delete the currently signed-in administrator"}), 400
    # Preserve clinical/audit history rather than allowing a user delete to
    # cascade into appointments, records, or logs. Deactivate instead.
    user.is_active = False
    user.sessions_revoked_at = datetime.utcnow()
    user.is_blocked = False
    user.blocked_reason = None
    db.session.commit()
    return jsonify({"message": "user deactivated", "user": user.to_dict()}), 200


@admin_bp.route("/logs", methods=["GET"])
@role_required("admin")
def list_logs():
    limit = int(request.args.get("limit", 50))
    logs = ActivityLog.query.order_by(ActivityLog.timestamp.desc()).limit(limit).all()
    return jsonify([l.to_dict() for l in logs]), 200


@admin_bp.route("/alerts", methods=["GET"])
@role_required("admin")
def list_alerts():
    """ML alerts panel: everything the anomaly engine flagged as
    suspicious or critical, most recent first."""
    logs = (
        ActivityLog.query.filter(ActivityLog.risk_level.in_(["suspicious", "critical"]))
        .order_by(ActivityLog.timestamp.desc())
        .limit(100)
        .all()
    )
    return jsonify([l.to_dict() for l in logs]), 200


@admin_bp.route("/revoked-sessions", methods=["GET"])
@role_required("admin")
def list_revoked():
    revoked = RevokedSession.query.order_by(RevokedSession.revoked_at.desc()).all()
    return jsonify([
        {"jti": r.jti, "user_id": r.user_id, "reason": r.reason,
         "revoked_at": r.revoked_at.isoformat()}
        for r in revoked
    ]), 200


@admin_bp.route("/simulate-attack/<int:user_id>", methods=["POST"])
@role_required("admin")
def simulate_attack(user_id):
    """Demo helper for your report/viva: floods synthetic ActivityLog rows
    for a user to mimic stolen-credential behaviour (rapid requests,
    off-hours, wide PHI access), then triggers the real scoring pipeline
    so you can show the auto-mitigation flow live without an actual attack."""
    from datetime import datetime, timedelta
    from app.ml_engine.features import extract_features_for_user
    from app.ml_engine.infer import score_features
    from app.logging.middleware import _mitigate
    from flask import current_app

    now = datetime.utcnow()
    target = User.query.get(user_id)
    # Deliberately extreme burst: rapid-fire requests hitting a wide spread
    # of distinct PHI records, timestamped at 3am -- a textbook signature
    # of a stolen-credential / automated scraping attack, not a real
    # clinician's workflow.
    off_hours_ts = now.replace(hour=3, minute=0, second=0, microsecond=0)
    for i in range(45):
        # a handful of 403s mixed in -- probing for records this account
        # isn't normally authorized to touch, alongside the successful hits
        status = 403 if i % 4 == 0 else 200
        db.session.add(ActivityLog(
            user_id=user_id,
            username=target.username if target else "unknown",
            role=target.role if target else "staff",
            endpoint="patients.get_patient",
            method="GET",
            ip_address="10.0.0.66",
            status_code=status,
            patient_id_accessed=100 + i,
            timestamp=off_hours_ts - timedelta(seconds=i * 2),
        ))
    db.session.commit()

    user = User.query.get_or_404(user_id)
    # Score at the same simulated timestamp as the injected burst so the
    # 5-min/15-min windows actually capture it (and off-hours is correctly
    # flagged) instead of comparing against the real current time.
    features = extract_features_for_user(db, ActivityLog, user_id, user.role, at_time=off_hours_ts)
    score, risk = score_features(
        features,
        current_app.config["ML_MODEL_PATH"],
        current_app.config["ML_SCALER_PATH"],
        current_app.config["RISK_SUSPICIOUS_THRESHOLD"],
        current_app.config["RISK_CRITICAL_THRESHOLD"],
    )

    # Simulations are strictly non-destructive. They demonstrate the
    # detector without blocking or revoking the selected real account.
    mitigated = False
    recommended_action = "admin_review" if risk in {"suspicious", "critical"} else "none"

    return jsonify({
        "user": user.to_dict(),
        "features": features,
        "anomaly_score": score,
        "risk_level": risk,
        "auto_mitigated": mitigated,
        "recommended_action": recommended_action,
    }), 200


@admin_bp.route("/dashboard/summary", methods=["GET"])
@role_required("admin", "doctor", "staff")
def dashboard_summary():
    """Single read-optimized payload for the React operations dashboard."""
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    role = get_jwt().get("role")
    identity = int(get_jwt_identity())
    activity_query = ActivityLog.query
    if role in {"doctor", "staff"}:
        activity_query = activity_query.filter_by(user_id=identity)
    recent = activity_query.order_by(ActivityLog.timestamp.desc()).limit(8).all()
    chart = []
    for minutes_ago in range(55, -1, -10):
        start = now - timedelta(minutes=minutes_ago + 10)
        end = now - timedelta(minutes=minutes_ago)
        bucket = ActivityLog.query.filter(ActivityLog.timestamp >= start, ActivityLog.timestamp < end)
        if role in {"doctor", "staff"}:
            bucket = bucket.filter(ActivityLog.user_id == identity)
        count = bucket.count()
        chart.append({"label": end.strftime("%H:%M"), "requests": count})
    upcoming_query = Appointment.query.filter(
        Appointment.scheduled_at >= now,
        Appointment.scheduled_at <= now + timedelta(days=7),
        Appointment.status == "scheduled"
    )
    if role == "doctor":
        upcoming_query = upcoming_query.filter_by(doctor_id=identity)
    upcoming = upcoming_query.count()

    if role == "doctor":
        patient_count = db.session.query(Patient.id).join(Appointment, Appointment.patient_id == Patient.id).filter(
            Appointment.doctor_id == identity
        ).distinct().count()
        record_count = MedicalRecord.query.filter_by(doctor_id=identity).count()
        open_alerts = ActivityLog.query.filter(
            ActivityLog.user_id == identity,
            ActivityLog.risk_level.in_(["suspicious", "critical"])
        ).count()
        blocked = 1 if User.query.get(identity).is_blocked else 0
    elif role == "staff":
        patient_count = Patient.query.count()
        record_count = 0
        open_alerts = 0
        blocked = 0
    else:
        patient_count = Patient.query.count()
        record_count = MedicalRecord.query.count()
        open_alerts = ActivityLog.query.filter(ActivityLog.risk_level.in_(["suspicious", "critical"])).count()
        blocked = User.query.filter_by(is_blocked=True).count()
    # Keep the score explainable: begin at 100 and apply small penalties for
    # unresolved alerts/blocked accounts. It is a posture indicator, not an ML score.
    score = max(0, min(100, 100 - min(open_alerts * 2, 16) - min(blocked * 3, 12)))
    return jsonify({
        "role": role,
        "patients": patient_count,
        "record_count": record_count,
        "upcoming_appointments": upcoming,
        "open_alerts": open_alerts,
        "blocked_accounts": blocked,
        "security_score": score,
        "activity_chart": chart,
        "recent_events": [x.to_dict() for x in recent],
    }), 200
