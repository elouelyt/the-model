"""Module for flattening raw odds JSON from The-Odds-API into a tabular DataFrame."""

import logging
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


def filter_upcoming(df: pd.DataFrame) -> pd.DataFrame:
    """Remove in-play matches, keeping only matches that have not yet started.

    The Odds API returns ALL matches including those currently in progress.
    Live odds shift dramatically with the score (e.g. a player up two sets
    gets priced at 95%), so they reflect the current match state rather than
    pre-match probability. Comparing a static ranking-based model against live
    odds is meaningless. This filter ensures only pre-match odds reach the
    prediction layer.

    Args:
        df: Transformed DataFrame produced by flatten_odds, which must contain
            a UTC-aware ``commence_time`` column.

    Returns:
        A filtered DataFrame containing only rows where ``commence_time`` is
        strictly in the future relative to the current UTC time. Logs how
        many matches were dropped.
    """
    now = datetime.now(timezone.utc)
    upcoming = df[df["commence_time"] > now]

    dropped = df["event_id"].nunique() - upcoming["event_id"].nunique()
    if dropped > 0:
        logger.info(
            "Filtered out %d in-play or completed match(es) — only pre-match odds are valid model inputs.",
            dropped,
        )

    return upcoming


def flatten_odds(data: list[dict]) -> pd.DataFrame:
    """Flatten a list of nested odds event dicts into a 14-column DataFrame.

    Each row in the output represents a single outcome (e.g. one player's
    price) for a specific market, bookmaker, and event. The nesting path is:
    event → bookmakers → markets → outcomes.

    Args:
        data: Raw list of event dicts as returned by The-Odds-API.

    Returns:
        A pandas DataFrame with the following columns:
            event_id, sport_key, sport_title, home_team, away_team,
            commence_time, bookmaker_key, bookmaker_title,
            bookmaker_last_update, market_key, market_last_update,
            outcome_name, price, ingested_at, raw_implied, true_implied.

    Raises:
        ValueError: If ``data`` is empty.
    """
    if not data:
        raise ValueError("Input data list is empty — nothing to flatten.")

    rows: list[dict] = []
    ingested_at = datetime.now(timezone.utc)

    for event in data:
        event_base = {
            "event_id": event.get("id"),
            "sport_key": event.get("sport_key"),
            "sport_title": event.get("sport_title"),
            "home_team": event.get("home_team"),
            "away_team": event.get("away_team"),
            "commence_time": event.get("commence_time"),
        }

        for bookmaker in event.get("bookmakers", []):
            bookmaker_base = {
                "bookmaker_key": bookmaker.get("key"),
                "bookmaker_title": bookmaker.get("title"),
                "bookmaker_last_update": bookmaker.get("last_update"),
            }

            for market in bookmaker.get("markets", []):
                market_base = {
                    "market_key": market.get("key"),
                    "market_last_update": market.get("last_update"),
                }

                for outcome in market.get("outcomes", []):
                    rows.append({
                        **event_base,
                        **bookmaker_base,
                        **market_base,
                        "outcome_name": outcome.get("name"),
                        "price": outcome.get("price"),
                        "ingested_at": ingested_at,
                    })

    df = pd.DataFrame(rows)

    # Cast timestamp columns to UTC-aware datetime
    for col in ("commence_time", "bookmaker_last_update", "market_last_update"):
        df[col] = pd.to_datetime(df[col], utc=True)

    # ingested_at is already a datetime object; ensure consistent dtype
    df["ingested_at"] = pd.to_datetime(df["ingested_at"], utc=True)

    # Raw implied probability: 1 / decimal_odds
    df["raw_implied"] = 1 / df["price"]

    # Vig-removed true implied probability: normalise per bookmaker per market.
    # Bookmakers build a margin (overround) into their odds so raw implieds sum
    # to >1. Dividing each raw implied by the sum for that group removes the vig
    # and produces probabilities that sum to exactly 1.0 per market.
    group_sum = df.groupby(["event_id", "bookmaker_key", "market_key"])["raw_implied"].transform("sum")
    df["true_implied"] = df["raw_implied"] / group_sum

    logger.info("Flattened %d events into %d rows.", len(data), len(df))
    return df


def save_locally(df: pd.DataFrame, output_dir: str = "data/processed") -> Path:
    """Save the transformed DataFrame as a CSV for local sandbox development.

    Avoids re-hitting the API during local development and testing of the
    prediction layer. In production, data goes directly to BigQuery instead.

    Args:
        df: Transformed DataFrame produced by flatten_odds.
        output_dir: Relative path to the local output directory.

    Returns:
        The Path of the saved CSV file.
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_path = Path(output_dir) / f"tennis_odds_processed_{timestamp}.csv"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    df.to_csv(out_path, index=False)
    logger.info("Saved %d rows to %s", len(df), out_path)
    return out_path
