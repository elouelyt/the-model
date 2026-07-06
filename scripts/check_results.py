"""Check parlay predictions against Wimbledon match results.

Uses Google News RSS to determine match outcomes — searches for each predicted
player name + "Wimbledon" and classifies win/loss from headline keywords.
Results are filtered to articles published after the prediction date so we
match the correct round (not a future/past one).

Run daily in GitHub Actions BEFORE generate_html.py.
"""

import json
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from email.utils import parsedate_to_datetime
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

_WIN_KEYWORDS  = {"beats", "beat", "defeats", "defeated", "wins", "won", "advances",
                  "through", "victory", "victorious", "progresses", "into the"}
_LOSS_KEYWORDS = {"loses", "lost", "exits", "exit", "eliminated", "knocked out",
                  "beaten", "out of", "crashed out", "bows out", "departure"}


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def _player_in_headline(player: str, headline: str) -> bool:
    """True if player's last name appears in the headline."""
    last = player.split()[-1].lower()
    return last in headline.lower()


def _classify_headline(player: str, headline: str) -> str | None:
    """Return 'won' or 'lost' based on headline keywords, or None if unclear."""
    hl = headline.lower()
    last = player.split()[-1].lower()
    if last not in hl:
        return None

    # Check which keyword appears and whether the player is the subject or object
    for kw in _WIN_KEYWORDS:
        idx = hl.find(kw)
        if idx == -1:
            continue
        before = hl[:idx]
        # If player's last name appears before the win keyword → player won
        if last in before:
            return "won"
        # If player's last name appears after the win keyword → player lost (was beaten by someone)
        after = hl[idx:]
        if last in after:
            return "lost"

    for kw in _LOSS_KEYWORDS:
        idx = hl.find(kw)
        if idx == -1:
            continue
        before = hl[:idx]
        if last in before:
            return "lost"
        after = hl[idx:]
        if last in after:
            return "won"

    return None


def fetch_player_result(player: str, pred_date_str: str) -> str | None:
    """Search Google News RSS for a player's Wimbledon result on/after pred_date_str.

    Returns 'won', 'lost', or None if unknown.
    """
    pred_date = datetime.fromisoformat(pred_date_str).replace(tzinfo=timezone.utc)
    # We look for results published within 3 days of the prediction date
    cutoff_end = pred_date + timedelta(days=3)

    last_name = player.split()[-1]
    query = f"{last_name} Wimbledon"
    url = f"https://news.google.com/rss/search?q={requests.utils.quote(query)}&hl=en&gl=US&ceid=US:en"

    try:
        resp = requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
    except Exception as exc:
        logger.warning("News fetch failed for %s: %s", player, exc)
        return None

    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError:
        return None

    items = root.findall(".//item")
    outcomes: dict[str, int] = {"won": 0, "lost": 0}

    for item in items:
        title_el = item.find("title")
        pubdate_el = item.find("pubDate")
        if title_el is None or pubdate_el is None:
            continue

        headline = title_el.text or ""
        try:
            pub_dt = parsedate_to_datetime(pubdate_el.text).astimezone(timezone.utc)
        except Exception:
            continue

        # Only consider articles published after the prediction date and within window
        if pub_dt < pred_date or pub_dt > cutoff_end:
            continue

        outcome = _classify_headline(player, headline)
        if outcome:
            logger.debug("[%s] %s → %s (from: %s)", player, headline[:80], outcome, pub_dt.date())
            outcomes[outcome] += 1

    if outcomes["won"] > 0 and outcomes["lost"] == 0:
        return "won"
    if outcomes["lost"] > 0 and outcomes["won"] == 0:
        return "lost"
    if outcomes["won"] > 0 and outcomes["lost"] > 0:
        # Majority vote
        return "won" if outcomes["won"] >= outcomes["lost"] else "lost"

    return None


def check_parlay(parlay: dict, pred_date: str) -> bool | None:
    """Return True if all legs won, False if any lost, None if any unknown."""
    all_won = True
    for pick in parlay.get("picks", []):
        player = pick.get("player", "")
        result = fetch_player_result(player, pred_date)
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
