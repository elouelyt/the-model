"""Check yesterday's parlay predictions against The-Odds-API scores.

For each saved prediction file, fetches completed match scores and marks
each parlay leg as won/lost. Updates data/track_record.json with the results.

Run daily in GitHub Actions BEFORE generate_html.py.
"""

import json
import logging
import os
import sys
from datetime import date, datetime, timedelta, timezone
from difflib import SequenceMatcher
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s — %(levelname)s — %(message)s")
logger = logging.getLogger(__name__)

_ROOT          = Path(__file__).resolve().parents[1]
_PREDS_DIR     = _ROOT / "data" / "predictions"
_TRACK_FILE    = _ROOT / "data" / "track_record.json"
_API_KEY       = os.getenv("THE_ODDS_API_KEY", "")
_STAKE_PER_BET = 15.0  # €15 per parlay


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def _match_player(name: str, candidates: list[str], cutoff: float = 0.75) -> str | None:
    best, score = None, 0.0
    name_last = name.split()[-1].lower()
    for c in candidates:
        s = max(_similarity(name, c), _similarity(name_last, c.split()[-1].lower()) * 0.9)
        if s > score:
            score, best = s, c
    return best if score >= cutoff else None


def fetch_scores(sport_key: str, days_from: int = 1) -> list[dict]:
    """Fetch completed scores from The-Odds-API."""
    if not _API_KEY:
        return []
    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/scores"
    try:
        r = requests.get(url, params={"apiKey": _API_KEY, "daysFrom": days_from}, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        logger.warning("Failed to fetch scores for %s: %s", sport_key, exc)
        return []


def fetch_all_tennis_scores() -> dict[str, str]:
    """Return {player_name: 'won'|'lost'} for all completed tennis matches."""
    # Try both ATP Wimbledon and generic ATP keys
    sport_keys = ["tennis_atp_wimbledon", "tennis_atp", "tennis_wta"]
    results: dict[str, str] = {}

    for sport_key in sport_keys:
        scores = fetch_scores(sport_key, days_from=3)
        for match in scores:
            if not match.get("completed"):
                continue
            home = match.get("home_team", "")
            away = match.get("away_team", "")
            score_list = match.get("scores") or []
            if not score_list:
                continue
            # Find winner: player with highest score value
            winner = None
            try:
                scores_map = {s["name"]: float(s["score"]) for s in score_list if s.get("score") not in (None, "")}
                if scores_map:
                    winner = max(scores_map, key=lambda k: scores_map[k])
            except Exception:
                pass
            if winner:
                for player in [home, away]:
                    results[player] = "won" if player == winner else "lost"

    logger.info("Fetched results for %d players", len(results))
    return results


def check_parlay(parlay: dict, results: dict[str, str]) -> bool | None:
    """Return True if all legs won, False if any lost, None if unknown."""
    for pick in parlay.get("picks", []):
        player = pick.get("player", "")
        matched = _match_player(player, list(results.keys()))
        if matched is None:
            logger.debug("No result found for %s", player)
            return None  # can't determine
        outcome = results[matched]
        if outcome == "lost":
            return False
    return True


def load_track_record() -> dict:
    if _TRACK_FILE.exists():
        return json.loads(_TRACK_FILE.read_text(encoding="utf-8"))
    return {"months": {}}


def save_track_record(tr: dict) -> None:
    _TRACK_FILE.parent.mkdir(parents=True, exist_ok=True)
    _TRACK_FILE.write_text(json.dumps(tr, indent=2, ensure_ascii=False), encoding="utf-8")


def process_pending(tr: dict, results: dict[str, str]) -> int:
    """Check any prediction files that don't yet have results. Returns count updated."""
    updated = 0
    for pred_file in sorted(_PREDS_DIR.glob("*.json")):
        try:
            pred = json.loads(pred_file.read_text(encoding="utf-8"))
        except Exception:
            continue

        day_str = pred.get("date")  # YYYY-MM-DD
        if not day_str:
            continue

        month_str = day_str[:7]  # YYYY-MM
        day_num = int(day_str[8:10])

        # Init month if needed
        tr["months"].setdefault(month_str, {"days": {}})
        month = tr["months"][month_str]

        day_key = str(day_num)
        existing = month["days"].get(day_key, {})

        # Skip days that are fully resolved
        if existing.get("resolved"):
            continue

        parlays = pred.get("parlays", [])
        day_results = existing.get("parlays", [])

        # Build results list if empty
        if not day_results:
            day_results = [
                {
                    "legs": [p["player"] for p in parl.get("picks", [])],
                    "stake_odds": parl.get("stake_total_odds"),
                    "best_odds":  parl.get("total_odds"),
                    "won": None,
                }
                for parl in parlays
            ]

        any_updated = False
        all_resolved = True
        for entry in day_results:
            if entry["won"] is not None:
                continue
            # Find parlay in original pred by matching legs
            matching_parl = next(
                (p for p in parlays if [q["player"] for q in p.get("picks", [])] == entry["legs"]),
                None
            )
            if matching_parl is None:
                all_resolved = False
                continue
            outcome = check_parlay(matching_parl, results)
            if outcome is not None:
                entry["won"] = outcome
                any_updated = True
            else:
                all_resolved = False

        if any_updated or not existing:
            month["days"][day_key] = {
                "parlays": day_results,
                "resolved": all_resolved,
            }
            updated += 1

    return updated


def main() -> None:
    if not _PREDS_DIR.exists():
        logger.info("No predictions directory yet — nothing to check")
        return

    logger.info("Fetching tennis scores...")
    results = fetch_all_tennis_scores()

    if not results:
        logger.warning("No scores fetched — skipping results check")
        return

    tr = load_track_record()
    updated = process_pending(tr, results)
    save_track_record(tr)
    logger.info("Updated %d day(s) in track record", updated)


if __name__ == "__main__":
    main()
