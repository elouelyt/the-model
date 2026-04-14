"""H2H agent — computes head-to-head records from the Sackmann ATP dataset.

Downloads the last N years of ATP match results from the public JeffSackmann/tennis_atp
GitHub repository and computes H2H win counts for any two players, overall and by surface.

Data is downloaded once per process and cached in-memory for the full pipeline run.
Retirements, walkovers, and defaults are excluded from H2H counts.
"""

import difflib
import io
import logging
from functools import lru_cache

import pandas as pd
import requests

logger = logging.getLogger(__name__)

_SACKMANN_BASE = (
    "https://raw.githubusercontent.com/JeffSackmann/tennis_atp/master/atp_matches_{year}.csv"
)
_YEARS = [2021, 2022, 2023, 2024, 2025]
_TIMEOUT = 15

# Sackmann surface values → our canonical surface strings
_SURFACE_NORM: dict[str, str] = {
    "Clay":    "clay",
    "Grass":   "grass",
    "Hard":    "hard",
    "Carpet":  "indoor_hard",
}

# Score patterns that indicate an incomplete match
_INCOMPLETE_SCORE_PATTERNS = ["RET", "W/O", "DEF", "walkover", "In Progress", "ABD"]


@lru_cache(maxsize=1)
def _load_matches() -> pd.DataFrame:
    """Download and cache Sackmann match CSVs for the configured years.

    Returns:
        Combined DataFrame with columns: winner_name, loser_name, surface, score.
        Empty DataFrame if no data could be loaded.
    """
    frames: list[pd.DataFrame] = []
    cols = ["winner_name", "loser_name", "surface", "score", "tourney_date"]

    for year in _YEARS:
        url = _SACKMANN_BASE.format(year=year)
        try:
            resp = requests.get(url, timeout=_TIMEOUT)
            resp.raise_for_status()
            df = pd.read_csv(io.StringIO(resp.text), usecols=cols, dtype=str)
            df["year"] = year
            frames.append(df)
            logger.info("H2H: loaded %d matches from %d.", len(df), year)
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                logger.info("H2H: no data for %d yet (404).", year)
            else:
                logger.warning("H2H: HTTP error loading %d: %s", year, exc)
        except Exception as exc:
            logger.warning("H2H: could not load %d: %s", year, exc)

    if not frames:
        logger.warning("H2H: no Sackmann data loaded — H2H stats will be unavailable.")
        return pd.DataFrame(columns=cols)

    combined = pd.concat(frames, ignore_index=True)

    # Drop incomplete matches (retirements, walkovers, defaults)
    pattern = "|".join(_INCOMPLETE_SCORE_PATTERNS)
    complete = combined[~combined["score"].str.contains(pattern, na=False, case=False)]
    dropped = len(combined) - len(complete)
    if dropped:
        logger.info("H2H: dropped %d incomplete matches (RET/W/O/DEF).", dropped)

    # Normalise surface to canonical strings
    complete = complete.copy()
    complete["surface"] = complete["surface"].map(_SURFACE_NORM).fillna("hard")

    return complete.reset_index(drop=True)


def _match_name(player_name: str, candidate_names: list[str]) -> str | None:
    """Fuzzy-match a player name from the odds API to a Sackmann dataset name.

    Uses exact match first, then difflib sequence matching with a high cutoff
    (0.82) to avoid false positives — a wrong H2H match is worse than no data.

    Args:
        player_name: Name string from The-Odds-API.
        candidate_names: All unique names present in the Sackmann dataset.

    Returns:
        The best-matching Sackmann name, or None if no match meets the threshold.
    """
    lower = player_name.lower()
    candidates_lower = {n.lower(): n for n in candidate_names}

    if lower in candidates_lower:
        return candidates_lower[lower]

    matches = difflib.get_close_matches(lower, list(candidates_lower.keys()), n=1, cutoff=0.82)
    if matches:
        matched = candidates_lower[matches[0]]
        logger.debug("H2H name fuzzy-match: %r → %r", player_name, matched)
        return matched

    return None


def get_h2h(player_a: str, player_b: str, surface: str) -> dict:
    """Return H2H stats between two players from the Sackmann dataset.

    Args:
        player_a: Home player name (The-Odds-API format).
        player_b: Away player name (The-Odds-API format).
        surface: Court surface ("clay", "grass", "hard", "indoor_hard").

    Returns:
        A dict with the following keys:
            - ``available`` (bool): False if data is missing or names unmatched.
            - ``a_wins`` (int): player_a overall wins in H2H.
            - ``b_wins`` (int): player_b overall wins in H2H.
            - ``total`` (int): total completed H2H matches.
            - ``a_wins_surface`` (int): player_a wins on this surface.
            - ``b_wins_surface`` (int): player_b wins on this surface.
            - ``total_surface`` (int): H2H matches on this surface.
            - ``leader`` (str | None): "a", "b", or None if equal / no data.
            - ``leader_surface`` (str | None): "a", "b", or None if equal / no data.
    """
    _empty = {
        "available": False,
        "a_wins": 0, "b_wins": 0, "total": 0,
        "a_wins_surface": 0, "b_wins_surface": 0, "total_surface": 0,
        "leader": None, "leader_surface": None,
    }

    df = _load_matches()
    if df.empty:
        return _empty

    all_names: list[str] = list(
        set(df["winner_name"].dropna().tolist()) |
        set(df["loser_name"].dropna().tolist())
    )

    name_a = _match_name(player_a, all_names)
    name_b = _match_name(player_b, all_names)

    if not name_a or not name_b:
        logger.warning(
            "H2H: could not match one or both players — a=%r→%r  b=%r→%r",
            player_a, name_a, player_b, name_b,
        )
        return _empty

    # Matches between the two players in either direction
    mask = (
        ((df["winner_name"] == name_a) & (df["loser_name"] == name_b)) |
        ((df["winner_name"] == name_b) & (df["loser_name"] == name_a))
    )
    h2h = df[mask]

    a_wins = int((h2h["winner_name"] == name_a).sum())
    b_wins = int((h2h["winner_name"] == name_b).sum())
    total = a_wins + b_wins

    h2h_surf = h2h[h2h["surface"] == surface]
    a_wins_s = int((h2h_surf["winner_name"] == name_a).sum())
    b_wins_s = int((h2h_surf["winner_name"] == name_b).sum())
    total_s = a_wins_s + b_wins_s

    return {
        "available": True,
        "a_wins": a_wins,
        "b_wins": b_wins,
        "total": total,
        "a_wins_surface": a_wins_s,
        "b_wins_surface": b_wins_s,
        "total_surface": total_s,
        "leader":         "a" if a_wins > b_wins else ("b" if b_wins > a_wins else None),
        "leader_surface": "a" if a_wins_s > b_wins_s else ("b" if b_wins_s > a_wins_s else None),
    }
