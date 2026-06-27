"""Ranking agent — reads ATP rankings from data/rankings_cache.json.

The cache is updated locally via scripts/rankings_update.py (which uses
cloudscraper to bypass Cloudflare) and pushed to GitHub so that GitHub
Actions can use it without hitting atptour.com directly.

Rankings are updated weekly (every Monday on the ATP Tour), so the cache
only needs to be refreshed once a week via morning_update.bat.
"""

import difflib
import json
import logging
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s — %(levelname)s — %(message)s")
logger = logging.getLogger(__name__)

_CACHE_PATH = Path(__file__).resolve().parents[2] / "data" / "rankings_cache.json"


def _load_rankings_cache() -> dict[str, dict]:
    """Load the rankings cache from disk.

    Returns:
        A dict mapping full player name → {"rank": int, "points": int}.
        Returns empty dict if cache is missing or corrupt.
    """
    if not _CACHE_PATH.exists():
        logger.warning("rankings_cache.json not found at %s — run scripts/rankings_update.py", _CACHE_PATH)
        return {}

    try:
        payload = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
        rankings = payload.get("rankings", {})
        cached_at = payload.get("timestamp", "unknown")
        logger.info("Loaded %d ranked players from cache (snapshot: %s)", len(rankings), cached_at)
        return rankings
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to parse rankings_cache.json: %s", exc)
        return {}


def _match_name(odds_name: str, cache_names: list[str]) -> str | None:
    """Fuzzy-match an odds API player name to the closest cached name."""
    odds_lower = odds_name.lower()
    name_map = {n.lower(): n for n in cache_names}

    if odds_lower in name_map:
        return name_map[odds_lower]

    matches = difflib.get_close_matches(odds_lower, list(name_map.keys()), n=1, cutoff=0.6)
    if matches:
        return name_map[matches[0]]

    return None


def fetch_atp_rankings(player_names: list[str]) -> dict[str, dict]:
    """Fetch current ATP rankings for a list of players from the local cache.

    Cache is populated by scripts/rankings_update.py which scrapes atptour.com
    locally (requires cloudscraper; run with VPN if needed).

    Args:
        player_names: List of player name strings exactly as returned by The-Odds-API.

    Returns:
        A dict mapping player name → {"rank": int, "points": int}.
        Players not found in cache are silently omitted.
    """
    if not player_names:
        raise ValueError("player_names must not be empty.")

    logger.info("Resolving ATP rankings for %d players from cache.", len(player_names))
    ranking_map = _load_rankings_cache()

    if not ranking_map:
        logger.warning("Rankings cache is empty — predictions will run without ranking data")
        return {}

    cache_names = list(ranking_map.keys())
    result: dict[str, dict] = {}

    for odds_name in player_names:
        matched = _match_name(odds_name, cache_names)
        if matched:
            result[odds_name] = ranking_map[matched]
        else:
            logger.warning("No ranking match found for: %r", odds_name)

    logger.info("Matched rankings for %d/%d players.", len(result), len(player_names))
    return result


if __name__ == "__main__":
    test_players = [
        "Carlos Alcaraz", "Jannik Sinner",
        "Alexander Zverev", "Casper Ruud",
        "Ben Shelton", "Alex Michelsen",
        "Adolfo Daniel Vallejo", "Nicolas Mejia",
    ]
    rankings = fetch_atp_rankings(player_names=test_players)
    if rankings:
        print(f"\nRankings for {len(rankings)} players:")
        for name, data in sorted(rankings.items(), key=lambda x: x[1]["rank"]):
            print(f"  {data['rank']:>3}. {name:<30} {data['points']:>6} pts")
    else:
        print("No rankings found — run scripts/rankings_update.py first")
