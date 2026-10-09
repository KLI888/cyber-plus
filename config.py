import os
import secrets
from datetime import timedelta

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "change-this-in-production")

    # Swap this connection string for MySQL/PostgreSQL in production, e.g.:
    #   mysql+pymysql://user:pass@localhost/cyberpulse
    #   postgresql+psycopg2://user:pass@localhost/cyberpulse
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'cyberpulse.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Zero Trust: short-lived access tokens force continuous re-verification
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY") or secrets.token_urlsafe(32)
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=15)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(hours=8)
    JWT_TOKEN_LOCATION = ["headers", "cookies"]
    JWT_COOKIE_CSRF_PROTECT = False  # simplified for demo; enable in production
    JWT_COOKIE_SECURE = False  # set True when served over HTTPS

    ML_MODEL_PATH = os.path.join(BASE_DIR, "models", "isolation_forest.pkl")
    ML_SCALER_PATH = os.path.join(BASE_DIR, "models", "scaler.pkl")

    # Anomaly score routing (Isolation Forest decision_function output,
    # roughly in [-0.5, 0.5]; lower = more anomalous)
    RISK_SUSPICIOUS_THRESHOLD = 0.0
    RISK_CRITICAL_THRESHOLD = -0.15
