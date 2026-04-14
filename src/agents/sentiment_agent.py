"""Sentiment agent — surfaces player form signals from recent news headlines.

Scrapes Google News RSS for each player, scores the last N headlines using
keyword matching, and returns a compact sentiment flag. No API key required.

Uses ThreadPoolExecutor to fetch all players in parallel, keeping total
latency proportional to the slowest single request rather than O(n).
"""

import logging
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote_plus

import requests

logger = logging.getLogger(__name__)

_NEWS_RSS_URL = (
    "https://news.google.com/rss/search"
    "?q={query}&hl=en&gl=US&ceid=US:en"
)
_TIMEOUT = 8
_MAX_HEADLINES = 6
_MAX_WORKERS = 10

# Keywords scored as negative (injury, withdrawal, controversy)
_NEGATIVE: set[str] = {
    "injur", "withdraw", "retir", "illness", "ill ", "doubt",
    "suspend", "absent", "scratch", "concern", "struggling",
    "lost", "defeated", "eliminated", "crisis", "default",
}
# Keywords scored as positive (good form, titles, strong results)
_POSITIVE: set[str] = {
    "win", "won", "champion", "title", "final", "semifinal",
    "dominant", "strong form", "comeback", "streak", "victor",
    "best", "unbeaten", "confident", "in form",
}

# Sentiment thresholds
_POSITIVE_THRESHOLD = 1   # net score ≥ 1 → "positive"
_CONCERN_THRESHOLD = -1   # net score ≤ -1 → "concern"


def _score_headline(headline: str) -> int:
    """Return +1, -1, or 0 for a single headline based on keyword matching."""
    lower = headline.lower()
    pos = sum(1 for kw in _POSITIVE if kw in lower)
    neg = sum(1 for kw in _NEGATIVE if kw in lower)
    if pos > neg:
        return 1
    if neg > pos:
        return -1
    return 0


def _fetch_headlines(player_name: str) -> list[str]:
    """Fetch the latest news headlines for a player from Google News RSS.

    Args:
        player_name: Full player name (e.g. "Carlos Alcaraz").

    Returns:
        List of headline strings (may be empty on failure).
    """
    query = quote_plus(f"{player_name} tennis")
    url = _NEWS_RSS_URL.format(query=query)
    try:
        resp = requests.get(url, timeout=_TIMEOUT, headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        titles = [item.findtext("title") or "" for item in root.iter("item")]
        headlines = [t for t in titles if t][:_MAX_HEADLINES]
        logger.debug("Sentiment: %d headlines for %r", len(headlines), player_name)
        return headlines
    except Exception as exc:
        logger.warning("Sentiment: failed to fetch headlines for %r: %s", player_name, exc)
        return []


def get_player_sentiment(player_name: str) -> dict:
    """Score recent news sentiment for a single player.

    Args:
        player_name: Full player name.

    Returns:
        A dict with:
            - ``available`` (bool): False if news could not be fetched.
            - ``flag`` (str): ``"positive"``, ``"concern"``, or ``"neutral"``.
            - ``label`` (str | None): Human-readable label, or None if neutral.
            - ``headline`` (str | None): The most signal-carrying headline, or None.
    """
    _neutral = {"available": False, "flag": "neutral", "label": None, "headline": None}

    headlines = _fetch_headlines(player_name)
    if not headlines:
        return _neutral

    scores = [_score_headline(h) for h in headlines]
    net = sum(scores)

    # Find the most signal-carrying headline (highest absolute score)
    scored_pairs = sorted(zip(scores, headlines), key=lambda x: abs(x[0]), reverse=True)
    top_headline = scored_pairs[0][1] if scored_pairs[0][0] != 0 else None

    if net >= _POSITIVE_THRESHOLD:
        return {
            "available": True,
            "flag": "positive",
            "label": "In form",
            "headline": top_headline,
        }
    if net <= _CONCERN_THRESHOLD:
        return {
            "available": True,
            "flag": "concern",
            "label": "Form concern",
            "headline": top_headline,
        }
    return {"available": True, "flag": "neutral", "label": None, "headline": top_headline}


def fetch_sentiment_batch(player_names: list[str]) -> dict[str, dict]:
    """Fetch sentiment for multiple players in parallel.

    Args:
        player_names: List of unique player name strings.

    Returns:
        Dict mapping player name → sentiment dict (from get_player_sentiment).
    """
    results: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=min(_MAX_WORKERS, len(player_names))) as executor:
        future_to_name = {
            executor.submit(get_player_sentiment, name): name
            for name in player_names
        }
        for future in as_completed(future_to_name):
            name = future_to_name[future]
            try:
                results[name] = future.result()
            except Exception as exc:
                logger.warning("Sentiment: unhandled error for %r: %s", name, exc)
                results[name] = {"available": False, "flag": "neutral", "label": None, "headline": None}

    flags = [v["flag"] for v in results.values()]
    logger.info(
        "Sentiment batch complete — %d players: %d positive, %d concern, %d neutral.",
        len(player_names),
        flags.count("positive"),
        flags.count("concern"),
        flags.count("neutral"),
    )
    return results
