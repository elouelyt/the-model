"""Safe Parlay / Daily Compounder agent.

Independent algorithm from parlay_agent.py — optimises for maximum probability
of winning, not for value. Designed for progressive reinvestment strategies
where each day's winnings are staked on the next combination.

Algorithm:
1. Eligible picks: raw_implied (bookmaker) > 65% — only high-confidence market picks
2. Generate all combinations of 2–6 picks (one pick per match)
3. No odds filter — show whatever the odds come out to
4. Rank all combinations by cumulative model_prob (highest = safest)
5. Take top 5
6. Gemini Flash rates each (1-10) and recommends which to bet today
7. Mark the top-rated pick as today_pick=True
8. Return sorted by Gemini rating descending
"""

import json
import logging
import math
import os
import re
from itertools import combinations

logger = logging.getLogger(__name__)

_MIN_IMPLIED   = 0.65   # bookmaker implied > 65%
_MAX_COMBO     = 6      # up to 6-leg parlays
_TOP_N         = 5


# ── Pick extraction ────────────────────────────────────────────────────────────

def extract_safe_picks(results: list[dict]) -> list[dict]:
    """Return picks where bookmaker implied probability > 65%."""
    picks: list[dict] = []
    for match in results:
        if "error" in match or not match.get("players"):
            continue
        players_in_match = {q["player"]: q.get("rank") for q in match["players"]}
        for p in match["players"]:
            stake_implied = (1.0 / p["stake_price"]) if p.get("stake_price") else None
            eligible = p["raw_implied"] > _MIN_IMPLIED or (
                stake_implied is not None and stake_implied > _MIN_IMPLIED
            )
            if not eligible:
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
                "player":         p["player"],
                "rank":           p["rank"],
                "points":         p["points"],
                "model_prob":     p["model_prob"],
                "raw_implied":    p["raw_implied"],
                "edge":           p["edge"],
                "signal":         p["signal"],
                "surface":        match.get("surface", "hard"),
                "h2h":            match.get("h2h", {}),
                "sentiment":      p.get("sentiment", {}),
                "best_price":     best_price,
                "best_bookmaker": best_bookmaker,
                "stake_price":    p.get("stake_price"),
                "match_id":       f"{match['home']}|{match['away']}",
                "opponent":       opponent,
                "opponent_rank":  players_in_match.get(opponent),
            })
    return picks


# ── Combination builder ────────────────────────────────────────────────────────

def build_safe_parlays(picks: list[dict]) -> list[dict]:
    """All 2–6 combos (one per match), ranked by cumulative market implied prob, top 5."""
    candidates: list[dict] = []

    for size in range(2, min(_MAX_COMBO + 1, len(picks) + 1)):
        for combo in combinations(picks, size):
            # No two picks from the same match
            if len({p["match_id"] for p in combo}) < len(combo):
                continue

            # Skip combos where any leg has a Stake price below 1.17
            if any(
                p["stake_price"] is not None and p["stake_price"] < 1.17
                for p in combo
            ):
                continue

            total_odds = math.prod(
                p["stake_price"] if p["stake_price"] is not None else p["best_price"]
                for p in combo
            )
            cum_prob = math.prod(p["model_prob"] for p in combo)

            # Market-implied prob per pick: prefer stake_implied, fall back to raw_implied
            cum_implied = math.prod(
                (1.0 / p["stake_price"]) if p["stake_price"] is not None else p["raw_implied"]
                for p in combo
            )

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
                "cum_implied":      round(cum_implied, 4),
                "size":             size,
            })

    candidates.sort(key=lambda x: x["cum_implied"], reverse=True)
    return candidates[:_TOP_N]


# ── Gemini rating ──────────────────────────────────────────────────────────────

_SURFACE_LABELS = {
    "clay": "clay", "grass": "grass",
    "hard": "hard", "indoor_hard": "indoor hard",
}
_SENTIMENT_MAP = {
    "positive": "positive/in form",
    "concern":  "concern/out of form",
}


def _pick_summary(p: dict) -> str:
    sent = p.get("sentiment", {}) or {}
    sent_label = _SENTIMENT_MAP.get(sent.get("flag", ""), "neutral")
    h2h = p.get("h2h", {}) or {}
    h2h_str = (
        f"{h2h['total']} meetings" if h2h.get("available") and h2h.get("total", 0) > 0
        else "no previous meetings"
    )
    return (
        f"{p['player']} (Rank #{p['rank']}, {p['points']:,} pts, "
        f"{_SURFACE_LABELS.get(p['surface'], p['surface'])}, "
        f"mkt implied {p['raw_implied']:.1%}, model {p['model_prob']:.1%}, "
        f"price {p['best_price']:.2f}, sentiment: {sent_label}, H2H: {h2h_str})"
    )


_SAFE_PROMPT = """\
You are a tennis betting analyst evaluating a SAFE COMPOUNDER parlay.
This strategy prioritises maximum win probability — picks are chosen because
bookmakers give them >65% implied probability. Winnings are reinvested daily.

Parlay ({size} picks, total odds {total_odds:.2f}, cumulative model prob {cum_prob:.1%}):
{picks_text}

Evaluate this combination for a daily compounder strategy. Focus on:
probability of all legs winning, consistency across surfaces, and form.

Return strictly valid JSON only — no markdown fences, no extra keys:
{{"rating": <integer 1-10>, "summary": "<max 2 sentences>", "risk": "<low|medium|high>"}}"""


def _rate_with_gemini(parlay: dict) -> dict:
    """Rate one safe parlay with Gemini Flash. Falls back to neutral defaults."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return {**parlay, "rating": 5, "summary": "Gemini rating unavailable.", "risk": "medium"}

    picks_text = "\n".join(f"  - {_pick_summary(p)}" for p in parlay["picks"])
    prompt = _SAFE_PROMPT.format(
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

        legs = " + ".join(p["player"].split()[-1] for p in parlay["picks"])
        logger.info("[safe_parlay_agent] Rated %s: %d/10 (%s)", legs, rating, risk)
        return {**parlay, "rating": rating, "summary": summary, "risk": risk}

    except Exception as exc:  # noqa: BLE001
        logger.warning("[safe_parlay_agent] Gemini rating failed: %s", exc)
        return {**parlay, "rating": 5, "summary": "Rating unavailable.", "risk": "medium"}


# ── Public interface ───────────────────────────────────────────────────────────

def generate_safe_parlays(results: list[dict]) -> list[dict]:
    """Full pipeline: extract → combine → rate → sort by Gemini rating.

    The parlay with the highest Gemini rating receives today_pick=True.

    Returns:
        Up to 5 rated parlay dicts sorted by Gemini rating descending.
        today_pick=True marks the recommended bet for today.
        Empty list if fewer than 2 eligible picks.
    """
    picks = extract_safe_picks(results)
    logger.info("[safe_parlay_agent] %d eligible picks (mkt > 65%%)", len(picks))

    if len(picks) < 2:
        logger.info("[safe_parlay_agent] Not enough picks for safe parlays")
        return []

    top5 = build_safe_parlays(picks)
    logger.info("[safe_parlay_agent] Top %d combos by cumulative prob selected", len(top5))

    if not top5:
        return []

    rated = [_rate_with_gemini(p) for p in top5]
    rated.sort(key=lambda x: (x["rating"], x["cum_prob"]), reverse=True)

    # Mark today's top pick
    if rated:
        rated[0] = {**rated[0], "today_pick": True}
    for r in rated[1:]:
        r.setdefault("today_pick", False)

    return rated
