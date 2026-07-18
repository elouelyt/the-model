"""Parlay selection and Gemini rating agent.

Algorithm:
1. Filter picks: model_prob > 0.60 AND raw_implied > 0.60
2. Confidence score = (model_prob + raw_implied) / 2
3. Generate all 2–5 pick combinations (one pick per match only)
4. Keep combinations whose total bookmaker odds fall between 1.65 and 1.85
5. Sort by accumulated model_prob (product), take top 5
6. Call Gemini Flash once per parlay to get rating (1–10), summary, risk
7. Return top 5 sorted by Gemini rating descending
"""

import json
import logging
import math
import os
import re
from itertools import combinations

logger = logging.getLogger(__name__)

_MIN_ODDS        = 1.65
_MAX_ODDS        = 1.85
_TOP_N           = 5
_MIN_STAKE_PRICE = 1.17   # exclude legs with Stake odds below this threshold


# ── Pick extraction ────────────────────────────────────────────────────────────

def extract_eligible_picks(results: list[dict]) -> list[dict]:
    """Return one enriched pick dict per qualifying player across all matches."""
    picks: list[dict] = []
    for match in results:
        if "error" in match or not match.get("players"):
            continue
        players_in_match = {q["player"]: q.get("rank") for q in match["players"]}
        for p in match["players"]:
            if p["model_prob"] <= 0.60 or p["raw_implied"] <= 0.60:
                continue
            bk = p.get("bookmakers", [])
            if bk:
                best_bk = max(bk, key=lambda b: b["price"])
                best_price = best_bk["price"]
                best_bookmaker = best_bk.get("bookmaker_title", "")
            else:
                best_price = round(1.0 / p["raw_implied"], 4)
                best_bookmaker = ""
            opponent = match["away"] if p["player"] == match["home"] else match["home"]
            picks.append({
                "player":          p["player"],
                "rank":            p["rank"],
                "points":          p["points"],
                "model_prob":      p["model_prob"],
                "raw_implied":     p["raw_implied"],
                "edge":            p["edge"],
                "signal":          p["signal"],
                "surface":         match.get("surface", "hard"),
                "h2h":             match.get("h2h", {}),
                "sentiment":       p.get("sentiment", {}),
                "best_price":      best_price,
                "best_bookmaker":  best_bookmaker,
                "stake_price":     p.get("stake_price"),
                "confidence":      round((p["model_prob"] + p["raw_implied"]) / 2, 4),
                "match_id":        f"{match['home']}|{match['away']}",
                "opponent":        opponent,
                "opponent_rank":   players_in_match.get(opponent),
                "sport_title":     match.get("sport_title", ""),
            })
    return picks


# ── Combination generation ─────────────────────────────────────────────────────

def build_parlays(picks: list[dict]) -> list[dict]:
    """Generate all valid 2–5 pick combos, filter by total odds, rank by cum_prob."""
    candidates: list[dict] = []

    for size in range(2, 6):
        if size > len(picks):
            break
        for combo in combinations(picks, size):
            # No two picks from the same match
            match_ids = [p["match_id"] for p in combo]
            if len(set(match_ids)) < len(match_ids):
                continue

            # Skip combos where any leg has a Stake price below the minimum
            if any(
                p["stake_price"] is not None and p["stake_price"] < _MIN_STAKE_PRICE
                for p in combo
            ):
                continue

            total_odds = math.prod(p["best_price"] for p in combo)
            if not (_MIN_ODDS <= total_odds <= _MAX_ODDS):
                continue

            cum_prob = math.prod(p["model_prob"] for p in combo)

            # Stake combined odds — only set when every pick has a Stake price
            stake_prices = [p["stake_price"] for p in combo]
            stake_total_odds = (
                round(math.prod(stake_prices), 3)
                if all(sp is not None for sp in stake_prices)
                else None
            )

            candidates.append({
                "picks":            list(combo),
                "total_odds":       round(total_odds, 3),
                "stake_total_odds": stake_total_odds,
                "cum_prob":         round(cum_prob, 4),
                "size":             size,
            })

    # Best cumulative probability first → top 5 go to Gemini
    candidates.sort(key=lambda x: x["cum_prob"], reverse=True)
    return candidates[:_TOP_N]


# ── Gemini rating ──────────────────────────────────────────────────────────────

_SURFACE_LABELS = {
    "clay": "clay", "grass": "grass",
    "hard": "hard", "indoor_hard": "indoor hard",
}

_SENTIMENT_MAP = {
    "positive": "positive/in form",
    "concern": "concern/out of form",
}


def _pick_summary(p: dict) -> str:
    sent = p.get("sentiment", {})
    sent_label = _SENTIMENT_MAP.get(sent.get("flag", ""), "neutral")
    h2h = p.get("h2h", {})
    h2h_str = "no previous meetings"
    if h2h.get("available") and h2h.get("total", 0) > 0:
        h2h_str = f"{h2h['total']} meetings"

    return (
        f"{p['player']} (Rank #{p['rank']}, {p['points']:,} pts, "
        f"{_SURFACE_LABELS.get(p['surface'], p['surface'])}, "
        f"model {p['model_prob']:.1%}, mkt {p['raw_implied']:.1%}, "
        f"edge {p['edge']:+.1%}, sentiment: {sent_label}, H2H: {h2h_str})"
    )


_PARLAY_PROMPT = """\
You are a tennis betting analyst rating a potential parlay combination.

Parlay ({size} picks, total odds {total_odds:.2f}, cumulative model prob {cum_prob:.1%}):
{picks_text}

Rate this parlay as a combined bet. Consider: independence of outcomes, \
surface consistency, form signals, H2H edges, and overall risk.

Return strictly valid JSON only — no markdown fences, no extra keys:
{{"rating": <integer 1-10>, "summary": "<max 2 sentences>", "risk": "<low|medium|high>"}}"""


def rate_parlay_with_gemini(parlay: dict) -> dict:
    """Call Gemini Flash to rate one parlay. Returns parlay dict with rating fields added.

    Falls back to neutral defaults if GEMINI_API_KEY is missing or call fails.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {**parlay, "rating": 5, "summary": "Gemini rating unavailable.", "risk": "medium"}

    picks_text = "\n".join(f"  - {_pick_summary(p)}" for p in parlay["picks"])
    prompt = _PARLAY_PROMPT.format(
        size=parlay["size"],
        total_odds=parlay["total_odds"],
        cum_prob=parlay["cum_prob"],
        picks_text=picks_text,
    )

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.3,
                max_output_tokens=200,
                thinking_config=types.ThinkingConfig(thinking_budget=0),
            ),
        )
        raw = response.text or ""
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)
        data = json.loads(raw)

        rating  = max(1, min(10, int(data.get("rating", 5))))
        summary = str(data.get("summary", "")).strip() or "No summary available."
        risk    = data.get("risk", "medium").lower()
        if risk not in ("low", "medium", "high"):
            risk = "medium"

        logger.info(
            "[parlay_agent] Rated parlay %s: rating=%d, risk=%s",
            " + ".join(p["player"].split()[-1] for p in parlay["picks"]),
            rating, risk,
        )
        return {**parlay, "rating": rating, "summary": summary, "risk": risk}

    except Exception as exc:  # noqa: BLE001
        logger.warning("[parlay_agent] Gemini rating failed: %s", exc)
        return {**parlay, "rating": 5, "summary": "Rating unavailable.", "risk": "medium"}


# ── Public interface ───────────────────────────────────────────────────────────

def generate_parlays(results: list[dict]) -> list[dict]:
    """Full pipeline: extract picks → build combos → rate with Gemini → sort by rating.

    Args:
        results: List of match result dicts from compute_predictions_node.

    Returns:
        Up to 5 rated parlay dicts, sorted by Gemini rating descending.
        Empty list if fewer than 2 eligible picks or no combos in odds range.
    """
    picks = extract_eligible_picks(results)
    logger.info("[parlay_agent] %d eligible picks (model>60%% & mkt>60%%)", len(picks))

    if len(picks) < 2:
        logger.info("[parlay_agent] Not enough picks for parlays")
        return []

    top_parlays = build_parlays(picks)
    logger.info("[parlay_agent] %d parlays in odds range [%.2f, %.2f]",
                len(top_parlays), _MIN_ODDS, _MAX_ODDS)

    if not top_parlays:
        return []

    rated = [rate_parlay_with_gemini(p) for p in top_parlays]
    rated.sort(key=lambda x: x["rating"], reverse=True)
    return rated
