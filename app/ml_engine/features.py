"""
Feature extraction for the anomaly detection engine.

In the survey paper, the Isolation Forest is trained on CIC-IDS2017
network-flow features. For an *application-layer* HIS, we translate that
same idea into behavioural features computed from the ActivityLog table:
each row = one request; features describe the *pattern* of a user's
recent behaviour rather than a single request in isolation.

FEATURE VECTOR (5 dims):
  0. requests_last_5min       - burst detection (credential stuffing / scripted abuse)
  1. failed_ratio_last_15min  - repeated auth/permission failures
  2. distinct_patients_5min   - abnormal breadth of PHI access ("data mining")
  3. is_off_hours             - 1 if outside 07:00-21:00 (typical clinical hours)
  4. role_risk_weight         - staff=0.3, doctor=0.6, admin=1.0 (higher-privilege
                                 accounts are scored more strictly -- a compromised
                                 admin account is a bigger blast radius)
"""
from datetime import datetime, timedelta

ROLE_RISK_WEIGHT = {"staff": 0.3, "doctor": 0.6, "admin": 1.0}


def is_off_hours(ts: datetime) -> int:
    return 0 if 7 <= ts.hour < 21 else 1


def extract_features_for_user(db, ActivityLog, user_id: int, role: str, at_time: datetime = None):
    at_time = at_time or datetime.utcnow()
    window_5min = at_time - timedelta(minutes=5)
    window_15min = at_time - timedelta(minutes=15)

    requests_5min = ActivityLog.query.filter(
        ActivityLog.user_id == user_id,
        ActivityLog.timestamp >= window_5min,
    ).count()

    total_15min = ActivityLog.query.filter(
        ActivityLog.user_id == user_id,
        ActivityLog.timestamp >= window_15min,
    ).count()
    failed_15min = ActivityLog.query.filter(
        ActivityLog.user_id == user_id,
        ActivityLog.timestamp >= window_15min,
        ActivityLog.status_code >= 400,
    ).count()
    failed_ratio = (failed_15min / total_15min) if total_15min else 0.0

    distinct_patients = (
        db.session.query(ActivityLog.patient_id_accessed)
        .filter(
            ActivityLog.user_id == user_id,
            ActivityLog.timestamp >= window_5min,
            ActivityLog.patient_id_accessed.isnot(None),
        )
        .distinct()
        .count()
    )

    return [
        float(requests_5min),
        float(failed_ratio),
        float(distinct_patients),
        float(is_off_hours(at_time)),
        ROLE_RISK_WEIGHT.get(role, 0.5),
    ]


FEATURE_NAMES = [
    "requests_last_5min",
    "failed_ratio_last_15min",
    "distinct_patients_5min",
    "is_off_hours",
    "role_risk_weight",
]
