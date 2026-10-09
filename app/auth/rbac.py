from functools import wraps
from flask import jsonify
from flask_jwt_extended import get_jwt, get_jwt_identity, verify_jwt_in_request
from app.models import User


def role_required(*allowed_roles):
    """Granular RBAC (Section VI-A). Every protected route declares exactly
    which roles may call it -- least privilege, enforced per-request, not
    just once at login."""

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            claims = get_jwt()
            role = claims.get("role")
            identity = get_jwt_identity()
            user = User.query.get(int(identity)) if identity is not None else None
            # Never trust role claims forever: admins can change a user's role
            # after a token was issued. The database is the current source of truth.
            if not user or not user.is_active or user.is_blocked:
                return jsonify({"error": "unauthorized", "message": "Account is no longer active."}), 401
            current_role = user.role
            if current_role != role or current_role not in allowed_roles:
                return jsonify({
                    "error": "forbidden",
                    "message": f"Role '{current_role}' is not permitted to access this resource."
                }), 403
            return fn(*args, **kwargs)
        return wrapper
    return decorator
