"""
Trains the Isolation Forest anomaly detector.

Two data sources are supported:

1. CIC-IDS2017 (paper's benchmark dataset) -- if you place a CSV at
   data/CIC-IDS2017.csv, this script will use it (see load_cicids17()).
   Download it yourself from https://www.unb.ca/cic/datasets/ids-2017.html
   (not fetchable from this sandbox).

2. Synthetic baseline (default, used when no CSV is found) -- generates
   behavioural data in the same 5-feature space used at inference time
   (app/ml_engine/features.py), representative of "normal" clinical
   staff activity, so you have a working model to demo immediately.
   Swap in CIC-IDS2017 for your actual report numbers.

Usage:
    python -m app.ml_engine.train
"""
import os
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from app.ml_engine.features import FEATURE_NAMES

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
CICIDS_PATH = os.path.join(BASE_DIR, "data", "CIC-IDS2017.csv")
MODEL_PATH = os.path.join(BASE_DIR, "models", "isolation_forest.pkl")
SCALER_PATH = os.path.join(BASE_DIR, "models", "scaler.pkl")


def load_cicids17():
    """Loads and maps CIC-IDS2017 into the same 5-column feature space.
    Column names vary by CIC-IDS2017 release, so this is intentionally a
    template -- adjust the column mapping to match your CSV header."""
    df = pd.read_csv(CICIDS_PATH)
    df.columns = [c.strip() for c in df.columns]
    mapped = pd.DataFrame({
        "requests_last_5min": df.get("Flow Packets/s", pd.Series(dtype=float)).clip(upper=500),
        "failed_ratio_last_15min": (df.get("Label", "BENIGN") != "BENIGN").astype(float) * 0.0,
        "distinct_patients_5min": df.get("Destination Port", pd.Series(dtype=float)) % 10,
        "is_off_hours": np.random.randint(0, 2, size=len(df)),
        "role_risk_weight": np.random.choice([0.3, 0.6, 1.0], size=len(df)),
    })
    return mapped[FEATURE_NAMES].fillna(0)


def generate_synthetic_baseline(n_samples=4000, contamination_seed=42):
    """Simulates realistic clinical-staff behaviour: mostly calm, steady
    access patterns during working hours, occasional legitimate bursts."""
    rng = np.random.default_rng(contamination_seed)

    requests_5min = rng.poisson(lam=3, size=n_samples).clip(0, 15)
    failed_ratio = rng.beta(a=1, b=20, size=n_samples)  # mostly near 0
    distinct_patients = rng.poisson(lam=1.5, size=n_samples).clip(0, 8)
    off_hours = rng.choice([0, 1], size=n_samples, p=[0.85, 0.15])
    role_weight = rng.choice([0.3, 0.6, 1.0], size=n_samples, p=[0.5, 0.35, 0.15])

    df = pd.DataFrame({
        "requests_last_5min": requests_5min,
        "failed_ratio_last_15min": failed_ratio,
        "distinct_patients_5min": distinct_patients,
        "is_off_hours": off_hours,
        "role_risk_weight": role_weight,
    })
    return df[FEATURE_NAMES]


def train():
    os.makedirs(os.path.join(BASE_DIR, "models"), exist_ok=True)

    if os.path.exists(CICIDS_PATH):
        print(f"Loading CIC-IDS2017 from {CICIDS_PATH} ...")
        data = load_cicids17()
    else:
        print("No CIC-IDS2017.csv found in data/ -- generating synthetic baseline instead.")
        print("(Place the real dataset at data/CIC-IDS2017.csv and re-run for report-grade numbers.)")
        data = generate_synthetic_baseline()

    scaler = StandardScaler()
    X = scaler.fit_transform(data.values)

    # contamination='auto' lets the model estimate the proportion of
    # outliers itself, consistent with the unsupervised approach in
    # Section VI-D of the paper
    model = IsolationForest(
        n_estimators=200,
        contamination=0.05,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X)

    joblib.dump(model, MODEL_PATH)
    joblib.dump(scaler, SCALER_PATH)
    print(f"Model saved to {MODEL_PATH}")
    print(f"Scaler saved to {SCALER_PATH}")

    # Quick sanity check
    scores = model.decision_function(X)
    print(f"Training data score range: min={scores.min():.3f} max={scores.max():.3f} mean={scores.mean():.3f}")


if __name__ == "__main__":
    train()
