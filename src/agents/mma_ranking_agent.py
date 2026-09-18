"""MMA ranking agent — returns UFC division rank from local cache."""

import difflib
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_CACHE_PATH = Path(__file__).resolve().parents[2] / "data" / "ufc_rankings_cache.json"

_WEIGHT_CLASS_KEYWORDS = {
    "flyweight": ["flyweight", "fly"],
    "bantamweight": ["bantamweight", "bant"],
    "featherweight": ["featherweight", "feat", "feather"],
    "lightweight": ["lightweight", "light"],
    "welterweight": ["welterweight", "welt", "welter"],
    "middleweight": ["middleweight", "middle", "midd"],
    "light heavyweight": ["light heavyweight", "lhw", "light heavy"],
    "heavyweight": ["heavyweight", "heavy"],
    "women's strawweight": ["strawweight", "straw"],
    "women's flyweight": ["women's flyweight", "w flyweight"],
    "women's bantamweight": ["women's bantamweight", "w bantamweight"],
    "women's featherweight": ["women's featherweight", "w featherweight"],
}


def _load_cache() -> dict:
    if not _CACHE_PATH.exists():
        logger.warning("ufc_rankings_cache.json not found — run scripts/ufc_scrape_rankings.py")
        return {}
    try:
        return json.loads(_CACHE_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.error("Failed to load UFC rankings cache: %s", exc)
        return {}


def _match_fighter(name: str, division_rankings: dict[str, int]) -> int | None:
    """Fuzzy-match fighter name to division rankings, return rank or None."""
    lower = name.lower()
    name_map = {n.lower(): n for n in division_rankings}
    if lower in name_map:
        return division_rankings[name_map[lower]]
    matches = difflib.get_close_matches(lower, list(name_map.keys()), n=1, cutoff=0.80)
    if matches:
        return division_rankings[name_map[matches[0]]]
    return None


def fetch_ufc_rankings(fighter_names: list[str], weight_class: str = "") -> dict[str, dict]:
    """Return UFC ranking info for a list of fighters.

    Args:
        fighter_names: Names as returned by The-Odds-API.
        weight_class: Optional weight class string to narrow search.

    Returns:
        dict mapping name → {"rank": int, "division": str}
    """
    payload = _load_cache()
    if not payload:
        return {}

    all_divisions: dict[str, dict[str, int]] = payload.get("rankings", {})
    if not all_divisions:
        return {}

    # Filter divisions by weight_class if provided
    wc_lower = weight_class.lower()
    if wc_lower:
        filtered = {
            div: ranks for div, ranks in all_divisions.items()
            if any(kw in div.lower() for kw in [wc_lower] + _WEIGHT_CLASS_KEYWORDS.get(wc_lower, []))
        } or all_divisions
    else:
        filtered = all_divisions

    result = {}
    for name in fighter_names:
        for division, ranks in filtered.items():
            rank = _match_fighter(name, ranks)
            if rank is not None:
                result[name] = {"rank": rank, "division": division}
                break
        if name not in result:
            logger.debug("No UFC ranking found for: %r", name)

    return result
