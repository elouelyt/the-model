"""Elo rating system for UFC fighters, built from data/ufc_fights_history.json.

Unlike the logistic-regression model (mma_model_agent.py), which applies today's
career-to-date stats to every training fight regardless of when it happened, Elo
is point-in-time BY CONSTRUCTION: ratings are built by replaying fights in
chronological order, so a fighter's rating after their 2015 fight only reflects
what was knowable in 2015. No lookahead bias possible.

See scripts/ufc_walkforward_backtest.py for an honest point-in-time accuracy
check (predicts each fight using only ratings as they stood BEFORE that fight).

Design adapted from the "Octane Alpha" project's src/elo.py (MIT-style approach,
reimplemented against our own JSON data format and fight history).
"""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_FIGHTS_PATH = Path(__file__).resolve().parents[2] / "data" / "ufc_fights_history.json"
_ELO_CACHE_PATH = Path(__file__).resolve().parents[2] / "data" / "ufc_elo_ratings.json"

INITIAL_RATING = 1500.0
BASE_K = 32.0

# A fighter's first few results should move their rating a lot (1500 is a
# guess, not knowledge); an established fighter's rating reflects real
# evidence and should move less per fight. Point-in-time safe: the fight
# count used to pick K is only the fights already replayed for that fighter.
ADAPTIVE_K_SCHEDULE = [
    (5, 64.0),
    (10, 48.0),
]

# NOTE: the reference design this is adapted from also weights K by method
# (KO/TKO moves ratings more than a decision, since it's a more decisive
# signal). Not implemented here: every row in data/ufc_fights_history.json
# has method="UNK" (4110/4110) - the scraper that built it never captured
# method. Getting real method data (ufcstats.com has it per-fight) would let
# this be added the same way reach/sig_str_def/td_def were added to the
# logistic model.


def _k_for(fight_count: int) -> float:
    for threshold, k in ADAPTIVE_K_SCHEDULE:
        if fight_count < threshold:
            return k
    return BASE_K


def expected_score(rating_a: float, rating_b: float) -> float:
    """Probability fighter A beats fighter B given their current ratings."""
    return 1.0 / (1.0 + 10 ** ((rating_b - rating_a) / 400.0))


class EloRatingSystem:
    def __init__(self):
        self.ratings: dict[str, float] = {}
        self.fight_counts: dict[str, int] = {}
        # Running sum/count of OPPONENTS' ratings at fight time, per fighter -
        # a strength-of-schedule proxy. Elo itself already partly captures this
        # (beating a weak opponent earns little), but the logistic model's
        # other stat features (td_acc, sig_str_acc, finish_rate...) are raw
        # career rates with NO opponent-quality adjustment at all - a 10-0
        # record built against weak competition posts the same gaudy stats as
        # one built against elite competition. This gives those features a
        # companion signal that says which record to trust more.
        self._opp_elo_sum: dict[str, float] = {}
        self._opp_elo_count: dict[str, int] = {}

    def get_rating(self, fighter: str) -> float:
        return self.ratings.get(fighter, INITIAL_RATING)

    def avg_opponent_elo(self, fighter: str) -> float:
        """Mean Elo of everyone this fighter has faced, at the time they faced them.

        Defaults to INITIAL_RATING for a fighter with no recorded opponents -
        "unknown schedule strength" should read as neutral, not as weak or strong.
        """
        n = self._opp_elo_count.get(fighter, 0)
        if n == 0:
            return INITIAL_RATING
        return self._opp_elo_sum[fighter] / n

    def update(self, winner: str, loser: str, k_mult: float = 1.0) -> None:
        r_w, r_l = self.get_rating(winner), self.get_rating(loser)
        exp_w = expected_score(r_w, r_l)

        k_w = _k_for(self.fight_counts.get(winner, 0)) * k_mult
        k_l = _k_for(self.fight_counts.get(loser, 0)) * k_mult

        # Opponent-quality bookkeeping uses each side's rating BEFORE this
        # fight's result is applied - a fighter's resume records who they
        # actually faced at the time, not a rating inflated by this result.
        self._opp_elo_sum[winner] = self._opp_elo_sum.get(winner, 0.0) + r_l
        self._opp_elo_count[winner] = self._opp_elo_count.get(winner, 0) + 1
        self._opp_elo_sum[loser] = self._opp_elo_sum.get(loser, 0.0) + r_w
        self._opp_elo_count[loser] = self._opp_elo_count.get(loser, 0) + 1

        self.ratings[winner] = r_w + k_w * (1.0 - exp_w)
        self.ratings[loser] = r_l + k_l * (0.0 - (1.0 - exp_w))
        self.fight_counts[winner] = self.fight_counts.get(winner, 0) + 1
        self.fight_counts[loser] = self.fight_counts.get(loser, 0) + 1

    def build_from_history(self, fights: list[dict]) -> "EloRatingSystem":
        """Replay fights in chronological order. Expects date, winner, loser keys."""
        ordered = sorted(
            (f for f in fights if f.get("winner") and f.get("loser") and f.get("date")),
            key=lambda f: f["date"],
        )
        for fight in ordered:
            self.update(fight["winner"], fight["loser"])
        logger.info("Elo built from %d fights, %d rated fighters", len(ordered), len(self.ratings))
        return self


_elo_cache: EloRatingSystem | None = None


def _load_elo() -> EloRatingSystem:
    global _elo_cache
    if _elo_cache is not None:
        return _elo_cache
    _elo_cache = EloRatingSystem()
    if not _FIGHTS_PATH.exists():
        logger.warning("%s not found — Elo ratings unavailable", _FIGHTS_PATH)
        return _elo_cache
    data = json.loads(_FIGHTS_PATH.read_text(encoding="utf-8"))
    _elo_cache.build_from_history(data.get("fights", []))
    return _elo_cache


def predict_elo(fighter1: str, fighter2: str) -> dict:
    """Return elo ratings/probabilities plus each fighter's strength-of-schedule
    proxy (avg_opp_elo_f*: mean Elo of everyone they've faced)."""
    elo = _load_elo()
    r1, r2 = elo.get_rating(fighter1), elo.get_rating(fighter2)
    p1 = expected_score(r1, r2)
    return {
        "prob_f1": round(p1, 4), "prob_f2": round(1 - p1, 4),
        "elo_f1": round(r1, 1), "elo_f2": round(r2, 1),
        "avg_opp_elo_f1": round(elo.avg_opponent_elo(fighter1), 1),
        "avg_opp_elo_f2": round(elo.avg_opponent_elo(fighter2), 1),
    }


def save_ratings_snapshot() -> None:
    """Persist current Elo ratings to disk (for inspection / debugging)."""
    elo = _load_elo()
    payload = {
        "ratings": {k: round(v, 1) for k, v in elo.ratings.items()},
        "fight_counts": elo.fight_counts,
    }
    _ELO_CACHE_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Saved Elo ratings snapshot to %s (%d fighters)", _ELO_CACHE_PATH, len(elo.ratings))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    save_ratings_snapshot()
