"""Ranking agent that fetches live ATP rankings by scraping the official ATP website."""

import difflib
import logging
import re
from pathlib import Path

import cloudscraper
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parents[2] / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s — %(levelname)s — %(message)s")
logger = logging.getLogger(__name__)

_ATP_RANKINGS_URL = "https://www.atptour.com/en/rankings/singles"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.google.com/",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "cross-site",
    "Sec-Fetch-User": "?1",
}


def fetch_atp_rankings(player_names: list[str]) -> dict[str, dict]:
    """Fetch current ATP rankings for a list of players by scraping the ATP website.

    Scrapes the official ATP singles rankings page, extracts rank and points for
    all listed players, then fuzzy-matches the scraped names back to the exact
    player name strings returned by The-Odds-API.

    Args:
        player_names: List of player name strings exactly as returned by The-Odds-API
            (e.g. ["Jannik Sinner", "Carlos Alcaraz"]).

    Returns:
        A dict mapping player name (str) to a dict with ``rank`` (int) and
        ``points`` (int).
        Example: {"Jannik Sinner": {"rank": 2, "points": 12400}, ...}

    Raises:
        ValueError: If player_names is empty or the ATP page cannot be parsed.
        requests.RequestException: If the ATP website is unreachable.
    """
    if not player_names:
        raise ValueError("player_names must not be empty.")

    logger.info("Fetching live ATP rankings from atptour.com for %d players.", len(player_names))
    atp_rankings = _scrape_atp_rankings()
    logger.info("Scraped %d players from ATP rankings page.", len(atp_rankings))

    result: dict[str, dict] = {}
    atp_names = list(atp_rankings.keys())

    for odds_name in player_names:
        matched = _match_name(odds_name, atp_names)
        if matched:
            result[odds_name] = atp_rankings[matched]
        else:
            logger.warning("No ATP ranking match found for: %r", odds_name)

    logger.info("Matched rankings for %d/%d players.", len(result), len(player_names))
    return result


def _scrape_atp_rankings() -> dict[str, dict]:
    """Scrape the ATP singles rankings page and return a full rankings dict.

    Extracts player full names (from the profile link slug), rank, and points
    for all players on the page.

    Returns:
        A dict mapping full player name (str) to ``{"rank": int, "points": int}``.

    Raises:
        ValueError: If no rankings rows could be parsed from the page.
        requests.RequestException: If the HTTP request fails.
    """
    scraper = cloudscraper.create_scraper()
    response = scraper.get(_ATP_RANKINGS_URL, headers=_HEADERS, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    rows = soup.select("table tbody tr")

    if not rows:
        raise ValueError("Could not find rankings table on ATP website.")

    rankings: dict[str, dict] = {}
    rank_counter = 0

    for row in rows:
        cells = row.select("td")
        if len(cells) < 3:
            continue

        # Extract rank from first cell — strip any movement indicator (e.g. "+1", "-2")
        rank_text = re.sub(r"[^\d]", "", cells[0].get_text(strip=True))
        if not rank_text:
            rank_counter += 1
            rank = rank_counter
        else:
            rank = int(rank_text)
            rank_counter = rank

        # Extract full name from the player profile link slug
        # href format: /en/players/carlos-alcaraz/a0e2/overview
        player_link = row.select_one('a[href*="/en/players/"]')
        if not player_link:
            continue
        href = player_link.get("href", "")
        slug_match = re.search(r"/en/players/([^/]+)/", href)
        if not slug_match:
            continue
        full_name = slug_match.group(1).replace("-", " ").title()

        # Extract points — last link text in the row (rankings-breakdown link)
        points_text = re.sub(r"[^\d]", "", cells[2].get_text(strip=True))
        if not points_text:
            continue
        points = int(points_text)

        # Only store first occurrence — breakdown rows later in the table
        # overwrite the total ranking points with tournament-specific points.
        if full_name not in rankings:
            rankings[full_name] = {"rank": rank, "points": points}

    if not rankings:
        raise ValueError("Could not parse any rankings from ATP website.")

    return rankings


def _match_name(odds_name: str, atp_names: list[str]) -> str | None:
    """Fuzzy-match an odds API player name to the closest ATP website name.

    Uses difflib sequence matching on lowercased names. Requires a minimum
    similarity of 0.6 to avoid false positives.

    Args:
        odds_name: Player name string from The-Odds-API.
        atp_names: List of full player names scraped from the ATP website.

    Returns:
        The best-matching ATP name string, or None if no match meets the threshold.
    """
    odds_lower = odds_name.lower()
    atp_lower = {n.lower(): n for n in atp_names}

    # Exact match first
    if odds_lower in atp_lower:
        return atp_lower[odds_lower]

    # Fuzzy match
    matches = difflib.get_close_matches(odds_lower, list(atp_lower.keys()), n=1, cutoff=0.6)
    if matches:
        return atp_lower[matches[0]]

    return None


if __name__ == "__main__":
    test_players = [
        "Carlos Alcaraz", "Jannik Sinner",
        "Alexander Zverev", "Casper Ruud",
        "Felix Auger-Aliassime", "Tomas Machac",
    ]
    rankings = fetch_atp_rankings(player_names=test_players)
    print(f"\nRankings for {len(rankings)} players:")
    for name, data in sorted(rankings.items(), key=lambda x: x[1]["rank"]):
        print(f"  {data['rank']:>3}. {name:<30} {data['points']:>6} pts")
