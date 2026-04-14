"""Gemini Flash explanation agent — generates contextual match insights.

Replaces the static template text in ``compare_with_bookmaker`` with a
2-sentence analyst narrative per player, synthesising model edge, H2H
history, surface context, and sentiment into a human-readable insight.

One API call per match (not per player) — returns insights for both players
in a single structured JSON response.

Non-fatal: if Gemini is unavailable or the API key is missing, returns None
and the coordinator falls back to the original template recommendations.
"""

import json
import logging
import os
import re

logger = logging.getLogger(__name__)

_SURFACE_LABELS = {
    "clay": "clay", "grass": "grass",
    "hard": "hard", "indoor_hard": "indoor hard",
}

_PROMPT_TEMPLATE = """\
You are a concise tennis betting analyst. Given the pre-match data below, write \
a sharp 1–2 sentence insight for each player explaining WHY the model edge exists \
and what context supports or contradicts it. Be specific — mention H2H, surface, \
form, or ranking as relevant. No generic disclaimers. No markdown.

Match: {home} vs {away} on {surface}

{home}:
  Rank #{home_rank} | {home_pts} pts
  Model prob: {home_model:.1f}% | Market implied: {home_implied:.1f}%
  Edge: {home_edge:+.1f}%
  Sentiment: {home_sentiment}

{away}:
  Rank #{away_rank} | {away_pts} pts
  Model prob: {away_model:.1f}% | Market implied: {away_implied:.1f}%
  Edge: {away_edge:+.1f}%
  Sentiment: {away_sentiment}

Head-to-head (last 4 years): {h2h_summary}

Return strictly valid JSON — no markdown fences, no extra keys:
{{"home_insight": "...", "away_insight": "..."}}"""


def _format_h2h(h2h: dict, home: str, away: str, surface: str) -> str:
    """Convert H2H dict to a compact human-readable string for the prompt."""
    if not h2h or not h2h.get("available") or h2h.get("total", 0) == 0:
        return "No previous meetings"

    home_short = home.split()[-1]
    away_short = away.split()[-1]
    surf_label = _SURFACE_LABELS.get(surface, surface)
    overall = f"{home_short} leads {h2h['a_wins']}–{h2h['b_wins']}" if h2h.get("leader") == "a" \
        else f"{away_short} leads {h2h['b_wins']}–{h2h['a_wins']}" if h2h.get("leader") == "b" \
        else f"Tied {h2h['a_wins']}–{h2h['b_wins']}"

    surface_part = ""
    if h2h.get("total_surface", 0) > 0:
        surface_part = (
            f"; on {surf_label}: "
            f"{home_short} {h2h['a_wins_surface']}–{h2h['b_wins_surface']} {away_short}"
        )

    return f"{overall} ({h2h['total']} matches total{surface_part})"


def _sentiment_label(sentiment: dict) -> str:
    """Convert sentiment dict to a single readable word."""
    if not sentiment or not sentiment.get("available"):
        return "neutral"
    flag = sentiment.get("flag", "neutral")
    return {"positive": "positive/in form", "concern": "concern/out of form"}.get(flag, "neutral")


def generate_match_explanations(
    home: str,
    away: str,
    surface: str,
    home_player: dict,
    away_player: dict,
    h2h: dict,
) -> dict[str, str] | None:
    """Call Gemini Flash to generate contextual insights for both players.

    Args:
        home: Home player name.
        away: Away player name.
        surface: Surface key (clay/grass/hard/indoor_hard).
        home_player: Player dict from compute_predictions (has rank, points,
            model_prob, raw_implied, edge, sentiment).
        away_player: Same structure for away player.
        h2h: H2H result dict from h2h_agent.

    Returns:
        Dict with ``home_insight`` and ``away_insight`` strings, or None if
        Gemini is unavailable (coordinator falls back to template text).
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.warning("[explanation_agent] GEMINI_API_KEY not set — skipping")
        return None

    prompt = _PROMPT_TEMPLATE.format(
        home=home,
        away=away,
        surface=_SURFACE_LABELS.get(surface, surface),
        home_rank=home_player["rank"],
        home_pts=f'{home_player["points"]:,}',
        home_model=home_player["model_prob"] * 100,
        home_implied=home_player["raw_implied"] * 100,
        home_edge=home_player["edge"] * 100,
        home_sentiment=_sentiment_label(home_player.get("sentiment", {})),
        away_rank=away_player["rank"],
        away_pts=f'{away_player["points"]:,}',
        away_model=away_player["model_prob"] * 100,
        away_implied=away_player["raw_implied"] * 100,
        away_edge=away_player["edge"] * 100,
        away_sentiment=_sentiment_label(away_player.get("sentiment", {})),
        h2h_summary=_format_h2h(h2h, home, away, surface),
    )

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.4,
                max_output_tokens=300,
            ),
        )

        raw = response.text
        if not raw:
            logger.warning("[explanation_agent] Empty response for %s vs %s", home, away)
            return None

        # Strip any accidental markdown fences before parsing
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)
        data = json.loads(raw)

        home_insight = str(data.get("home_insight", "")).strip()
        away_insight = str(data.get("away_insight", "")).strip()

        if not home_insight or not away_insight:
            logger.warning("[explanation_agent] Missing insight keys for %s vs %s", home, away)
            return None

        logger.info("[explanation_agent] Generated insights for %s vs %s", home, away)
        return {"home_insight": home_insight, "away_insight": away_insight}

    except Exception as exc:  # noqa: BLE001
        logger.warning("[explanation_agent] Gemini call failed for %s vs %s: %s", home, away, exc)
        return None
