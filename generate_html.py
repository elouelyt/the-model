"""Static site generator — runs the full prediction pipeline and writes index.html.

Designed to run in CI (GitHub Actions) with no GCP dependencies.
Only requires THE_ODDS_API_KEY in the environment.

Usage:
    python generate_html.py
"""

import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s — %(levelname)s — %(message)s")
logger = logging.getLogger(__name__)

# ── Signal styling ─────────────────────────────────────────────────────────────
_SURFACE_META: dict[str, dict] = {
    "clay":        {"label": "Clay",        "color": "#ea580c", "bg": "rgba(234,88,12,0.12)"},
    "grass":       {"label": "Grass",       "color": "#16a34a", "bg": "rgba(22,163,74,0.12)"},
    "hard":        {"label": "Hard",        "color": "#2563eb", "bg": "rgba(37,99,235,0.12)"},
    "indoor_hard": {"label": "Indoor Hard", "color": "#7c3aed", "bg": "rgba(124,58,237,0.12)"},
}

_SIGNAL_META = {
    "value_bet": {
        "label": "VALUE BET",
        "color": "#10b981",
        "bg": "rgba(16,185,129,0.10)",
        "border": "#10b981",
    },
    "marginal": {
        "label": "MARGINAL",
        "color": "#f59e0b",
        "bg": "rgba(245,158,11,0.10)",
        "border": "#f59e0b",
    },
    "no_bet": {
        "label": "NO BET",
        "color": "#6b7280",
        "bg": "rgba(107,114,128,0.10)",
        "border": "#374151",
    },
}


def run_pipeline() -> list[dict]:
    """Run the full prediction pipeline and return a list of match result dicts."""
    from src.ingestion.extract_odds import fetch_odds
    from src.processing.transform import flatten_odds, filter_upcoming
    from src.agents.ranking_agent import fetch_atp_rankings
    from src.agents.probability_calculator import compare_with_bookmaker
    from src.agents.model_agent import predict_win_probability
    from src.agents.surface_agent import get_surface, SURFACE_NOTE
    from src.agents.h2h_agent import get_h2h
    from src.agents.sentiment_agent import fetch_sentiment_batch

    logger.info("Fetching live odds...")
    data = fetch_odds()

    if not data:
        logger.warning("No active tournaments found.")
        return []

    df = flatten_odds(data)
    df = filter_upcoming(df)

    if df.empty:
        logger.warning("All matches are currently in-play. No pre-match odds available.")
        return []

    players = df["outcome_name"].unique().tolist()
    logger.info("Fetching rankings for %d players...", len(players))
    rankings = fetch_atp_rankings(player_names=players)

    logger.info("Fetching sentiment for %d players...", len(players))
    sentiment_map = fetch_sentiment_batch(players)

    results = []
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
            rows = group[group["outcome_name"] == player]
            rec = compare_with_bookmaker(
                model_prob,
                rows["raw_implied"].mean(),
                rows["true_implied"].mean(),
                player,
            )
            rec["rank"] = rankings[player]["rank"]
            rec["points"] = rankings[player]["points"]
            rec["sentiment"] = sentiment_map.get(
                player, {"available": False, "flag": "neutral", "label": None, "headline": None}
            )
            # Per-bookmaker odds — one row per bookmaker, sorted best price first
            bk = (
                rows[["bookmaker_title", "price", "raw_implied"]]
                .drop_duplicates(subset=["bookmaker_title"])
                .sort_values("price", ascending=False)
            )
            rec["bookmakers"] = bk.to_dict("records")
            # Append surface context to recommendation when it adds useful signal
            if surface_note:
                rec["recommendation"] = rec["recommendation"] + f" · {surface_note}"
            players_data.append(rec)

        h2h = get_h2h(home, away, surface)

        results.append({
            "home": home,
            "away": away,
            "commence_time": commence_time,
            "surface": surface,
            "h2h": h2h,
            "players": players_data,
        })

    logger.info("Pipeline complete — %d matches processed.", len(results))
    return results


# ── HTML rendering ─────────────────────────────────────────────────────────────

_SENTIMENT_STYLE: dict[str, dict] = {
    "positive": {"color": "#10b981", "icon": "↑"},
    "concern":  {"color": "#f87171", "icon": "⚠"},
}


def _sentiment_html(sentiment: dict) -> str:
    """Render a small inline sentiment indicator. Empty string if neutral/unavailable."""
    flag = sentiment.get("flag", "neutral")
    label = sentiment.get("label")
    if not label or flag not in _SENTIMENT_STYLE:
        return ""
    s = _SENTIMENT_STYLE[flag]
    return (
        f'<span class="sentiment-flag" style="color:{s["color"]};" '
        f'title="{sentiment.get("headline") or ""}">'
        f'{s["icon"]} {label}</span>'
    )


def _bookmaker_table_html(bookmakers: list[dict]) -> str:
    """Render a collapsible <details> block with per-bookmaker odds table."""
    if not bookmakers:
        return ""

    best_price = max(b["price"] for b in bookmakers)

    rows_html = ""
    for b in bookmakers:
        is_best = abs(b["price"] - best_price) < 0.001
        price_style = ' style="color:#10b981;font-weight:700;"' if is_best else ""
        rows_html += (
            f'<tr>'
            f'<td class="bk-name">{b["bookmaker_title"]}</td>'
            f'<td class="bk-price"{price_style}>{b["price"]:.2f}</td>'
            f'<td class="bk-implied">{b["raw_implied"]:.1%}</td>'
            f'</tr>'
        )

    return f"""
            <details class="odds-details">
                <summary class="odds-summary">Odds by bookmaker <span class="odds-count">({len(bookmakers)})</span></summary>
                <table class="odds-table">
                    <thead>
                        <tr>
                            <th>Bookmaker</th>
                            <th>Price</th>
                            <th>Implied</th>
                        </tr>
                    </thead>
                    <tbody>{rows_html}</tbody>
                </table>
            </details>"""


def _player_card_html(p: dict) -> str:
    meta = _SIGNAL_META[p["signal"]]
    edge_sign = "+" if p["edge"] >= 0 else ""
    edge_color = "#10b981" if p["edge"] > 0.05 else ("#f59e0b" if p["edge"] > 0 else "#6b7280")
    sentiment_tag = _sentiment_html(p.get("sentiment", {}))
    return f"""
        <div class="player-card" style="border-top: 3px solid {meta['border']};">
            <div class="player-name">{p['player']}</div>
            <div class="player-meta">Rank #{p['rank']} &nbsp;·&nbsp; {p['points']:,} pts{(" &nbsp;·&nbsp; " + sentiment_tag) if sentiment_tag else ""}</div>
            <div class="stats-grid">
                <div class="stat">
                    <span class="stat-label">Model prob</span>
                    <span class="stat-value">{p['model_prob']:.1%}</span>
                </div>
                <div class="stat">
                    <span class="stat-label">Bookmaker</span>
                    <span class="stat-value">{p['raw_implied']:.1%}</span>
                </div>
                <div class="stat">
                    <span class="stat-label">Edge</span>
                    <span class="stat-value" style="color:{edge_color};">{edge_sign}{p['edge']:.1%}</span>
                </div>
                <div class="stat">
                    <span class="stat-label">Vig (est.)</span>
                    <span class="stat-value" style="color:#9ca3af;">{p['vig_per_player']:.1%}</span>
                </div>
            </div>
            <div class="signal-badge" style="color:{meta['color']};background:{meta['bg']};border:1px solid {meta['border']};">
                {meta['label']}
            </div>
            <div class="recommendation">{p['recommendation']}</div>
            {_bookmaker_table_html(p.get("bookmakers", []))}
        </div>"""


def _h2h_html(h2h: dict, home: str, away: str, surface: str) -> str:
    """Render a compact H2H line for the match card. Returns empty string if unavailable."""
    if not h2h.get("available") or h2h["total"] == 0:
        return ""

    home_short = home.split()[-1]   # last name only for compactness
    away_short = away.split()[-1]

    overall = f"{home_short} {h2h['a_wins']}–{h2h['b_wins']} {away_short}"

    surface_part = ""
    if h2h["total_surface"] > 0:
        from src.agents.surface_agent import SURFACE_LABEL
        surf_label = SURFACE_LABEL.get(surface, surface.title())
        surface_part = (
            f'<span class="h2h-divider">·</span>'
            f'<span class="h2h-surface">{surf_label}: '
            f'{home_short} {h2h["a_wins_surface"]}–{h2h["b_wins_surface"]} {away_short}</span>'
        )

    return (
        f'<div class="h2h-bar">'
        f'<span class="h2h-label">H2H</span>'
        f'<span class="h2h-record">{overall}</span>'
        f'{surface_part}'
        f'</div>'
    )


def _surface_badge_html(surface: str) -> str:
    s = _SURFACE_META.get(surface, _SURFACE_META["hard"])
    return (
        f'<span class="surface-badge" '
        f'style="color:{s["color"]};background:{s["bg"]};">'
        f'{s["label"]}</span>'
    )


def _match_card_html(match: dict) -> str:
    ct = match["commence_time"]
    ct_str = ct.strftime("%a %d %b · %H:%M UTC") if hasattr(ct, "strftime") else str(ct)
    surface_badge = _surface_badge_html(match.get("surface", "hard"))

    if "error" in match:
        return f"""
    <div class="match-card match-error">
        <div class="match-header">
            <span class="match-teams">{match['home']} <span class="vs">vs</span> {match['away']}</span>
            <span class="match-meta">{surface_badge}<span class="match-time">{ct_str}</span></span>
        </div>
        <div class="error-msg">⚠ {match['error']}</div>
    </div>"""

    players = match["players"]
    signals = [p["signal"] for p in players]
    if "value_bet" in signals:
        accent = _SIGNAL_META["value_bet"]["border"]
    elif "marginal" in signals:
        accent = _SIGNAL_META["marginal"]["border"]
    else:
        accent = "#2a2a2a"

    h2h_html = _h2h_html(match.get("h2h", {}), match["home"], match["away"], match.get("surface", "hard"))
    player_cols = "".join(_player_card_html(p) for p in players)

    return f"""
    <div class="match-card" style="border-left: 3px solid {accent};">
        <div class="match-header">
            <span class="match-teams">{match['home']} <span class="vs">vs</span> {match['away']}</span>
            <span class="match-meta">{surface_badge}<span class="match-time">{ct_str}</span></span>
        </div>
        {h2h_html}
        <div class="players-row">
            {player_cols}
        </div>
    </div>"""


def _no_matches_html() -> str:
    return """
    <div class="empty-state">
        <div class="empty-icon">○</div>
        <div class="empty-title">No pre-match odds available right now</div>
        <div class="empty-body">This page updates daily at 08:00 UTC. Check back when the next event is active.</div>
    </div>"""


def _error_html(message: str) -> str:
    return f"""
    <div class="empty-state" style="border-color:#ef4444;">
        <div class="empty-icon" style="color:#ef4444;">✕</div>
        <div class="empty-title" style="color:#ef4444;">Pipeline error</div>
        <div class="empty-body">{message}</div>
    </div>"""


def generate_html(results: list[dict] | None, error: str | None = None) -> str:
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    if error:
        content = _error_html(error)
        summary_html = ""
    elif not results:
        content = _no_matches_html()
        summary_html = ""
    else:
        value_bets = sum(
            1 for m in results if "players" in m
            for p in m["players"] if p["signal"] == "value_bet"
        )
        total_matches = len(results)
        summary_html = f"""
        <div class="summary-bar">
            <span class="summary-item"><strong>{total_matches}</strong> match{'es' if total_matches != 1 else ''}</span>
            <span class="divider">·</span>
            <span class="summary-item" style="color:#10b981;"><strong>{value_bets}</strong> value bet{'s' if value_bets != 1 else ''} found</span>
        </div>"""
        content = "\n".join(_match_card_html(m) for m in results)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>The Model</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

  :root {{
    --bg:        #0a0a0a;
    --surface:   #141414;
    --surface-2: #1c1c1c;
    --border:    #262626;
    --orange:    #E8650A;
    --text:      #e5e5e5;
    --muted:     #737373;
    --small:     #525252;
  }}

  body {{
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
    font-size: 14px;
    line-height: 1.5;
    min-height: 100vh;
  }}

  /* ── Header ──────────────────────────────────────────────── */
  header {{
    border-bottom: 1px solid var(--border);
    padding: 20px 24px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
  }}
  .site-title {{
    font-size: 18px;
    font-weight: 700;
    letter-spacing: -0.3px;
    color: var(--text);
  }}
  .site-title span {{ color: var(--orange); }}
  .updated {{
    font-size: 12px;
    color: var(--muted);
  }}

  /* ── Layout ──────────────────────────────────────────────── */
  main {{
    max-width: 860px;
    margin: 0 auto;
    padding: 24px 16px 48px;
  }}

  /* ── Summary bar ─────────────────────────────────────────── */
  .summary-bar {{
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 20px;
    font-size: 13px;
    color: var(--muted);
  }}
  .divider {{ color: var(--border); }}

  /* ── Match card ──────────────────────────────────────────── */
  .match-card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 20px;
    margin-bottom: 16px;
    transition: border-color 0.15s;
  }}
  .match-card:hover {{ border-color: #333; }}
  .match-header {{
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 16px;
    flex-wrap: wrap;
  }}
  .match-teams {{
    font-size: 16px;
    font-weight: 600;
    color: var(--text);
  }}
  .vs {{
    color: var(--muted);
    font-weight: 400;
    margin: 0 6px;
  }}
  .match-meta {{
    display: flex;
    align-items: center;
    gap: 8px;
    flex-shrink: 0;
  }}
  .match-time {{
    font-size: 12px;
    color: var(--muted);
    white-space: nowrap;
  }}
  .surface-badge {{
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.5px;
    padding: 2px 7px;
    border-radius: 3px;
    white-space: nowrap;
  }}

  /* ── H2H bar ─────────────────────────────────────────────── */
  .h2h-bar {{
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 10px;
    margin-bottom: 12px;
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: 6px;
    font-size: 12px;
    flex-wrap: wrap;
  }}
  .h2h-label {{
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.5px;
    color: var(--small);
    text-transform: uppercase;
  }}
  .h2h-record {{
    color: var(--text);
    font-weight: 500;
    font-variant-numeric: tabular-nums;
  }}
  .h2h-divider {{ color: var(--border); }}
  .h2h-surface {{ color: var(--muted); }}

  /* ── Player row ──────────────────────────────────────────── */
  .players-row {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
  }}
  @media (max-width: 540px) {{
    .players-row {{ grid-template-columns: 1fr; }}
  }}

  /* ── Player card ─────────────────────────────────────────── */
  .player-card {{
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 14px;
  }}
  .player-name {{
    font-weight: 600;
    font-size: 14px;
    margin-bottom: 2px;
  }}
  .player-meta {{
    font-size: 11px;
    color: var(--muted);
    margin-bottom: 12px;
  }}
  .sentiment-flag {{
    font-size: 11px;
    font-weight: 600;
    cursor: default;
  }}
  .stats-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
    margin-bottom: 12px;
  }}
  .stat {{
    display: flex;
    flex-direction: column;
    gap: 2px;
  }}
  .stat-label {{
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--small);
  }}
  .stat-value {{
    font-size: 15px;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
  }}

  /* ── Signal badge ────────────────────────────────────────── */
  .signal-badge {{
    display: inline-block;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.8px;
    padding: 3px 8px;
    border-radius: 4px;
    margin-bottom: 8px;
  }}
  .recommendation {{
    font-size: 12px;
    color: var(--muted);
    line-height: 1.45;
  }}

  /* ── Bookmaker odds toggle ───────────────────────────────── */
  .odds-details {{
    margin-top: 10px;
    border-top: 1px solid var(--border);
    padding-top: 8px;
  }}
  .odds-summary {{
    font-size: 11px;
    color: var(--small);
    cursor: pointer;
    list-style: none;
    display: flex;
    align-items: center;
    gap: 4px;
    user-select: none;
  }}
  .odds-summary::-webkit-details-marker {{ display: none; }}
  .odds-summary::before {{
    content: "▸";
    font-size: 9px;
    transition: transform 0.15s;
    display: inline-block;
  }}
  details[open] .odds-summary::before {{ transform: rotate(90deg); }}
  .odds-summary:hover {{ color: var(--muted); }}
  .odds-count {{ color: var(--small); }}
  .odds-table {{
    width: 100%;
    border-collapse: collapse;
    margin-top: 8px;
    font-size: 11px;
  }}
  .odds-table th {{
    text-align: left;
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.4px;
    color: var(--small);
    padding: 3px 6px;
    border-bottom: 1px solid var(--border);
  }}
  .odds-table td {{
    padding: 4px 6px;
    border-bottom: 1px solid #1e1e1e;
    color: var(--muted);
    font-variant-numeric: tabular-nums;
  }}
  .odds-table tr:last-child td {{ border-bottom: none; }}
  .bk-name  {{ color: var(--text); }}
  .bk-price {{ font-weight: 500; }}
  .bk-implied {{ color: var(--small); }}

  /* ── Error / empty states ────────────────────────────────── */
  .match-error {{ border-color: #374151; }}
  .error-msg {{
    font-size: 13px;
    color: #f59e0b;
    margin-top: 4px;
  }}
  .empty-state {{
    text-align: center;
    padding: 64px 24px;
    border: 1px dashed var(--border);
    border-radius: 12px;
    margin-top: 24px;
  }}
  .empty-icon {{
    font-size: 32px;
    color: var(--muted);
    margin-bottom: 12px;
  }}
  .empty-title {{
    font-size: 16px;
    font-weight: 600;
    margin-bottom: 8px;
  }}
  .empty-body {{
    font-size: 13px;
    color: var(--muted);
    max-width: 340px;
    margin: 0 auto;
  }}

  /* ── Footer ──────────────────────────────────────────────── */
  footer {{
    border-top: 1px solid var(--border);
    padding: 16px 24px;
    font-size: 11px;
    color: var(--small);
    text-align: center;
  }}
  footer a {{ color: var(--muted); text-decoration: none; }}
  footer a:hover {{ color: var(--text); }}
</style>
</head>
<body>

<header>
  <div class="site-title">the<span>·</span>model</div>
  <div class="updated">Updated {now_utc}</div>
</header>

<main>
  {summary_html}
  {content}
</main>

<footer>
  Pre-match predictions only &nbsp;·&nbsp; Model: logistic regression (ranking pts, rank, surface) &nbsp;·&nbsp;
  For informational purposes only — not financial or betting advice &nbsp;·&nbsp;
  <a href="https://github.com/elouelyt/the-model" target="_blank">Source</a>
</footer>

</body>
</html>
"""


def main() -> None:
    if not os.getenv("THE_ODDS_API_KEY"):
        logger.error("THE_ODDS_API_KEY is not set. Aborting.")
        sys.exit(1)

    results = None
    error = None

    try:
        results = run_pipeline()
    except Exception as exc:
        logger.error("Pipeline failed: %s", exc, exc_info=True)
        error = str(exc)

    html = generate_html(results, error=error)
    out = Path("index.html")
    out.write_text(html, encoding="utf-8")
    logger.info("Written %s (%d bytes)", out, len(html))


if __name__ == "__main__":
    main()
