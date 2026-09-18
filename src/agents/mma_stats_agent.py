"""MMA stats agent — matches fighter names to cached UFC stats."""

import difflib
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_CACHE_PATH = Path(__file__).resolve().parents[2] / "data" / "ufc_fighters_cache.json"


def _load_cache() -> dict[str, dict]:
    if not _CACHE_PATH.exists():
        logger.warning("ufc_fighters_cache.json not found — run scripts/ufc_scrape_fighters.py")
        return {}
    try:
        payload = json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
        return payload.get("fighters", {})
    except Exception as exc:
        logger.error("Failed to load UFC fighters cache: %s", exc)
        return {}


def _match_name(name: str, cache_names: list[str], cutoff: float = 0.80) -> str | None:
    lower = name.lower()
    name_map = {n.lower(): n for n in cache_names}
    if lower in name_map:
        return name_map[lower]
    matches = difflib.get_close_matches(lower, list(name_map.keys()), n=1, cutoff=cutoff)
    if matches:
        return name_map[matches[0]]
    return None


def fetch_fighter_stats(fighter_names: list[str]) -> dict[str, dict]:
    """Return stats for a list of fighter names (fuzzy-matched to cache).

    Returns dict mapping input name → stats dict (subset of ufc_fighters_cache fields).
    Missing fighters are silently omitted.
    """
    cache = _load_cache()
    if not cache:
        return {}

    cache_names = list(cache.keys())
    result: dict[str, dict] = {}

    for name in fighter_names:
        matched = _match_name(name, cache_names)
        if matched:
            result[name] = cache[matched]
        else:
            logger.warning("No UFC stats match for: %r", name)

    logger.info("Matched UFC stats for %d/%d fighters", len(result), len(fighter_names))
    return result
