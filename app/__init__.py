from datetime import datetime, timezone
from flask import Flask, send_from_directory, jsonify, request
from flask_jwt_extended import JWTManager

from config import Config
from app.models import db, RevokedSession, User


def create_app(config_class=Config):
    app = Flask(__name__, static_folder="static", static_url_path="/static")
    app.config.from_object(config_class)

    db.init_app(app)
    jwt = JWTManager(app)

    app.config.setdefault("MAX_CONTENT_LENGTH", 2 * 1024 * 1024)

    @app.errorhandler(413)
    def request_too_large(_error):
        return jsonify({"error": "payload_too_large", "message": "Request payload exceeds the 2 MB limit."}), 413

    @app.errorhandler(400)
    def bad_request(_error):
        if request.path.startswith("/api/"):
            return jsonify({"error": "bad_request", "message": "The request could not be processed."}), 400
        return jsonify({"error": "bad_request", "message": "The request could not be processed."}), 400

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        response.headers.setdefault("Content-Security-Policy", "default-src 'self'; img-src 'self' data: https://images.unsplash.com; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; script-src 'self'; connect-src 'self'")
        return response

    # Two independent ways a token can be rejected before it naturally
    # expires:
    #   1. Its exact JTI was blacklisted (used by /auth/logout, single
    #      session).
    #   2. It was issued (iat) before the user's account-wide
    #      sessions_revoked_at timestamp -- this is what the ML engine
    #      uses when an administrator explicitly revokes account sessions.
    @jwt.token_in_blocklist_loader
    def check_if_revoked(jwt_header, jwt_payload):
        jti = jwt_payload["jti"]
        if RevokedSession.query.filter_by(jti=jti).first() is not None:
            return True

        user_id = jwt_payload.get("sub")
        issued_at = jwt_payload.get("iat")
        if user_id is None or issued_at is None:
            return False

        user = User.query.get(int(user_id))
        if user and user.sessions_revoked_at:
            token_issued = datetime.fromtimestamp(issued_at, tz=timezone.utc).replace(tzinfo=None)
            return token_issued < user.sessions_revoked_at
        return False

    @jwt.revoked_token_loader
    def revoked_token_response(jwt_header, jwt_payload):
        return {"error": "session_revoked",
                "message": "This session was terminated. Please sign in again."}, 401

    from app.auth.routes import auth_bp
    from app.patients.routes import patients_bp
    from app.admin.routes import admin_bp
    from app.hospital.routes import hospital_bp, public_bp

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(patients_bp, url_prefix="/api/patients")
    app.register_blueprint(admin_bp, url_prefix="/api/admin")
    app.register_blueprint(hospital_bp, url_prefix="/api")
    app.register_blueprint(public_bp, url_prefix="/api/public")

    from app.logging.middleware import register_logging
    register_logging(app)

    # React SPA entrypoint. Flask remains the API/security boundary; the
    # compiled React application owns every non-API browser route.
    @app.route("/")
    @app.route("/<path:path>")
    def react_app(path=""):
        if path.startswith("api/"):
            return {"error": "not_found"}, 404
        dist = app.static_folder + "/dist"
        return send_from_directory(dist, "index.html")

    with app.app_context():
        db.create_all()

    return app
