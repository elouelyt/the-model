"""Check parlay predictions against ATP match results.

Uses Sofascore's API to determine match outcomes — accessible from GitHub
Actions (no Cloudflare block) and covers ALL ATP tournaments including 250s
and Challengers.

Run daily in GitHub Actions BEFORE generate_html.py.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
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

# Cache of ESPN ATP scoreboard events keyed by "YYYYMMDD" (reused across players)
_espn_cache: dict[str, list[dict]] = {}


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def _fetch_espn_competitions(date_str_8: str) -> list[dict]:
    """Fetch all finished men's singles ATP competitions for a date (YYYYMMDD). Cached."""
    if date_str_8 in _espn_cache:
        return _espn_cache[date_str_8]

    url = f"https://site.api.espn.com/apis/site/v2/sports/tennis/atp/scoreboard?dates={date_str_8}"
    try:
        resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        logger.warning("ESPN fetch failed for %s: %s", date_str_8, exc)
        _espn_cache[date_str_8] = []
        return []

    comps: list[dict] = []
    for event in data.get("events", []):
        for grp in event.get("groupings", []):
            if grp.get("grouping", {}).get("slug") != "mens-singles":
                continue
            for comp in grp.get("competitions", []):
                if comp.get("status", {}).get("type", {}).get("state") == "post":
                    comps.append(comp)

    logger.debug("ESPN %s → %d finished men's singles comps", date_str_8, len(comps))
    _espn_cache[date_str_8] = comps
    return comps


def _player_matches_name(player: str, name: str) -> bool:
    """True if the ESPN display name matches our player name."""
    if _similarity(player, name) >= 0.78:
        return True
    last = player.split()[-1].lower()
    return last in name.lower() and len(last) > 3


def fetch_player_result(player: str, pred_date_str: str, tournament: str = "ATP tennis") -> str | None:
    """Check ESPN ATP scoreboard for a player's result on/after pred_date_str.

    Returns 'won', 'lost', or None if no match found in the 6-day window.
    Uses the competition date to only consider matches >= pred_date.
    """
    pred_date = datetime.fromisoformat(pred_date_str).replace(tzinfo=timezone.utc)
    cutoff_end = pred_date + timedelta(days=6)

    # Fetch up to 7 days of ESPN data (tournament-level, covers all rounds)
    seen_dates: set[str] = set()
    all_comps: list[dict] = []
    for delta in range(7):
        d = pred_date + timedelta(days=delta)
        d8 = d.strftime("%Y%m%d")
        if d8 not in seen_dates:
            seen_dates.add(d8)
            all_comps.extend(_fetch_espn_competitions(d8))

    # Find the EARLIEST finished match for this player on/after pred_date
    best: tuple[datetime, str] | None = None

    for comp in all_comps:
        comp_date_str = comp.get("date", "")
        try:
            comp_dt = datetime.fromisoformat(comp_date_str.replace("Z", "+00:00"))
        except Exception:
            continue

        if comp_dt < pred_date or comp_dt > cutoff_end:
            continue

        competitors = comp.get("competitors", [])
        for c in competitors:
            name = c.get("athlete", {}).get("displayName", "")
            if not _player_matches_name(player, name):
                continue
            won = c.get("winner", False)
            result = "won" if won else "lost"
            if best is None or comp_dt < best[0]:
                best = (comp_dt, result)
            break

    if best:
        logger.info("[espn] %s → %s (match at %s)", player, best[1].upper(), best[0].date())
        return best[1]

    logger.debug("No ESPN match found for %s from %s", player, pred_date_str)
    return None


def check_parlay(parlay: dict, pred_date: str) -> bool | None:
    """Return True if all legs won, False if any lost, None if any unknown."""
    all_won = True
    for pick in parlay.get("picks", []):
        player = pick.get("player", "")
        tournament = pick.get("tournament", "ATP tennis")
        result = fetch_player_result(player, pred_date, tournament=tournament)
        logger.info("[check] %s → %s", player, result)
        if result == "lost":
            return False
        if result is None:
            all_won = False
    return True if all_won else None


def load_track_record() -> dict:
    if _TRACK_FILE.exists():
        return json.loads(_TRACK_FILE.read_text(encoding="utf-8"))
    return {"months": {}}


def save_track_record(tr: dict) -> None:
    _TRACK_FILE.parent.mkdir(parents=True, exist_ok=True)
    _TRACK_FILE.write_text(json.dumps(tr, indent=2, ensure_ascii=False), encoding="utf-8")


def process_pending(tr: dict) -> int:
    """Check any prediction files that don't yet have results. Returns count updated."""
    if not _PREDS_DIR.exists():
        return 0

    now = datetime.now(timezone.utc)
    updated = 0

    # Track leg-sets already seen in earlier days to skip stale API duplicates
    seen_leg_sets: set[frozenset] = set()
    for month_data in tr.get("months", {}).values():
        for day_data in month_data.get("days", {}).values():
            for parl in day_data.get("parlays", []):
                seen_leg_sets.add(frozenset(parl["legs"]))

    for pred_file in sorted(_PREDS_DIR.glob("*.json")):
        try:
            pred = json.loads(pred_file.read_text(encoding="utf-8"))
        except Exception:
            continue

        day_str = pred.get("date")
        if not day_str:
            continue

        # Only check predictions from at least 1 day ago (matches must be finished)
        pred_dt = datetime.fromisoformat(day_str).replace(tzinfo=timezone.utc)
        if (now - pred_dt).days < 1:
            logger.info("Skipping %s — too recent to have results", day_str)
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
        day_results = list(existing.get("parlays", []))

        if not day_results:
            for parl in parlays_raw:
                legs = [p["player"] for p in parl.get("picks", [])]
                key = frozenset(legs)
                if key in seen_leg_sets:
                    logger.info("Skipping duplicate parlay %s for %s (seen in earlier day)", legs, day_str)
                    continue
                day_results.append({
                    "legs":       legs,
                    "stake_odds": parl.get("stake_total_odds"),
                    "best_odds":  parl.get("total_odds"),
                    "won":        None,
                })
                seen_leg_sets.add(key)

        if not day_results:
            logger.info("Day %s has no unique parlays after dedup — skipping", day_str)
            continue

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
            outcome = check_parlay(matching, day_str)
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
    logger.info("Checking parlay results via Google News...")
    tr = load_track_record()
    updated = process_pending(tr)
    save_track_record(tr)
    logger.info("Updated %d day(s) in track record", updated)


if __name__ == "__main__":
    main()
