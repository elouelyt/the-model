"""Model agent — applies the trained logistic regression model at inference time.

Loads coefficients from models/lr_model.json and predicts win probabilities
using plain Python math. No sklearn dependency required at runtime.

Falls back to the ranking-points ratio (the pre-Sprint-6 baseline) if the
model file is missing or corrupt, so the pipeline never breaks.

Features used (must match scripts/train_model.py):
    log_pts_ratio  — log(home_points / away_points)
    rank_diff      — away_rank - home_rank  (positive = home has better rank)
    clay           — 1.0 if surface == "clay"
    grass          — 1.0 if surface == "grass"
    indoor_hard    — 1.0 if surface == "indoor_hard"
"""

import json
import logging
import math
from pathlib import Path

logger = logging.getLogger(__name__)

_MODEL_PATH = Path(__file__).resolve().parents[2] / "models" / "lr_model.json"

# Module-level cache — loaded once per process
_MODEL: dict | None = None


def _sigmoid(x: float) -> float:
    """Numerically stable sigmoid."""
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    exp_x = math.exp(x)
    return exp_x / (1.0 + exp_x)


def _load_model() -> dict:
    global _MODEL
    if _MODEL is not None:
        return _MODEL
    if not _MODEL_PATH.exists():
        raise FileNotFoundError(f"Model file not found: {_MODEL_PATH}")
    _MODEL = json.loads(_MODEL_PATH.read_text(encoding="utf-8"))
    logger.info(
        "LR model loaded — CV accuracy %.3f ± %.3f (n=%d, years %d–%d).",
        _MODEL["cv_accuracy_mean"],
        _MODEL["cv_accuracy_std"],
        _MODEL["n_train"],
        _MODEL["train_years"][0],
        _MODEL["train_years"][-1],
    )
    return _MODEL


def predict_win_probability(
    home_points: int,
    away_points: int,
    home_rank: int,
    away_rank: int,
    surface: str,
) -> tuple[float, float]:
    """Predict win probabilities using the trained logistic regression model.

    Falls back to the ranking-points ratio if the model is unavailable.

    Args:
        home_points: ATP ranking points for the home player.
        away_points: ATP ranking points for the away player.
        home_rank:   ATP rank of the home player (lower number = better).
        away_rank:   ATP rank of the away player.
        surface:     Court surface string ("clay", "grass", "hard", "indoor_hard").

    Returns:
        (prob_home, prob_away) tuple — both positive, sum to 1.0.

    Raises:
        ValueError: If any points value is zero or negative.
    """
    if home_points <= 0 or away_points <= 0:
        raise ValueError(f"Points must be positive. Got: {home_points}, {away_points}")

    try:
        model = _load_model()
    except Exception as exc:
        logger.warning("LR model unavailable (%s) — falling back to points ratio.", exc)
        prob_home = home_points / (home_points + away_points)
        return round(prob_home, 4), round(1.0 - prob_home, 4)

    coef = model["coef"]
    intercept = model["intercept"]
    mean = model["scaler_mean"]
    std = model["scaler_std"]

    # Raw feature vector — must match training order in FEATURE_NAMES
    raw = [
        math.log(home_points / away_points),       # log_pts_ratio
        float(away_rank) - float(home_rank),        # rank_diff (positive = home ranked better)
        1.0 if surface == "clay"        else 0.0,  # clay
        1.0 if surface == "grass"       else 0.0,  # grass
        1.0 if surface == "indoor_hard" else 0.0,  # indoor_hard
    ]

    # StandardScaler transform: x_scaled = (x - mean) / std
    scaled = [(raw[i] - mean[i]) / std[i] for i in range(len(raw))]

    # Logistic regression: P(home wins) = sigmoid(coef · scaled + intercept)
    z = sum(coef[i] * scaled[i] for i in range(len(coef))) + intercept
    prob_home = _sigmoid(z)

    return round(prob_home, 4), round(1.0 - prob_home, 4)
