"""
Wrapper around the trained PFZ (Potential Fishing Zone) XGBoost model.

Model expects features in this exact order (confirmed from the uploaded
pfz_xgboost_model.json): latitude, longitude, sst, chlorophyll, wind_speed
Objective: binary:logistic -> predict() already returns a probability in [0, 1].
"""
from pathlib import Path
import xgboost as xgb
import numpy as np

MODEL_PATH = Path(__file__).parent.parent / "model_files" / "pfz_xgboost_model.json"

_booster: xgb.Booster | None = None


def get_booster() -> xgb.Booster:
    """Lazily load and cache the model so it's only read from disk once per process."""
    global _booster
    if _booster is None:
        if not MODEL_PATH.exists():
            raise FileNotFoundError(
                f"Model file not found at {MODEL_PATH}. "
                "Copy pfz_xgboost_model.json into orca/model_files/ before starting the server."
            )
        _booster = xgb.Booster()
        _booster.load_model(str(MODEL_PATH))
    return _booster


def predict_pfz_score(latitude: float, longitude: float, sst: float, chlorophyll: float, wind_speed: float) -> float:
    """
    Returns the model's predicted probability (0-1) that this location/condition
    combination is a Potential Fishing Zone.
    """
    booster = get_booster()
    features = np.array([[latitude, longitude, sst, chlorophyll, wind_speed]], dtype=np.float32)
    dmat = xgb.DMatrix(features, feature_names=booster.feature_names)
    score = booster.predict(dmat)[0]
    return float(score)
