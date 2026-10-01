"""Train a logistic regression model on historical UFC fight data.

Requires:
  - data/ufc_fights_history.json   (from ufc_scrape_events.py)
  - data/ufc_fighters_cache.json   (from ufc_scrape_fighters.py)

Output: data/ufc_model.json  (coefficients + scaler params, no sklearn at inference)

Features per fight (symmetric — each fight generates 2 rows):
  reach_diff, height_diff, age_diff,
  sig_str_acc_diff, sig_str_def_diff, td_acc_diff, td_def_diff,
  finish_rate_diff, recent_win_rate_diff, elo_diff

elo_diff is computed point-in-time (see src/agents/mma_elo_agent.py): fights
are replayed in chronological order and each fight's elo_diff is captured
BEFORE that fight's result updates the ratings, same discipline as
scripts/ufc_walkforward_backtest.py. Every other feature above is a
today's-snapshot stat applied uniformly to all historical fights (a known,
documented limitation - see CLAUDE.md "lookahead bias" notes) - elo_diff is
the one feature in this model that doesn't share that flaw.
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
    "finish_rate_diff", "recent_win_rate_diff", "elo_diff",
]

ELO_INITIAL = 1500.0
ELO_BASE_K = 32.0
ELO_ADAPTIVE_K_SCHEDULE = [(5, 64.0), (10, 48.0)]

L2_LAMBDA = 0.5  # ridge penalty — shrinks weights toward 0, guards against a single
                 # sparse/noisy feature (e.g. finish_rate) dominating the model


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


def _pointintime_elo_diffs(fights_sorted: list[dict]) -> list[float]:
    """elo(winner) - elo(loser) captured BEFORE each fight updates the ratings.

    fights_sorted must already be in chronological order. Mirrors
    src/agents/mma_elo_agent.py's update rule exactly, so this is the same
    point-in-time discipline as scripts/ufc_walkforward_backtest.py - no
    fight's feature depends on any fight that happens later in time.
    """
    def k_for(count: int) -> float:
        for threshold, k in ELO_ADAPTIVE_K_SCHEDULE:
            if count < threshold:
                return k
        return ELO_BASE_K

    def expected(r_a: float, r_b: float) -> float:
        return 1.0 / (1.0 + 10 ** ((r_b - r_a) / 400.0))

    ratings: dict[str, float] = {}
    counts: dict[str, int] = {}
    diffs: list[float] = []
    for fight in fights_sorted:
        w, l = fight["winner"], fight["loser"]
        r_w, r_l = ratings.get(w, ELO_INITIAL), ratings.get(l, ELO_INITIAL)
        diffs.append(r_w - r_l)

        exp_w = expected(r_w, r_l)
        k_w, k_l = k_for(counts.get(w, 0)), k_for(counts.get(l, 0))
        ratings[w] = r_w + k_w * (1.0 - exp_w)
        ratings[l] = r_l + k_l * (0.0 - (1.0 - exp_w))
        counts[w] = counts.get(w, 0) + 1
        counts[l] = counts.get(l, 0) + 1
    return diffs


def _features(
    f1: dict, f2: dict, recent_wr: dict, name1: str, name2: str,
    elo_diff: float = 0.0,
) -> list[float]:
    def diff(key: str) -> float:
        a = f1.get(key) or 0.0
        b = f2.get(key) or 0.0
        return a - b

    def diff_default(key: str, default: float) -> float:
        a = f1.get(key)
        b = f2.get(key)
        return (a if a is not None else default) - (b if b is not None else default)

    return [
        diff("reach_cm"),
        diff("height_cm"),
        diff("age") * -1,  # younger = advantage (negative age = younger)
        diff("sig_str_acc"),
        diff("sig_str_def"),
        diff("td_acc"),
        diff("td_def"),
        # f1/f2 ARE the fighters-cache dicts, which already carry a real,
        # ESPN-sourced finish_rate (tkos+subs/wins) - read it directly instead
        # of rebuilding it from fight_history.json's method field. That field
        # is "UNK" for all 4110 rows (the scraper never captured it), which
        # made the old _build_finish_rate() helper detect 0 finishes out of
        # 4110 fights and train this weight against near-constant noise while
        # inference applied it to real numbers - a train/inference mismatch
        # that was very likely the actual reason this feature kept dominating
        # predictions in a counterintuitive direction.
        diff_default("finish_rate", 0.5),
        (recent_wr.get(name1, 0.5) - recent_wr.get(name2, 0.5)),
        elo_diff,
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


def _train_lr(
    X: list[list[float]], y: list[int], lr: float = 0.1, epochs: int = 200,
    l2: float = 0.0,
) -> tuple[list[float], float]:
    """L2-regularized (ridge) logistic regression via batch gradient descent.

    The ridge penalty shrinks weights toward 0 - without it a single sparse or
    noisy feature (e.g. finish_rate, which only has ~1900/4110 fighters with
    real underlying data) can end up with a disproportionately large weight
    that dominates every prediction.
    """
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
        # Bias term is never regularized.
        w = [w[j] - lr * (dw[j] / n + l2 * w[j]) for j in range(m)]
        b -= lr * db / n
    return w, b


def _kfold_accuracy(X: list[list[float]], y: list[int], k: int = 5, l2: float = 0.0) -> tuple[float, float]:
    """k-fold cross-validated accuracy (mean, std) - more robust than a single 80/20 split.

    X/y alternate (winner-row, loser-row) per fight - fold boundaries are kept aligned to
    fight pairs (even indices) so a single match's two mirrored rows never split across
    train/test (that would leak the same match's outcome into the fold that's supposed to
    be unseen).
    """
    n_fights = len(X) // 2
    fold_size = n_fights // k
    accs = []
    for fold in range(k):
        f_start = fold * fold_size
        f_end = (fold + 1) * fold_size if fold < k - 1 else n_fights
        start, end = f_start * 2, f_end * 2
        X_test, y_test = X[start:end], y[start:end]
        X_train = X[:start] + X[end:]
        y_train = y[:start] + y[end:]
        if not X_train or not X_test:
            continue
        w, b = _train_lr(X_train, y_train, lr=0.05, epochs=300, l2=l2)
        correct = sum(
            1 for i in range(len(X_test))
            if ((_sigmoid(_dot(w, X_test[i]) + b) >= 0.5) == bool(y_test[i]))
        )
        accs.append(correct / len(X_test))
    mean_acc = sum(accs) / len(accs)
    std_acc = math.sqrt(sum((a - mean_acc) ** 2 for a in accs) / len(accs))
    return mean_acc, std_acc


def main() -> None:
    if not _FIGHTS_FILE.exists():
        logger.error("Missing %s — run ufc_scrape_events.py first", _FIGHTS_FILE)
        return
    if not _FIGHTERS_FILE.exists():
        logger.error("Missing %s — run ufc_scrape_fighters.py first", _FIGHTERS_FILE)
        return

    fights_data = json.loads(_FIGHTS_FILE.read_text(encoding="utf-8"))
    fighters_data = json.loads(_FIGHTERS_FILE.read_text(encoding="utf-8"))
    fighters = fighters_data["fighters"]

    # Chronological order is required for elo_diff to be point-in-time honest
    # (see _pointintime_elo_diffs). This also makes the k-fold CV below fold
    # over contiguous TIME windows rather than arbitrary file order, which is
    # closer in spirit to a walk-forward split.
    fights = sorted(
        (f for f in fights_data["fights"] if f.get("winner") and f.get("loser") and f.get("date")),
        key=lambda f: f["date"],
    )
    elo_diffs = _pointintime_elo_diffs(fights)

    logger.info("Loaded %d fights, %d fighters", len(fights), len(fighters))

    recent_wr = _build_recent_win_rate(fights)

    X_raw, y = [], []
    skipped = 0

    for fight, elo_diff in zip(fights, elo_diffs):
        w_name, l_name = fight["winner"], fight["loser"]
        wf = fighters.get(w_name)
        lf = fighters.get(l_name)
        if not wf or not lf:
            skipped += 1
            continue

        # Winner as fighter1 (label=1)
        feats_w = _features(wf, lf, recent_wr, w_name, l_name, elo_diff=elo_diff)
        X_raw.append(feats_w)
        y.append(1)

        # Mirror: loser as fighter1 (label=0)
        feats_l = _features(lf, wf, recent_wr, l_name, w_name, elo_diff=-elo_diff)
        X_raw.append(feats_l)
        y.append(0)

    logger.info("Training on %d samples (%d fights skipped — no stats)", len(X_raw), skipped)

    Xs, means, stds = _standardize(X_raw)

    cv_mean, cv_std = _kfold_accuracy(Xs, y, k=5, l2=L2_LAMBDA)
    logger.info("5-fold CV accuracy: %.1f%% +/- %.1f%%", cv_mean * 100, cv_std * 100)

    weights, bias = _train_lr(Xs, y, lr=0.05, epochs=300, l2=L2_LAMBDA)

    model = {
        "feature_names": FEATURE_NAMES,
        "weights": weights,
        "bias": bias,
        "scaler_mean": means,
        "scaler_std": stds,
        "holdout_accuracy": round(cv_mean, 4),
        "cv_accuracy_std": round(cv_std, 4),
        "l2_lambda": L2_LAMBDA,
        "trained_on": len(X_raw),
    }
    _MODEL_OUT.write_text(json.dumps(model, indent=2), encoding="utf-8")
    logger.info("Model saved to %s (5-fold CV accuracy %.1f%%)", _MODEL_OUT, cv_mean * 100)


if __name__ == "__main__":
    main()
