import os
import joblib
import numpy as np

_model = None
_scaler = None


def _load(model_path, scaler_path):
    global _model, _scaler
    if _model is None or _scaler is None:
        if not (os.path.exists(model_path) and os.path.exists(scaler_path)):
            raise FileNotFoundError(
                "Model not found. Run `python -m app.ml_engine.train` first."
            )
        _model = joblib.load(model_path)
        _scaler = joblib.load(scaler_path)
    return _model, _scaler


def score_features(feature_vector, model_path, scaler_path,
                    suspicious_threshold=0.0, critical_threshold=-0.15):
    """Returns (anomaly_score, risk_level).

    IsolationForest.decision_function: lower score = more anomalous.
    We bucket it into three actionable tiers:
      normal      -> score >= suspicious_threshold
      suspicious  -> critical_threshold <= score < suspicious_threshold
      critical    -> score < critical_threshold  (triggers auto-mitigation)
    """
    model, scaler = _load(model_path, scaler_path)
    X = scaler.transform(np.array([feature_vector]))
    score = float(model.decision_function(X)[0])

    if score < critical_threshold:
        risk = "critical"
    elif score < suspicious_threshold:
        risk = "suspicious"
    else:
        risk = "normal"

    return score, risk
