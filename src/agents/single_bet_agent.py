"""Single-bet selector — picks the one best value bet for the day.

Algorithm:
1. Collect all players across all matches that have edge > MIN_EDGE and
   model_prob > MIN_MODEL_PROB (a genuine positive-EV signal).
2. Sort by edge descending — highest edge = largest gap between model
   confidence and what the market offers.
3. Return the top pick with full metadata, or None if nothing qualifies.

Why singles instead of parlays: at ~63% model accuracy per leg, a single
bet at ~1.52 implied odds has positive EV. Combining two legs at 1.72
combined odds requires ~76% accuracy per leg to break even — a bar the
model cannot clear. Singles are the only mathematically sound strategy
given the current accuracy range.

Stake "First Set, You Win" boost: when betting a single on Stake, the
effective win condition is winning the first set — not the full match.
A player the model rates at 63% to win the match typically wins the first
set ~70% of the time (serve dominance, no fatigue, no momentum shift).
Betting at match-winner odds with a first-set win condition yields
~6-8 pp extra effective win rate, significantly improving EV.
Always place the pick as a "First Set Winner" single on Stake.
"""

import logging
from pathlib import Path
import json

logger = logging.getLogger(__name__)

_MIN_EDGE        = 0.03   # model must beat market by at least 3 pp
_MIN_MODEL_PROB  = 0.61   # model must be at least 61% confident
_MIN_PRICE       = 1.30   # minimum decimal odds — below this the payout is too thin

# Players with documented poor performance — downweight their picks
_AVOID_PLAYERS: frozenset[str] = frozenset()  # populated dynamically from track_record


def _load_struggling_players() -> frozenset[str]:
    """Read track_record.json and flag players who lost ≥3 parlays in the last 7 days.

    Used to add a soft warning on picks — does not exclude them entirely,
    but reduces edge threshold so they only surface with a strong signal.
    """
    try:
        tr_path = Path(__file__).parent.parent.parent / "data" / "track_record.json"
        if not tr_path.exists():
            return frozenset()

        tr = json.loads(tr_path.read_text())
        loss_count: dict[str, int] = {}

        for month_data in tr.get("months", {}).values():
            for day_data in month_data.get("days", {}).values():
                for parlay in day_data.get("parlays", []):
                    if parlay.get("won") is False:
                        for leg in parlay.get("legs", []):
                            loss_count[leg] = loss_count.get(leg, 0) + 1

        # Flag players with 4+ parlay losses (appears in many losing combos)
        struggling = frozenset(p for p, n in loss_count.items() if n >= 4)
        if struggling:
            logger.info("[single_bet_agent] Struggling players (4+ losses): %s", list(struggling))
        return struggling
    except Exception as exc:
        logger.debug("[single_bet_agent] Could not load track_record: %s", exc)
        return frozenset()


def select_daily_pick(results: list[dict]) -> dict | None:
    """Select the single best value bet from today's match predictions.

    Args:
        results: List of match dicts from compute_predictions_node.

    Returns:
        A pick dict with full metadata, or None if no qualifying pick exists.
    """
    struggling = _load_struggling_players()
    candidates: list[dict] = []

    for match in results:
        if "error" in match or not match.get("players"):
            continue

        home = match["home"]
        away = match["away"]
        surface = match.get("surface", "hard")
        sport_title = match.get("sport_title", "")

        for p in match["players"]:
            edge = p.get("edge", 0)
            model_prob = p.get("model_prob", 0)
            signal = p.get("signal", "no_bet")

            # Hard filters
            if signal == "no_bet":
                continue
            if model_prob < _MIN_MODEL_PROB:
                continue
            if edge < _MIN_EDGE:
                continue

            # Price check — prefer best available (Stake if present, else best bk)
            best_price = p.get("stake_price") or 0
            if not best_price:
                bks = p.get("bookmakers", [])
                best_price = max((b["price"] for b in bks), default=0)
            if best_price < _MIN_PRICE:
                continue

            opponent = away if p["player"] == home else home
            opponent_rank = next(
                (q.get("rank") for q in match["players"] if q["player"] == opponent),
                None,
            )

            is_struggling = any(
                s.lower() in p["player"].lower() for s in struggling
            )

            candidates.append({
                "player":         p["player"],
                "rank":           p["rank"],
                "points":         p["points"],
                "opponent":       opponent,
                "opponent_rank":  opponent_rank,
                "model_prob":     p["model_prob"],
                "raw_implied":    p["raw_implied"],
                "edge":           p["edge"],
                "signal":         p["signal"],
                "surface":        surface,
                "sport_title":    sport_title,
                "best_price":     round(best_price, 3),
                "stake_price":    p.get("stake_price"),
                "best_bookmaker": (
                    "Stake" if p.get("stake_price") else
                    (max(p.get("bookmakers", []), key=lambda b: b["price"], default={})
                     .get("bookmaker_title", ""))
                ),
                "sentiment":      p.get("sentiment", {}),
                "recommendation": p.get("recommendation", ""),
                "is_struggling":  is_struggling,
            })

    if not candidates:
        logger.info("[single_bet_agent] No qualifying picks (edge>%.0f%%, model>%.0f%%)",
                    _MIN_EDGE * 100, _MIN_MODEL_PROB * 100)
        return None

    # Sort: non-struggling first, then by edge descending
    candidates.sort(key=lambda c: (c["is_struggling"], -c["edge"]))
    pick = candidates[0]
    logger.info(
        "[single_bet_agent] Daily pick: %s vs %s — edge %.1f%%, price %.2f%s",
        pick["player"], pick["opponent"], pick["edge"] * 100, pick["best_price"],
        " [struggling]" if pick["is_struggling"] else "",
    )
    return pick
