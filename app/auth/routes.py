from flask import Blueprint, request, jsonify
from datetime import datetime, timedelta
from threading import Lock
from flask_jwt_extended import (
    create_access_token, create_refresh_token, jwt_required,
    get_jwt, get_jwt_identity
)
from app.models import db, User, RevokedSession

auth_bp = Blueprint("auth", __name__)

ALLOWED_ROLES = {"admin", "doctor", "staff"}
_LOGIN_GUARD = {}
_LOGIN_LOCK = Lock()

def _login_rate_limited(ip):
    now = datetime.utcnow()
    with _LOGIN_LOCK:
        bucket = _LOGIN_GUARD.setdefault(ip, [])
        bucket[:] = [t for t in bucket if t > now - timedelta(minutes=5)]
        if len(bucket) >= 12:
            return True
        bucket.append(now)
        return False


@auth_bp.route("/register", methods=["POST"])
def register():
    """Public self-registration is disabled; admins provision accounts."""
    return jsonify({"error":"registration_disabled","message":"User accounts can only be created by an administrator."}), 403


@auth_bp.route("/login", methods=["POST"])
def login():
    if _login_rate_limited(request.remote_addr or "unknown"):
        return jsonify({"error": "rate_limited", "message": "Too many sign-in attempts. Please try again later."}), 429
    data = request.get_json(silent=True) or {}
    username = str(data.get("username", "")).strip()[:80]
    password = str(data.get("password", ""))

    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(password) or not user.is_active:
        # Deliberately vague -- don't leak which part failed
        return jsonify({"error": "invalid credentials"}), 401

    if user.is_blocked:
        # This is the account-level kill switch: even correct credentials
        # cannot get a new token while blocked. Only an admin unblock
        # (POST /api/admin/users/<id>/unblock) clears this.
        return jsonify({
            "error": "account_blocked",
            "message": "This account is blocked and requires administrator approval to regain access.",
            "reason": user.blocked_reason,
        }), 403

    extra_claims = {"role": user.role, "username": user.username}
    access_token = create_access_token(identity=str(user.id), additional_claims=extra_claims)
    refresh_token = create_refresh_token(identity=str(user.id), additional_claims=extra_claims)

    return jsonify({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": user.to_dict(),
    }), 200


@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def me():
    user = User.query.get(int(get_jwt_identity()))
    if not user or not user.is_active or user.is_blocked:
        return jsonify({"error": "account no longer active"}), 401
    return jsonify({"user": user.to_dict()}), 200


@auth_bp.route("/refresh", methods=["POST"])
@jwt_required(refresh=True)
def refresh():
    """Zero Trust re-verification: short-lived access tokens (15 min) force
    the client back through here regularly rather than trusting one login
    for an entire session."""
    identity = get_jwt_identity()
    claims = get_jwt()
    user = User.query.get(int(identity))
    if not user or not user.is_active or user.is_blocked:
        return jsonify({"error": "account no longer active"}), 401

    new_access_token = create_access_token(
        identity=identity,
        additional_claims={"role": user.role, "username": user.username},
    )
    return jsonify({"access_token": new_access_token}), 200


@auth_bp.route("/logout", methods=["POST"])
@jwt_required()
def logout():
    jti = get_jwt()["jti"]
    identity = get_jwt_identity()
    db.session.add(RevokedSession(jti=jti, user_id=int(identity), reason="user_logout"))
    db.session.commit()
    return jsonify({"message": "logged out"}), 200
