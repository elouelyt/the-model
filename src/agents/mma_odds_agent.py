"""MMA odds agent — fetches upcoming MMA fights from The-Odds-API."""

import logging
import os
from datetime import datetime, timedelta, timezone

import requests

logger = logging.getLogger(__name__)

_SPORT_KEY = "mma_mixed_martial_arts"


def fetch_mma_odds() -> list[dict]:
    """Return upcoming MMA fights with h2h odds from Stake (EU region).

    Each fight dict contains:
        fighter1, fighter2, odds1, odds2, commence_time (ISO str), event
    """
    api_key = os.getenv("THE_ODDS_API_KEY")
    if not api_key:
        logger.warning("THE_ODDS_API_KEY not set — skipping MMA odds")
        return []

    try:
        resp = requests.get(
            f"https://api.the-odds-api.com/v4/sports/{_SPORT_KEY}/odds/",
            params={"apiKey": api_key, "regions": "eu", "markets": "h2h", "oddsFormat": "decimal"},
            timeout=15,
        )
        resp.raise_for_status()
    except Exception as exc:
        logger.warning("MMA odds fetch failed: %s", exc)
        return []

    now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=60)
    fights = []

    for match in resp.json():
        ct_str = match.get("commence_time", "")
        try:
            ct = datetime.fromisoformat(ct_str.replace("Z", "+00:00"))
        except ValueError:
            continue

        if ct <= now or ct > cutoff:
            continue  # skip in-play / past / too far ahead

        bookmakers = match.get("bookmakers", [])
        stake_bm = next((b for b in bookmakers if b["key"] == "stake"), None)
        bm = stake_bm or (bookmakers[0] if bookmakers else None)
        if not bm:
            continue

        outcomes = bm["markets"][0]["outcomes"]
        if len(outcomes) < 2:
            continue

        p1, p2 = outcomes[0], outcomes[1]
        fights.append({
            "fighter1": p1["name"],
            "fighter2": p2["name"],
            "odds1": p1["price"],
            "odds2": p2["price"],
            "implied1": round(1 / p1["price"], 4),
            "implied2": round(1 / p2["price"], 4),
            "commence_time": ct_str,
            "commence_dt": ct,
            "event": match.get("sport_title", "MMA"),
            "bookmaker": bm["key"],
        })

    fights.sort(key=lambda f: f["commence_dt"])
    logger.info("Fetched %d upcoming MMA fights", len(fights))
    return fights
