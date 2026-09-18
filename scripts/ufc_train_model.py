"""Train a logistic regression model on historical UFC fight data.

Requires:
  - data/ufc_fights_history.json   (from ufc_scrape_events.py)
  - data/ufc_fighters_cache.json   (from ufc_scrape_fighters.py)

Output: data/ufc_model.json  (coefficients + scaler params, no sklearn at inference)

Features per fight (symmetric — each fight generates 2 rows):
  reach_diff, height_diff, age_diff,
  sig_str_acc_diff, sig_str_def_diff, td_acc_diff, td_def_diff,
  finish_rate_diff, recent_win_rate_diff
"""

import json
import logging
import math
from collections import defaultdict
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s — %(levelname)s — %(message)s")
logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parents[1] / "data"
_FIGHTS_FILE  = _ROOT / "ufc_fights_history.json"
_FIGHTERS_FILE = _ROOT / "ufc_fighters_cache.json"
_MODEL_OUT = _ROOT / "ufc_model.json"

FEATURE_NAMES = [
    "reach_diff", "height_diff", "age_diff",
    "sig_str_acc_diff", "sig_str_def_diff",
    "td_acc_diff", "td_def_diff",
    "finish_rate_diff",
]


def _finish(method: str) -> bool:
    m = method.upper()
    return any(x in m for x in ("KO", "TKO", "SUB", "SUBMISSION"))


def _build_finish_rate(fights: list[dict]) -> dict[str, float]:
    """Fighter → fraction of wins that were finishes."""
    wins = defaultdict(int)
    finish_wins = defaultdict(int)
    for f in fights:
        w = f["winner"]
        wins[w] += 1
        if _finish(f.get("method", "")):
            finish_wins[w] += 1
    return {
        name: finish_wins[name] / wins[name] if wins[name] else 0.5
        for name in wins
    }


def _build_recent_win_rate(fights: list[dict]) -> dict[str, float]:
    """Fighter → win rate in last 5 fights."""
    history: dict[str, list[int]] = defaultdict(list)
    for f in fights:
        history[f["winner"]].append(1)
        history[f["loser"]].append(0)
    result = {}
    for name, record in history.items():
        last5 = record[-5:]
        result[name] = sum(last5) / len(last5) if last5 else 0.5
    return result


def _features(f1: dict, f2: dict, finish_rate: dict, recent_wr: dict, name1: str, name2: str) -> list[float]:
    def diff(key: str) -> float:
        a = f1.get(key) or 0.0
        b = f2.get(key) or 0.0
        return a - b

    return [
        diff("reach_cm"),
        diff("height_cm"),
        diff("age") * -1,  # younger = advantage (negative age = younger)
        diff("sig_str_acc"),
        diff("sig_str_def"),
        diff("td_acc"),
        diff("td_def"),
        (finish_rate.get(name1, 0.5) - finish_rate.get(name2, 0.5)),
    ]


def _sigmoid(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-500, min(500, z))))


def _dot(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _standardize(X: list[list[float]]) -> tuple[list[list[float]], list[float], list[float]]:
    n, m = len(X), len(X[0])
    means = [sum(X[i][j] for i in range(n)) / n for j in range(m)]
    stds  = [
        math.sqrt(sum((X[i][j] - means[j]) ** 2 for i in range(n)) / max(n - 1, 1))
        for j in range(m)
    ]
    stds = [s if s > 1e-8 else 1.0 for s in stds]
    Xs = [[(X[i][j] - means[j]) / stds[j] for j in range(m)] for i in range(n)]
    return Xs, means, stds


def _train_lr(X: list[list[float]], y: list[int], lr: float = 0.1, epochs: int = 200) -> list[float]:
    n, m = len(X), len(X[0])
    w = [0.0] * m
    b = 0.0
    for _ in range(epochs):
        dw = [0.0] * m
        db = 0.0
        for i in range(n):
            z = _dot(w, X[i]) + b
            err = _sigmoid(z) - y[i]
            for j in range(m):
                dw[j] += err * X[i][j]
            db += err
        w = [w[j] - lr * dw[j] / n for j in range(m)]
        b -= lr * db / n
    return w, b


def main() -> None:
    if not _FIGHTS_FILE.exists():
        logger.error("Missing %s — run ufc_scrape_events.py first", _FIGHTS_FILE)
        return
    if not _FIGHTERS_FILE.exists():
        logger.error("Missing %s — run ufc_scrape_fighters.py first", _FIGHTERS_FILE)
        return

    fights_data = json.loads(_FIGHTS_FILE.read_text(encoding="utf-8"))
    fighters_data = json.loads(_FIGHTERS_FILE.read_text(encoding="utf-8"))
    fights = fights_data["fights"]
    fighters = fighters_data["fighters"]

    logger.info("Loaded %d fights, %d fighters", len(fights), len(fighters))

    finish_rate = _build_finish_rate(fights)
    recent_wr   = _build_recent_win_rate(fights)

    X_raw, y = [], []
    skipped = 0

    for fight in fights:
        w_name, l_name = fight["winner"], fight["loser"]
        wf = fighters.get(w_name)
        lf = fighters.get(l_name)
        if not wf or not lf:
            skipped += 1
            continue

        # Winner as fighter1 (label=1)
        feats_w = _features(wf, lf, finish_rate, recent_wr, w_name, l_name)
        X_raw.append(feats_w)
        y.append(1)

        # Mirror: loser as fighter1 (label=0)
        feats_l = _features(lf, wf, finish_rate, recent_wr, l_name, w_name)
        X_raw.append(feats_l)
        y.append(0)

    logger.info("Training on %d samples (%d fights skipped — no stats)", len(X_raw), skipped)

    Xs, means, stds = _standardize(X_raw)
    weights, bias = _train_lr(Xs, y, lr=0.05, epochs=300)

    # Cross-validate accuracy (last 20% as holdout)
    split = int(len(Xs) * 0.8)
    correct = sum(
        1 for i in range(split, len(Xs))
        if ((_sigmoid(_dot(weights, Xs[i]) + bias) >= 0.5) == bool(y[i]))
    )
    acc = correct / max(len(Xs) - split, 1)
    logger.info("Holdout accuracy: %.1f%%", acc * 100)

    model = {
        "feature_names": FEATURE_NAMES,
        "weights": weights,
        "bias": bias,
        "scaler_mean": means,
        "scaler_std": stds,
        "holdout_accuracy": round(acc, 4),
        "trained_on": len(X_raw),
    }
    _MODEL_OUT.write_text(json.dumps(model, indent=2), encoding="utf-8")
    logger.info("Model saved to %s (accuracy %.1f%%)", _MODEL_OUT, acc * 100)


if __name__ == "__main__":
    main()
