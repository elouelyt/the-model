"""MMA model agent — applies trained logistic regression to predict UFC fight outcomes.

Model trained by scripts/ufc_train_model.py on historical UFC fight data.
Features: reach_diff, height_diff, age_diff, sig_str_acc_diff, sig_str_def_diff,
          td_acc_diff, td_def_diff, finish_rate_diff
"""

import json
import logging
import math
from pathlib import Path

logger = logging.getLogger(__name__)

_MODEL_PATH = Path(__file__).resolve().parents[2] / "data" / "ufc_model.json"
_FINISH_RATE_PATH = Path(__file__).resolve().parents[2] / "data" / "ufc_finish_rates.json"

_model_cache: dict | None = None
_finish_rate_cache: dict | None = None


def _load_model() -> dict | None:
    global _model_cache
    if _model_cache is not None:
        return _model_cache
    if not _MODEL_PATH.exists():
        logger.warning("ufc_model.json not found — run scripts/ufc_train_model.py")
        return None
    try:
        _model_cache = json.loads(_MODEL_PATH.read_text(encoding="utf-8"))
        logger.info("UFC model loaded (accuracy %.1f%%)", _model_cache.get("holdout_accuracy", 0) * 100)
        return _model_cache
    except Exception as exc:
        logger.error("Failed to load UFC model: %s", exc)
        return None


def _sigmoid(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-500, min(500, z))))


def _standardize(features: list[float], means: list[float], stds: list[float]) -> list[float]:
    return [(f - m) / s for f, m, s in zip(features, means, stds)]


def predict_fight(
    f1_stats: dict,
    f2_stats: dict,
    f1_name: str = "",
    f2_name: str = "",
    finish_rates: dict | None = None,
) -> dict:
    """Predict P(fighter1 wins) given their stats.

    Args:
        f1_stats: Fighter 1 stats dict (from mma_stats_agent).
        f2_stats: Fighter 2 stats dict.
        f1_name, f2_name: Names for finish rate lookup.
        finish_rates: dict mapping fighter name → finish rate (0-1).

    Returns:
        {"prob_f1": float, "prob_f2": float, "model_used": bool}
    """
    model = _load_model()
    if not model:
        return {"prob_f1": 0.5, "prob_f2": 0.5, "model_used": False}

    fr = finish_rates or {}

    def get(stats: dict, key: str, default: float = 0.0) -> float:
        v = stats.get(key)
        return float(v) if v is not None else default

    features = [
        get(f1_stats, "reach_cm") - get(f2_stats, "reach_cm"),
        get(f1_stats, "height_cm") - get(f2_stats, "height_cm"),
        (get(f1_stats, "age") - get(f2_stats, "age")) * -1,  # younger = positive signal
        get(f1_stats, "sig_str_acc", 0.45) - get(f2_stats, "sig_str_acc", 0.45),
        get(f1_stats, "sig_str_def", 0.55) - get(f2_stats, "sig_str_def", 0.55),
        get(f1_stats, "td_acc", 0.35) - get(f2_stats, "td_acc", 0.35),
        get(f1_stats, "td_def", 0.60) - get(f2_stats, "td_def", 0.60),
        fr.get(f1_name, 0.5) - fr.get(f2_name, 0.5),
    ]

    means = model["scaler_mean"]
    stds  = model["scaler_std"]
    weights = model["weights"]
    bias = model["bias"]

    X = _standardize(features, means, stds)
    z = sum(w * x for w, x in zip(weights, X)) + bias
    prob_f1 = round(_sigmoid(z), 4)

    return {
        "prob_f1": prob_f1,
        "prob_f2": round(1 - prob_f1, 4),
        "model_used": True,
        "features": dict(zip(model["feature_names"], [round(f, 3) for f in features])),
    }


def compute_edge(prob: float, odds: float) -> float:
    """Kelly-style edge: model_prob - implied_prob."""
    implied = 1 / odds if odds > 1 else 1.0
    return round(prob - implied, 4)
