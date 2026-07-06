"""Check parlay predictions against Jeff Sackmann ATP match results.

Uses the JeffSackmann/tennis_atp GitHub repo (atp_matches_YYYY.csv) which is
updated daily with completed match results — more reliable than The-Odds-API
/scores which does not mark tennis matches as completed.

Run daily in GitHub Actions BEFORE generate_html.py.
"""

import csv
import io
import json
import logging
from datetime import datetime, timezone
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
_STAKE_PER_BET = 15.0

_SACKMANN_BASE = "https://raw.githubusercontent.com/JeffSackmann/tennis_atp/master"


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


def fetch_sackmann_results() -> dict[str, str]:
    """Return {player_name: 'won'|'lost'} from Sackmann ATP results CSV."""
    year = datetime.now(timezone.utc).year
    url = f"{_SACKMANN_BASE}/atp_matches_{year}.csv"
    try:
        r = requests.get(url, timeout=20)
        r.raise_for_status()
    except Exception as exc:
        logger.warning("Failed to fetch Sackmann results: %s", exc)
        return {}

    results: dict[str, str] = {}
    reader = csv.DictReader(io.StringIO(r.text))
    for row in reader:
        winner = row.get("winner_name", "").strip()
        loser  = row.get("loser_name", "").strip()
        score  = row.get("score", "").strip()
        # Skip walkovers / retirements with no real result
        if not winner or not loser:
            continue
        if score in ("W/O", "", "DEF"):
            continue
        results[winner] = "won"
        results[loser]  = "lost"

    logger.info("Loaded %d player results from Sackmann %d CSV", len(results), year)
    return results


def check_parlay(parlay: dict, results: dict[str, str]) -> bool | None:
    """Return True if all legs won, False if any lost, None if unknown."""
    candidates = list(results.keys())
    for pick in parlay.get("picks", []):
        player = pick.get("player", "")
        matched = _match_player(player, candidates)
        if matched is None:
            logger.debug("No result found for %s", player)
            return None
        outcome = results[matched]
        if outcome == "lost":
            logger.info("Leg LOST: %s (matched %s)", player, matched)
            return False
        logger.debug("Leg won: %s (matched %s)", player, matched)
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
    if not _PREDS_DIR.exists():
        return 0

    updated = 0
    for pred_file in sorted(_PREDS_DIR.glob("*.json")):
        try:
            pred = json.loads(pred_file.read_text(encoding="utf-8"))
        except Exception:
            continue

        day_str = pred.get("date")
        if not day_str:
            continue

        month_str = day_str[:7]
        day_num   = int(day_str[8:10])

        tr["months"].setdefault(month_str, {"days": {}})
        month = tr["months"][month_str]
        day_key = str(day_num)
        existing = month["days"].get(day_key, {})

        if existing.get("resolved"):
            continue

        parlays_raw = pred.get("parlays", [])
        day_results = existing.get("parlays", [])

        if not day_results:
            day_results = [
                {
                    "legs":       [p["player"] for p in parl.get("picks", [])],
                    "stake_odds": parl.get("stake_total_odds"),
                    "best_odds":  parl.get("total_odds"),
                    "won":        None,
                }
                for parl in parlays_raw
            ]

        any_updated  = False
        all_resolved = True
        for entry in day_results:
            if entry["won"] is not None:
                continue
            matching = next(
                (p for p in parlays_raw if [q["player"] for q in p.get("picks", [])] == entry["legs"]),
                None,
            )
            if matching is None:
                all_resolved = False
                continue
            outcome = check_parlay(matching, results)
            if outcome is not None:
                entry["won"] = outcome
                any_updated  = True
                logger.info("Day %s parlay %s → %s", day_str, entry["legs"], "WON" if outcome else "LOST")
            else:
                all_resolved = False

        if any_updated or not existing:
            month["days"][day_key] = {"parlays": day_results, "resolved": all_resolved}
            updated += 1

    return updated


def main() -> None:
    logger.info("Fetching ATP results from Sackmann repo...")
    results = fetch_sackmann_results()

    if not results:
        logger.warning("No results loaded — skipping results check")
        return

    tr = load_track_record()
    updated = process_pending(tr, results)
    save_track_record(tr)
    logger.info("Updated %d day(s) in track record", updated)


if __name__ == "__main__":
    main()
