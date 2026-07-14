"""LangGraph coordinator for the Tennis AI prediction pipeline.

Replaces the linear ``run_pipeline()`` function with a stateful graph that
supports retry logic and conditional routing:

    fetch_odds → fetch_rankings → fetch_sentiment → compute_predictions
                      ↑ retry ×2                         ↓
                                              generate_explanations → END
    fetch_odds → (empty) → END

Each node receives and returns the shared ``PipelineState`` TypedDict.
Errors are captured as non-fatal fallbacks so the page always renders
with whatever data is available.
"""

import logging
from typing import Annotated, TypedDict

from langgraph.graph import StateGraph, END

logger = logging.getLogger(__name__)

# ── State schema ───────────────────────────────────────────────────────────────


class PipelineState(TypedDict, total=False):
    """Shared state passed between all nodes in the pipeline graph."""

    # Raw odds fetched from The-Odds-API
    raw_odds: list[dict]

    # Flat DataFrame-compatible rows after transform (stored as list of dicts
    # because TypedDict cannot hold a pandas DataFrame directly)
    processed_rows: list[dict]

    # Ranking lookup: player_name → {"rank": int, "points": int}
    rankings: dict[str, dict]

    # Sentiment lookup: player_name → sentinel dict
    sentiment_map: dict[str, dict]

    # Final match result dicts (what generate_html.py consumes)
    results: list[dict]

    # Top-5 rated parlays (populated by generate_parlays_node)
    parlays: list[dict]

    # Top-5 safe parlays for daily compounder (populated by generate_safe_parlays_node)
    safe_parlays: list[dict]

    # Stake odds: player_name → decimal_price (populated by fetch_stake_odds_node)
    stake_odds: dict[str, float]

    # Retry counter for the rankings node
    rankings_retries: int

    # Signals that downstream nodes should not run
    abort: bool


# ── Nodes ──────────────────────────────────────────────────────────────────────


def fetch_odds_node(state: PipelineState) -> PipelineState:
    """Fetch live pre-match ATP odds with two-tier fallback.

    Priority:
      1. The-Odds-API  — Grand Slams + Masters (accurate bookmaker odds)
      2. Stake odds-data API — ALL ATP tournaments including 250s (Gstaad, Bastad, Umag…)
    """
    from src.ingestion.extract_odds import fetch_odds
    from src.processing.transform import flatten_odds, filter_upcoming

    logger.info("[coordinator] fetch_odds_node — tier 1: The-Odds-API")
    raw: list[dict] = []
    source = "the-odds-api"

    try:
        raw = fetch_odds()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[coordinator] The-Odds-API failed: %s", exc)

    if not raw:
        logger.info("[coordinator] tier 2: Stake odds-data fallback (covers ATP 250s)")
        source = "stake"
        try:
            from src.agents.stake_agent import fetch_all_stake_matches
            raw = fetch_all_stake_matches()
        except Exception as exc:  # noqa: BLE001
            logger.error("[coordinator] Stake fallback failed: %s", exc)

    if not raw:
        logger.warning("[coordinator] All odds sources empty — aborting")
        return {**state, "raw_odds": [], "processed_rows": [], "abort": True}

    df = filter_upcoming(flatten_odds(raw))

    if df.empty:
        logger.warning("[coordinator] All matches in-play (source=%s) — aborting", source)
        return {**state, "raw_odds": raw, "processed_rows": [], "abort": True}

    logger.info("[coordinator] %d pre-match rows ready (source=%s)", len(df), source)
    return {**state, "raw_odds": raw, "processed_rows": df.to_dict("records"), "abort": False}


def fetch_rankings_node(state: PipelineState) -> PipelineState:
    """Scrape ATP rankings with up to 2 retries on failure."""
    from src.agents.ranking_agent import fetch_atp_rankings
    import pandas as pd

    rows = state.get("processed_rows", [])
    retries = state.get("rankings_retries", 0)

    players = list({r["outcome_name"] for r in rows})
    logger.info("[coordinator] fetch_rankings_node — %d players (attempt %d)", len(players), retries + 1)

    try:
        rankings = fetch_atp_rankings(player_names=players)
        if not rankings:
            raise ValueError("Empty rankings returned")
        logger.info("[coordinator] Rankings fetched for %d players", len(rankings))
        return {**state, "rankings": rankings, "rankings_retries": retries + 1}
    except Exception as exc:  # noqa: BLE001
        logger.warning("[coordinator] Rankings fetch failed (attempt %d): %s", retries + 1, exc)
        return {**state, "rankings": {}, "rankings_retries": retries + 1}


def fetch_sentiment_node(state: PipelineState) -> PipelineState:
    """Fetch news sentiment for all players. Non-fatal — defaults to neutral."""
    from src.agents.sentiment_agent import fetch_sentiment_batch

    rows = state.get("processed_rows", [])
    players = list({r["outcome_name"] for r in rows})
    logger.info("[coordinator] fetch_sentiment_node — %d players", len(players))

    try:
        sentiment_map = fetch_sentiment_batch(players)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[coordinator] Sentiment fetch failed (non-fatal): %s", exc)
        sentiment_map = {}

    return {**state, "sentiment_map": sentiment_map}


def fetch_stake_odds_node(state: PipelineState) -> PipelineState:
    """Fetch pre-match Stake odds for all players in the current pipeline run.

    Tries the live Stake API first. If it returns nothing (Cloudflare blocks
    GitHub Actions), falls back to data/stake_cache.json written locally
    with VPN via scripts/stake_update.py.
    Non-fatal — empty dict if both live and cache are unavailable.
    """
    import json
    from pathlib import Path
    from src.agents.stake_agent import fetch_stake_odds

    rows = state.get("processed_rows", [])
    players = list({r["outcome_name"] for r in rows})
    logger.info("[coordinator] fetch_stake_odds_node — %d players", len(players))

    stake_odds: dict[str, float] = {}
    source = "none"

    # ── Try live API ──────────────────────────────────────────────────────────
    try:
        stake_odds = fetch_stake_odds(players)
        if stake_odds:
            source = "live"
    except Exception as exc:  # noqa: BLE001
        logger.warning("[coordinator] Stake live API failed (non-fatal): %s", exc)

    # ── Fallback: stake_cache.json ────────────────────────────────────────────
    if not stake_odds:
        cache_path = Path(__file__).parent.parent.parent / "data" / "stake_cache.json"
        if cache_path.exists():
            try:
                cached = json.loads(cache_path.read_text())
                cached_odds: dict[str, float] = cached.get("odds", {})
                stake_odds = {p: cached_odds[p] for p in players if p in cached_odds}
                if stake_odds:
                    source = f"cache ({cached.get('timestamp', '?')[:10]})"
                    logger.info(
                        "[coordinator] Stake live returned 0 — using cache from %s: %d / %d players matched",
                        cached.get("timestamp", "?"), len(stake_odds), len(players),
                    )
                else:
                    logger.info(
                        "[coordinator] Cache exists (%s) but 0 current players matched",
                        cached.get("timestamp", "?"),
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning("[coordinator] Failed to load stake_cache.json: %s", exc)
        else:
            logger.info("[coordinator] No stake_cache.json found — run scripts/stake_update.py with VPN")

    logger.info(
        "[coordinator] Stake odds source=%s, %d / %d players",
        source, len(stake_odds), len(players),
    )
    return {**state, "stake_odds": stake_odds}


def compute_predictions_node(state: PipelineState) -> PipelineState:
    """Assemble final match predictions from all upstream data."""
    import pandas as pd
    from src.agents.probability_calculator import compare_with_bookmaker
    from src.agents.model_agent import predict_win_probability
    from src.agents.surface_agent import get_surface, SURFACE_NOTE
    from src.agents.h2h_agent import get_h2h

    rows = state.get("processed_rows", [])
    rankings = state.get("rankings", {})
    sentiment_map = state.get("sentiment_map", {})
    stake_odds = state.get("stake_odds", {})

    if not rows:
        return {**state, "results": []}

    df = pd.DataFrame(rows)
    results: list[dict] = []

    for (event_id, home, away), group in df.groupby(["event_id", "home_team", "away_team"]):
        commence_time = group["commence_time"].iloc[0]
        sport_key = group["sport_key"].iloc[0]
        surface = get_surface(sport_key)
        surface_note = SURFACE_NOTE.get(surface)

        missing = [p for p in [home, away] if p not in rankings]
        if missing:
            results.append({
                "home": home,
                "away": away,
                "commence_time": commence_time,
                "surface": surface,
                "error": f"Rankings not found for: {', '.join(missing)}",
            })
            continue

        prob_home, prob_away = predict_win_probability(
            rankings[home]["points"], rankings[away]["points"],
            rankings[home]["rank"],   rankings[away]["rank"],
            surface,
        )

        players_data = []
        for player, model_prob in [(home, prob_home), (away, prob_away)]:
            player_rows = group[group["outcome_name"] == player]
            rec = compare_with_bookmaker(
                model_prob,
                player_rows["raw_implied"].mean(),
                player_rows["true_implied"].mean(),
                player,
            )
            rec["rank"] = rankings[player]["rank"]
            rec["points"] = rankings[player]["points"]
            rec["sentiment"] = sentiment_map.get(
                player, {"available": False, "flag": "neutral", "label": None, "headline": None,
                         "withdrawn": False, "withdrawal_headline": None}
            )
            bk = (
                player_rows[["bookmaker_title", "price", "raw_implied"]]
                .drop_duplicates(subset=["bookmaker_title"])
                .sort_values("price", ascending=False)
            )
            bookmakers_list = bk.to_dict("records")

            # Inject Stake odds if available — prepend so it sorts first if best price
            stake_price = stake_odds.get(player)
            if stake_price:
                stake_entry = {
                    "bookmaker_title": "Stake",
                    "price": round(stake_price, 3),
                    "raw_implied": round(1.0 / stake_price, 4),
                }
                bookmakers_list = [stake_entry] + [
                    b for b in bookmakers_list if b["bookmaker_title"] != "Stake"
                ]
                rec["stake_price"] = round(stake_price, 3)

            rec["bookmakers"] = bookmakers_list
            if surface_note:
                rec["recommendation"] = rec["recommendation"] + f" · {surface_note}"
            players_data.append(rec)

        h2h = get_h2h(home, away, surface)

        # Detect withdrawal alert from sentiment signals
        withdrawal_alert = None
        for pd_rec in players_data:
            sent = pd_rec.get("sentiment", {})
            if sent.get("withdrawn"):
                withdrawal_alert = {
                    "player": pd_rec["player"],
                    "headline": sent.get("withdrawal_headline"),
                }
                logger.warning(
                    "[coordinator] Withdrawal alert: %s — %s",
                    pd_rec["player"], sent.get("withdrawal_headline"),
                )
                break  # one alert per match is enough

        match_dict = {
            "home": home,
            "away": away,
            "commence_time": commence_time,
            "surface": surface,
            "h2h": h2h,
            "players": players_data,
        }
        if withdrawal_alert:
            match_dict["withdrawal_alert"] = withdrawal_alert

        results.append(match_dict)

    logger.info("[coordinator] compute_predictions_node — %d matches", len(results))
    return {**state, "results": results}


def generate_explanations_node(state: PipelineState) -> PipelineState:
    """Replace template recommendation text with Gemini Flash insights.

    Calls the explanation agent once per match (not per player). If the call
    fails for any match the original template text is kept — fully non-fatal.
    Matches with ``error`` keys (missing rankings) are skipped.
    """
    from src.agents.explanation_agent import generate_match_explanations

    results = state.get("results", [])
    if not results:
        return state

    import os
    if not os.getenv("GEMINI_API_KEY"):
        logger.info("[coordinator] GEMINI_API_KEY not set — skipping explanations node")
        return state

    updated: list[dict] = []
    for match in results:
        if "error" in match or not match.get("players"):
            updated.append(match)
            continue

        players = match["players"]
        if len(players) < 2:
            updated.append(match)
            continue

        home_p = next((p for p in players if p["player"] == match["home"]), players[0])
        away_p = next((p for p in players if p["player"] == match["away"]), players[1])

        insights = generate_match_explanations(
            home=match["home"],
            away=match["away"],
            surface=match.get("surface", "hard"),
            home_player=home_p,
            away_player=away_p,
            h2h=match.get("h2h", {}),
        )

        if insights:
            # Patch recommendation field in-place (copy to avoid mutating original)
            new_players = []
            for p in players:
                pc = dict(p)
                if pc["player"] == match["home"]:
                    pc["recommendation"] = insights["home_insight"]
                elif pc["player"] == match["away"]:
                    pc["recommendation"] = insights["away_insight"]
                new_players.append(pc)
            updated.append({**match, "players": new_players})
        else:
            updated.append(match)

    logger.info("[coordinator] generate_explanations_node — %d matches processed", len(updated))
    return {**state, "results": updated}


def generate_parlays_node(state: PipelineState) -> PipelineState:
    """Select top parlays and rate each with Gemini Flash.

    Runs after generate_explanations so recommendation text is already final.
    Non-fatal — empty list on any failure.
    """
    from src.agents.parlay_agent import generate_parlays

    results = state.get("results", [])
    try:
        parlays = generate_parlays(results)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[coordinator] generate_parlays_node failed (non-fatal): %s", exc)
        parlays = []

    logger.info("[coordinator] generate_parlays_node — %d parlays rated", len(parlays))
    return {**state, "parlays": parlays}


def generate_safe_parlays_node(state: PipelineState) -> PipelineState:
    """Select top safe parlays for the daily compounder strategy and rate with Gemini.

    Independent from generate_parlays_node — uses mkt>65% only filter, no odds
    range constraint, 2-6 legs. Non-fatal — empty list on any failure.
    """
    from src.agents.safe_parlay_agent import generate_safe_parlays

    results = state.get("results", [])
    try:
        safe_parlays = generate_safe_parlays(results)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[coordinator] generate_safe_parlays_node failed (non-fatal): %s", exc)
        safe_parlays = []

    logger.info("[coordinator] generate_safe_parlays_node — %d safe parlays rated", len(safe_parlays))
    return {**state, "safe_parlays": safe_parlays}


# ── Conditional routing ────────────────────────────────────────────────────────


def _should_abort(state: PipelineState) -> str:
    """Route to END if no odds data; otherwise continue to rankings."""
    return END if state.get("abort") else "fetch_rankings"


def _retry_or_continue(state: PipelineState) -> str:
    """Retry rankings up to 2 times; then proceed regardless (fallback to no-ranking cards)."""
    retries = state.get("rankings_retries", 0)
    rankings = state.get("rankings", {})

    if not rankings and retries < 2:
        logger.info("[coordinator] Rankings empty — retrying (attempt %d/2)", retries + 1)
        return "fetch_rankings"

    if not rankings:
        logger.warning("[coordinator] Rankings unavailable after %d attempts — all matches will show error cards", retries)

    return "fetch_sentiment"


# ── Graph construction ─────────────────────────────────────────────────────────


def _build_graph() -> StateGraph:
    graph = StateGraph(PipelineState)

    graph.add_node("fetch_odds", fetch_odds_node)
    graph.add_node("fetch_rankings", fetch_rankings_node)
    graph.add_node("fetch_sentiment", fetch_sentiment_node)
    graph.add_node("fetch_stake_odds", fetch_stake_odds_node)
    graph.add_node("compute_predictions", compute_predictions_node)
    graph.add_node("generate_explanations", generate_explanations_node)
    graph.add_node("generate_parlays", generate_parlays_node)
    graph.add_node("generate_safe_parlays", generate_safe_parlays_node)

    graph.set_entry_point("fetch_odds")

    # After fetch_odds: abort if no data, else go to rankings
    graph.add_conditional_edges("fetch_odds", _should_abort, {"fetch_rankings": "fetch_rankings", END: END})

    # After fetch_rankings: retry up to 2× or proceed
    graph.add_conditional_edges(
        "fetch_rankings",
        _retry_or_continue,
        {"fetch_rankings": "fetch_rankings", "fetch_sentiment": "fetch_sentiment"},
    )

    graph.add_edge("fetch_sentiment", "fetch_stake_odds")
    graph.add_edge("fetch_stake_odds", "compute_predictions")
    graph.add_edge("compute_predictions", "generate_explanations")
    graph.add_edge("generate_explanations", "generate_parlays")
    graph.add_edge("generate_parlays", "generate_safe_parlays")
    graph.add_edge("generate_safe_parlays", END)

    return graph


_GRAPH = _build_graph().compile()


# ── Public interface ───────────────────────────────────────────────────────────


def run_pipeline() -> list[dict]:
    """Execute the LangGraph prediction pipeline and return match result dicts.

    This is a drop-in replacement for the former linear ``run_pipeline()``
    in ``generate_html.py``.

    Returns:
        A list of match result dicts (same schema as before).
        Empty list if no active tournaments or all matches are in-play.
    """
    logger.info("[coordinator] Starting LangGraph pipeline")
    initial_state: PipelineState = {
        "raw_odds": [],
        "processed_rows": [],
        "rankings": {},
        "sentiment_map": {},
        "stake_odds": {},
        "results": [],
        "rankings_retries": 0,
        "abort": False,
    }

    final_state = _GRAPH.invoke(initial_state)
    results = final_state.get("results", [])
    parlays = final_state.get("parlays", [])
    safe_parlays = final_state.get("safe_parlays", [])
    logger.info(
        "[coordinator] Pipeline complete — %d matches, %d parlays, %d safe parlays",
        len(results), len(parlays), len(safe_parlays),
    )
    return results, parlays, safe_parlays
