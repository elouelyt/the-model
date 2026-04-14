#!/usr/bin/env python3
"""Train logistic regression on Sackmann ATP match data and serialize to JSON.

Downloads historical ATP match data from JeffSackmann/tennis_atp, builds a
symmetric feature matrix, trains LogisticRegression, and writes coefficients
to models/lr_model.json.

The JSON format avoids a sklearn dependency at inference time — the model
agent applies the coefficients directly with plain Python math.

Run once locally after any data or feature change, then commit lr_model.json.

Requires: scikit-learn, pandas, requests (not in requirements-generate.txt).
Usage:
    pip install scikit-learn
    python scripts/train_model.py
"""

import io
import json
import logging
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import cross_val_score
from sklearn.preprocessing import StandardScaler

logging.basicConfig(level=logging.INFO, format="%(asctime)s — %(levelname)s — %(message)s")
logger = logging.getLogger(__name__)

_SACKMANN_BASE = (
    "https://raw.githubusercontent.com/JeffSackmann/tennis_atp/master/atp_matches_{year}.csv"
)
_TRAIN_YEARS = list(range(2018, 2025))
_COLS = [
    "winner_rank", "loser_rank",
    "winner_rank_points", "loser_rank_points",
    "surface", "score",
]
_SURFACE_NORM = {"Clay": "clay", "Grass": "grass", "Hard": "hard", "Carpet": "indoor_hard"}
_INCOMPLETE = ["RET", "W/O", "DEF", "ABD"]
_OUTPUT = Path(__file__).parent.parent / "models" / "lr_model.json"

FEATURE_NAMES = ["log_pts_ratio", "rank_diff", "clay", "grass", "indoor_hard"]


def load_data() -> pd.DataFrame:
    """Download and combine Sackmann match data for training years."""
    frames: list[pd.DataFrame] = []
    for year in _TRAIN_YEARS:
        url = _SACKMANN_BASE.format(year=year)
        try:
            resp = requests.get(url, timeout=20)
            resp.raise_for_status()
            df = pd.read_csv(io.StringIO(resp.text), usecols=_COLS, dtype=str)
            frames.append(df)
            logger.info("Loaded %d rows from %d.", len(df), year)
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                logger.info("No data for %d (404).", year)
            else:
                logger.warning("HTTP error for %d: %s", year, exc)
        except Exception as exc:
            logger.warning("Failed to load %d: %s", year, exc)

    if not frames:
        logger.error("No training data loaded. Aborting.")
        sys.exit(1)

    combined = pd.concat(frames, ignore_index=True)

    # Remove incomplete matches
    pattern = "|".join(_INCOMPLETE)
    combined = combined[~combined["score"].str.contains(pattern, na=False, case=False)]

    combined["surface"] = combined["surface"].map(_SURFACE_NORM).fillna("hard")

    for col in ["winner_rank", "loser_rank", "winner_rank_points", "loser_rank_points"]:
        combined[col] = pd.to_numeric(combined[col], errors="coerce")

    # Drop rows missing ranking data (common for lower-ranked players)
    before = len(combined)
    combined = combined.dropna(
        subset=["winner_rank", "loser_rank", "winner_rank_points", "loser_rank_points"]
    )
    combined = combined[
        (combined["winner_rank_points"] > 0) & (combined["loser_rank_points"] > 0)
    ]
    logger.info(
        "After dropping missing ranking data: %d / %d matches retained.",
        len(combined), before,
    )
    return combined.reset_index(drop=True)


def build_features(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Build a symmetric feature matrix from match data.

    For each match we generate two training examples — one with the winner as
    the 'home' player (label=1) and one with the loser as 'home' (label=0).
    This makes the model invariant to which player is listed first.

    Features:
        log_pts_ratio  — log(home_points / away_points)
        rank_diff      — away_rank - home_rank  (positive = home has better rank)
        clay           — 1 if clay surface
        grass          — 1 if grass surface
        indoor_hard    — 1 if indoor hard (carpet)
    """
    rows: list[list[float]] = []
    labels: list[int] = []

    for _, row in df.iterrows():
        w_pts = float(row["winner_rank_points"])
        l_pts = float(row["loser_rank_points"])
        w_rank = float(row["winner_rank"])
        l_rank = float(row["loser_rank"])
        surface = row["surface"]

        clay   = 1.0 if surface == "clay"        else 0.0
        grass  = 1.0 if surface == "grass"       else 0.0
        indoor = 1.0 if surface == "indoor_hard" else 0.0

        # Winner as home → label 1
        rows.append([math.log(w_pts / l_pts), l_rank - w_rank, clay, grass, indoor])
        labels.append(1)

        # Loser as home → label 0  (mirror)
        rows.append([math.log(l_pts / w_pts), w_rank - l_rank, clay, grass, indoor])
        labels.append(0)

    return np.array(rows, dtype=np.float64), np.array(labels, dtype=np.int8)


def main() -> None:
    logger.info("Loading training data (%d–%d)...", _TRAIN_YEARS[0], _TRAIN_YEARS[-1])
    df = load_data()
    X, y = build_features(df)
    logger.info("Feature matrix: %s rows × %s features, %d labels.", *X.shape, len(y))

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    model = LogisticRegression(C=1.0, max_iter=1000, random_state=42, solver="lbfgs")

    # 5-fold cross-validation for honest accuracy estimate
    cv_scores = cross_val_score(model, X_scaled, y, cv=5, scoring="accuracy")
    logger.info("5-fold CV accuracy: %.3f ± %.3f", cv_scores.mean(), cv_scores.std())

    # Final fit on full training set
    model.fit(X_scaled, y)
    coef = model.coef_[0].tolist()
    logger.info(
        "Coefficients: %s",
        dict(zip(FEATURE_NAMES, [round(c, 4) for c in coef])),
    )

    output = {
        "feature_names":     FEATURE_NAMES,
        "coef":              coef,
        "intercept":         float(model.intercept_[0]),
        "scaler_mean":       scaler.mean_.tolist(),
        "scaler_std":        scaler.scale_.tolist(),
        "cv_accuracy_mean":  float(cv_scores.mean()),
        "cv_accuracy_std":   float(cv_scores.std()),
        "n_train":           int(len(y)),
        "train_years":       _TRAIN_YEARS,
    }

    _OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    _OUTPUT.write_text(json.dumps(output, indent=2))
    logger.info("Model written to %s", _OUTPUT)


if __name__ == "__main__":
    main()
