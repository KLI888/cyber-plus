from datetime import datetime, timedelta
from flask import request, g, current_app
from flask_jwt_extended import verify_jwt_in_request, get_jwt, get_jwt_identity

from app.models import db, ActivityLog, RevokedSession
from app.ml_engine.features import extract_features_for_user
from app.ml_engine.infer import score_features

# Endpoints excluded from logging/scoring (public, or would recurse)
EXEMPT_ENDPOINTS = {"auth.login", "auth.register", "static"}


def register_logging(app):

    @app.after_request
    def log_and_score(response):
        if (request.endpoint in EXEMPT_ENDPOINTS or request.endpoint is None
                or request.endpoint.startswith("public.")):
            return response

        user_id, username, role = None, None, None
        try:
            verify_jwt_in_request(optional=True)
            identity = get_jwt_identity()
            if identity is not None:
                claims = get_jwt()
                user_id = int(identity)
                username = claims.get("username")
                role = claims.get("role")
        except Exception:
            pass  # unauthenticated request; still log it with null identity

        patient_id = request.view_args.get("patient_id") if request.view_args else None

        log_entry = ActivityLog(
            user_id=user_id,
            username=username,
            role=role,
            endpoint=request.endpoint,
            method=request.method,
            ip_address=request.remote_addr,
            status_code=response.status_code,
            patient_id_accessed=patient_id,
            timestamp=datetime.utcnow(),
        )
        db.session.add(log_entry)
        db.session.commit()

        # Real-time ML scoring (Section VI-D/E) -- only for authenticated users
        if user_id is not None:
            try:
                recent_count = ActivityLog.query.filter(
                    ActivityLog.user_id == user_id,
                    ActivityLog.timestamp >= datetime.utcnow() - timedelta(minutes=15),
                ).count()
                # Cold-start guard: do not classify a normal first few requests.
                if recent_count < 5:
                    return response
                features = extract_features_for_user(db, ActivityLog, user_id, role)
                score, risk = score_features(
                    features,
                    current_app.config["ML_MODEL_PATH"],
                    current_app.config["ML_SCALER_PATH"],
                    current_app.config["RISK_SUSPICIOUS_THRESHOLD"],
                    current_app.config["RISK_CRITICAL_THRESHOLD"],
                )
                log_entry.anomaly_score = score
                log_entry.risk_level = risk
                db.session.commit()

                # Detection is non-destructive. Suspicious/critical events are
                # surfaced to administrators; only an explicit admin action
                # can block an account. This prevents false-positive lockouts.
            except FileNotFoundError:
                # model not trained yet -- don't block the app, just skip scoring
                pass

        return response


def _mitigate(user_id, reason):
    """Automated Threat Mitigation (Section VI-E), two-part:

    1. Revoke every live session for this user account-wide -- any token
       already issued to them, on any device, fails their very next
       request.
    2. Block the account outright (User.is_blocked) so they can't just
       log back in a second later with the same (still-valid, not
       actually stolen) password. The block persists until an admin
       explicitly clears it via POST /api/admin/users/<id>/unblock.
    """
    from app.models import User
    user = User.query.get(user_id)
    if user:
        user.sessions_revoked_at = datetime.utcnow()
        user.is_blocked = True
        user.blocked_reason = reason
        user.blocked_at = datetime.utcnow()
    try:
        current_jti = get_jwt().get("jti")
    except Exception:
        current_jti = None
    if current_jti and not RevokedSession.query.filter_by(jti=current_jti).first():
        db.session.add(RevokedSession(jti=current_jti, user_id=user_id, reason=reason))
    db.session.commit()
