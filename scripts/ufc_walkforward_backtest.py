"""Walk-forward backtest of the MMA Elo rating core (src/agents/mma_elo_agent.py).

Unlike scripts/ufc_train_model.py's k-fold CV (which standardizes stats across
the WHOLE dataset before splitting, so each fold's scaler has seen values from
fights outside it, and the stat features themselves are today's career-to-date
snapshot applied to every historical fight regardless of date), this replays
fights in strict chronological order and predicts each one using ONLY the Elo
ratings as they stood the moment before that fight happened. No future
information reaches any prediction. This is what "how accurate is Elo, really"
actually means.

Also reports a calibration table: when Elo says "65%", does the favorite
actually win ~65% of the time in this data? A model can have decent accuracy
while being badly overconfident or underconfident at specific probability
bands, and only a calibration check catches that.

Run: python scripts/ufc_walkforward_backtest.py
"""

import json
import logging
import math
from collections import defaultdict
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s — %(levelname)s — %(message)s")
logger = logging.getLogger(__name__)

_FIGHTS_PATH = Path(__file__).resolve().parents[1] / "data" / "ufc_fights_history.json"

INITIAL_RATING = 1500.0
BASE_K = 32.0
ADAPTIVE_K_SCHEDULE = [(5, 64.0), (10, 48.0)]


def _k_for(fight_count: int) -> float:
    for threshold, k in ADAPTIVE_K_SCHEDULE:
        if fight_count < threshold:
            return k
    return BASE_K


def _expected(r_a: float, r_b: float) -> float:
    return 1.0 / (1.0 + 10 ** ((r_b - r_a) / 400.0))


def main() -> None:
    data = json.loads(_FIGHTS_PATH.read_text(encoding="utf-8"))
    fights = [f for f in data["fights"] if f.get("winner") and f.get("loser") and f.get("date")]
    fights.sort(key=lambda f: f["date"])
    logger.info("Walk-forward over %d chronologically-ordered fights", len(fights))

    ratings: dict[str, float] = {}
    fight_counts: dict[str, int] = {}

    correct = 0
    predicted = 0
    brier_sum = 0.0
    # Calibration buckets: predicted-probability decile -> [wins, total]
    calib: dict[int, list[int]] = defaultdict(lambda: [0, 0])

    for fight in fights:
        w, l = fight["winner"], fight["loser"]
        r_w = ratings.get(w, INITIAL_RATING)
        r_l = ratings.get(l, INITIAL_RATING)
        cnt_w = fight_counts.get(w, 0)
        cnt_l = fight_counts.get(l, 0)

        # Only score fights where BOTH fighters already have some prior history in
        # our replay - a fresh 1500-vs-1500 matchup is an uninformative coinflip
        # by construction and would just dilute the accuracy number with noise
        # that has nothing to do with whether Elo works once it has data.
        if cnt_w >= 3 and cnt_l >= 3:
            prob_w = _expected(r_w, r_l)
            # Score from the perspective of whichever side has prob >= 0.5,
            # i.e. "did the model's favorite actually win".
            fav_prob = max(prob_w, 1 - prob_w)
            favorite_won = prob_w >= 0.5  # w is favorite and w is who actually won
            predicted += 1
            if favorite_won:
                correct += 1
            brier_sum += (prob_w - 1.0) ** 2  # w actually won (outcome=1 for w)
            bucket = min(9, int(fav_prob * 10))
            calib[bucket][1] += 1
            if favorite_won:
                calib[bucket][0] += 1

        # Update AFTER predicting.
        exp_w = _expected(r_w, r_l)
        k_w = _k_for(cnt_w)
        k_l = _k_for(cnt_l)
        ratings[w] = r_w + k_w * (1.0 - exp_w)
        ratings[l] = r_l + k_l * (0.0 - (1.0 - exp_w))
        fight_counts[w] = cnt_w + 1
        fight_counts[l] = cnt_l + 1

    accuracy = correct / predicted if predicted else 0.0
    brier = brier_sum / predicted if predicted else 0.0
    logger.info("Scored %d fights (both fighters had >=3 prior fights)", predicted)
    logger.info("Walk-forward accuracy: %.1f%%  Brier: %.4f", accuracy * 100, brier)

    print("\nCalibration table (favorite's predicted probability vs actual win rate):")
    print(f"{'bucket':>12s} {'n':>6s} {'predicted':>10s} {'actual':>8s}")
    for b in range(5, 10):
        wins, total = calib[b][0], calib[b][1]
        if total == 0:
            continue
        lo, hi = b * 10, b * 10 + 10
        actual = wins / total * 100
        print(f"{lo:>4d}-{hi:<4d}%   {total:>6d} {(lo+hi)/2:>9.0f}% {actual:>7.1f}%")

    out = {
        "n_fights_total": len(fights),
        "n_fights_scored": predicted,
        "walkforward_accuracy": round(accuracy, 4),
        "brier_score": round(brier, 4),
        "calibration": {
            f"{b*10}-{b*10+10}": {"n": calib[b][1], "actual_win_rate": round(calib[b][0] / calib[b][1], 4)}
            for b in range(10) if calib[b][1] > 0
        },
    }
    out_path = Path(__file__).resolve().parents[1] / "data" / "ufc_elo_walkforward_results.json"
    out_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    logger.info("Saved results to %s", out_path)


if __name__ == "__main__":
    main()
