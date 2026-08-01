"""Static site generator — runs the full prediction pipeline and writes index.html.

Designed to run in CI (GitHub Actions) with no GCP dependencies.
Only requires THE_ODDS_API_KEY in the environment.

Usage:
    python generate_html.py
"""

import json
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


def run_pipeline() -> tuple[list[dict], list[dict], list[dict]]:
    """Run the full prediction pipeline via LangGraph coordinator.

    Returns:
        (results, parlays, safe_parlays) — match result dicts, rated parlay dicts,
        and rated safe (daily compounder) parlay dicts.
    """
    from src.pipeline.coordinator import run_pipeline as _coordinator_run
    return _coordinator_run()


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


def _prob_bar_html(model_prob: float, raw_implied: float) -> str:
    """Render a dual probability bar: model (orange) vs bookmaker (grey)."""
    m = min(max(model_prob * 100, 0), 100)
    b = min(max(raw_implied * 100, 0), 100)
    return f"""
        <div class="prob-bars">
            <div class="prob-row">
                <span class="prob-label">Model</span>
                <div class="prob-track">
                    <div class="prob-fill prob-model" style="width:{m:.1f}%;"></div>
                </div>
                <span class="prob-val">{m:.1f}%</span>
            </div>
            <div class="prob-row">
                <span class="prob-label">Mkt</span>
                <div class="prob-track">
                    <div class="prob-fill prob-mkt" style="width:{b:.1f}%;"></div>
                </div>
                <span class="prob-val">{b:.1f}%</span>
            </div>
        </div>"""


def _stake_badge_html(stake_price: float) -> str:
    """Render a highlighted Stake odds badge."""
    return (
        f'<div class="stake-badge">'
        f'<span class="stake-logo">S</span>'
        f'<span class="stake-label">Stake</span>'
        f'<span class="stake-price">{stake_price:.2f}</span>'
        f'</div>'
    )


def _player_card_html(p: dict) -> str:
    meta = _SIGNAL_META[p["signal"]]
    edge_sign = "+" if p["edge"] >= 0 else ""
    edge_color = "#10b981" if p["edge"] > 0.05 else ("#f59e0b" if p["edge"] > 0 else "#6b7280")
    sentiment_tag = _sentiment_html(p.get("sentiment", {}))
    prob_bars = _prob_bar_html(p["model_prob"], p["raw_implied"])
    stake_html = _stake_badge_html(p["stake_price"]) if p.get("stake_price") else ""
    return f"""
        <div class="player-card" style="border-top: 2px solid {meta['border']};">
            <div class="player-name">{p['player']}{(" <span class='sentiment-sep'>·</span> " + sentiment_tag) if sentiment_tag else ""}</div>
            <div class="player-meta">Rank <strong>#{p['rank']}</strong> &nbsp;·&nbsp; {p['points']:,} pts</div>
            {prob_bars}
            {stake_html}
            <div class="stats-grid">
                <div class="stat">
                    <span class="stat-label">Edge</span>
                    <span class="stat-value" style="color:{edge_color};">{edge_sign}{p['edge']:.1%}</span>
                </div>
                <div class="stat">
                    <span class="stat-label">Vig</span>
                    <span class="stat-value" style="color:var(--small);">{p['vig_per_player']:.1%}</span>
                </div>
            </div>
            <div class="signal-pill" style="color:{meta['color']};background:{meta['bg']};border:1px solid {meta['border']}20;">
                <span class="signal-dot" style="background:{meta['color']};"></span>{meta['label']}
            </div>
            <div class="recommendation">{p['recommendation']}</div>
            {_bookmaker_table_html(p.get("bookmakers", []))}
        </div>"""


def _h2h_html(h2h: dict, home: str, away: str, surface: str) -> str:
    """Render the H2H section for a match card.

    Always renders (returns a bar even for zero-meeting pairs) so every card
    surfaces the historical context — or explicitly says there is none.
    Returns empty string only when the agent could not retrieve data at all.
    """
    if not h2h.get("available"):
        return ""

    home_short = home.split()[-1]
    away_short = away.split()[-1]
    total = h2h.get("total", 0)

    # ── No previous meetings ──────────────────────────────────────────────
    if total == 0:
        return (
            f'<div class="h2h-bar">'
            f'<span class="h2h-label">H2H</span>'
            f'<span class="h2h-no-data">No previous meetings (last 4 years)</span>'
            f'</div>'
        )

    # ── Head-to-head with data ────────────────────────────────────────────
    a_wins = h2h["a_wins"]
    b_wins = h2h["b_wins"]
    leader = h2h.get("leader")  # "a", "b", or None (tied)

    # Highlight the leader in orange
    if leader == "a":
        a_str = f'<span class="h2h-leader">{home_short} {a_wins}</span>'
        b_str = f'<span class="h2h-trailer">{b_wins} {away_short}</span>'
    elif leader == "b":
        a_str = f'<span class="h2h-trailer">{home_short} {a_wins}</span>'
        b_str = f'<span class="h2h-leader">{b_wins} {away_short}</span>'
    else:
        a_str = f'<span class="h2h-record">{home_short} {a_wins}</span>'
        b_str = f'<span class="h2h-record">{b_wins} {away_short}</span>'

    overall_html = (
        f'{a_str}'
        f'<span class="h2h-sep">–</span>'
        f'{b_str}'
        f'<span class="h2h-total">({total} match{"es" if total != 1 else ""})</span>'
    )

    # ── Surface breakdown ─────────────────────────────────────────────────
    surface_part = ""
    total_surf = h2h.get("total_surface", 0)
    if total_surf > 0:
        from src.agents.surface_agent import SURFACE_LABEL
        surf_label = SURFACE_LABEL.get(surface, surface.title())
        as_wins = h2h["a_wins_surface"]
        bs_wins = h2h["b_wins_surface"]
        leader_s = h2h.get("leader_surface")
        if leader_s == "a":
            as_str = f'<span class="h2h-leader">{home_short} {as_wins}</span>'
            bs_str = f'<span class="h2h-trailer">{bs_wins} {away_short}</span>'
        elif leader_s == "b":
            as_str = f'<span class="h2h-trailer">{home_short} {as_wins}</span>'
            bs_str = f'<span class="h2h-leader">{bs_wins} {away_short}</span>'
        else:
            as_str = f'<span class="h2h-record">{home_short} {as_wins}</span>'
            bs_str = f'<span class="h2h-record">{bs_wins} {away_short}</span>'

        surface_part = (
            f'<span class="h2h-divider">·</span>'
            f'<span class="h2h-surf-label">{surf_label}:</span> '
            f'{as_str}<span class="h2h-sep">–</span>{bs_str}'
            f'<span class="h2h-total">({total_surf})</span>'
        )

    return (
        f'<div class="h2h-bar">'
        f'<span class="h2h-label">H2H</span>'
        f'{overall_html}'
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
    glow_color = accent if accent != "#2a2a2a" else "transparent"

    withdrawal_alert = match.get("withdrawal_alert")
    if withdrawal_alert:
        wd_headline = withdrawal_alert.get("headline") or ""
        wd_text = f': &ldquo;{wd_headline}&rdquo;' if wd_headline else ""
        withdrawal_html = (
            f'<div class="withdrawal-alert">'
            f'<span class="withdrawal-icon">⚠</span>'
            f'<strong>WITHDRAWAL REPORTED</strong> &mdash; {withdrawal_alert["player"]}{wd_text}'
            f'</div>'
        )
        # Override accent to red when there's a withdrawal
        accent = "#f87171"
        glow_color = "#f87171"
    else:
        withdrawal_html = ""

    return f"""
    <div class="match-card" style="border-left: 3px solid {accent}; --card-glow: {glow_color};">
        <div class="match-header">
            <span class="match-teams">{match['home']} <span class="vs">vs</span> {match['away']}</span>
            <span class="match-meta">{surface_badge}<span class="match-time">{ct_str}</span></span>
        </div>
        {withdrawal_html}{h2h_html}
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


def _parlays_html(parlays: list[dict]) -> str:
    """Render the collapsed Recommended Parlays section."""
    if not parlays:
        return ""

    _SURFACE_COLORS = {
        "clay": "#ea580c", "grass": "#16a34a",
        "hard": "#2563eb", "indoor_hard": "#7c3aed",
    }
    _SURFACE_LABELS = {
        "clay": "Clay", "grass": "Grass",
        "hard": "Hard", "indoor_hard": "Indoor",
    }
    _RISK_META = {
        "low":    {"color": "#10b981", "bg": "rgba(16,185,129,0.10)",  "border": "rgba(16,185,129,0.25)"},
        "medium": {"color": "#f59e0b", "bg": "rgba(245,158,11,0.10)",  "border": "rgba(245,158,11,0.25)"},
        "high":   {"color": "#f87171", "bg": "rgba(248,113,113,0.10)", "border": "rgba(248,113,113,0.25)"},
    }

    cards_html = ""
    for i, parlay in enumerate(parlays):
        risk = parlay.get("risk", "medium")
        risk_meta = _RISK_META.get(risk, _RISK_META["medium"])
        rating = parlay.get("rating", 5)
        summary = parlay.get("summary", "")

        # Rating bar fill (out of 10)
        rating_pct = rating * 10

        # Pick rows
        picks_html = ""
        for p in parlay["picks"]:
            surf_color = _SURFACE_COLORS.get(p["surface"], "#2563eb")
            surf_label = _SURFACE_LABELS.get(p["surface"], p["surface"].title())
            sent = p.get("sentiment", {})
            sent_flag = sent.get("flag", "neutral") if sent else "neutral"
            sent_icon = "↑" if sent_flag == "positive" else ("⚠" if sent_flag == "concern" else "")
            sent_color = "#10b981" if sent_flag == "positive" else ("#f87171" if sent_flag == "concern" else "")
            bk_name = p.get("best_bookmaker", "")
            bk_html = f'&nbsp;<span style="color:#f97316;font-size:10px;opacity:0.8;">@ {bk_name}</span>' if bk_name and bk_name != "Stake" else ""
            opp_rank = p.get("opponent_rank")
            rank_html = f'#{p["rank"]} <span style="color:var(--muted);font-size:10px;">vs #{opp_rank}</span>' if opp_rank else f'#{p["rank"]}'
            picks_html += f"""
                <div class="parlay-pick">
                    <span class="parlay-pick-name">{p['player']}</span>
                    <span class="parlay-pick-meta">
                        {rank_html} &nbsp;·&nbsp;
                        <span style="color:{surf_color};font-weight:600;">{surf_label}</span> &nbsp;·&nbsp;
                        {p['model_prob']:.0%} model &nbsp;·&nbsp;
                        {p['best_price']:.2f}{bk_html}
                        {f'&nbsp;<span style="color:#00a86b;font-weight:700;">S {p["stake_price"]:.2f}</span>' if p.get("stake_price") else ""}
                        {f'&nbsp;<span style="color:{sent_color};font-size:10px;">{sent_icon}</span>' if sent_icon else ""}
                    </span>
                </div>"""

        stake_odds_html = ""
        if parlay.get("stake_total_odds"):
            stake_odds_html = f'<span class="parlay-stake-odds">S&nbsp;{parlay["stake_total_odds"]:.2f}</span>'

        cards_html += f"""
        <div class="parlay-card">
            <div class="parlay-card-header">
                <div class="parlay-legs">{parlay['size']}-leg parlay</div>
                <div class="parlay-header-right">
                    <span class="risk-badge" style="color:{risk_meta['color']};background:{risk_meta['bg']};border:1px solid {risk_meta['border']};">{risk.upper()}</span>
                    {stake_odds_html}
                    <span class="parlay-odds">{parlay['total_odds']:.2f}</span>
                </div>
            </div>
            <div class="parlay-picks">{picks_html}</div>
            <div class="parlay-footer">
                <div class="rating-row">
                    <span class="rating-label">Gemini</span>
                    <div class="rating-track">
                        <div class="rating-fill" style="width:{rating_pct}%;background:{'#10b981' if rating>=7 else '#f59e0b' if rating>=5 else '#f87171'};"></div>
                    </div>
                    <span class="rating-val">{rating}/10</span>
                </div>
                <div class="parlay-cum-prob">Cumulative model prob: <strong>{parlay['cum_prob']:.1%}</strong></div>
            </div>
            {f'<div class="parlay-summary">{summary}</div>' if summary else ""}
        </div>"""

    return f"""
    <details class="parlays-section">
        <summary class="parlays-summary">
            <span class="parlays-title">Recommended Parlays</span>
            <span class="parlays-count">({len(parlays)})</span>
            <span class="parlays-chevron">▸</span>
        </summary>
        <div class="parlays-grid">{cards_html}</div>
    </details>"""


def _safe_parlays_html(safe_parlays: list[dict]) -> str:
    """Render the collapsed Safe Parlays — Daily Compounder section."""
    if not safe_parlays:
        return ""

    _SURFACE_COLORS = {
        "clay": "#ea580c", "grass": "#16a34a",
        "hard": "#2563eb", "indoor_hard": "#7c3aed",
    }
    _SURFACE_LABELS = {
        "clay": "Clay", "grass": "Grass",
        "hard": "Hard", "indoor_hard": "Indoor",
    }
    _RISK_META = {
        "low":    {"color": "#10b981", "bg": "rgba(16,185,129,0.10)",  "border": "rgba(16,185,129,0.25)"},
        "medium": {"color": "#f59e0b", "bg": "rgba(245,158,11,0.10)",  "border": "rgba(245,158,11,0.25)"},
        "high":   {"color": "#f87171", "bg": "rgba(248,113,113,0.10)", "border": "rgba(248,113,113,0.25)"},
    }

    cards_html = ""
    for parlay in safe_parlays:
        risk = parlay.get("risk", "medium")
        risk_meta = _RISK_META.get(risk, _RISK_META["medium"])
        rating = parlay.get("rating", 5)
        summary = parlay.get("summary", "")
        is_today = parlay.get("today_pick", False)
        rating_pct = rating * 10

        picks_html = ""
        for p in parlay["picks"]:
            surf_color = _SURFACE_COLORS.get(p["surface"], "#2563eb")
            surf_label = _SURFACE_LABELS.get(p["surface"], p["surface"].title())
            sent = p.get("sentiment", {})
            sent_flag = sent.get("flag", "neutral") if sent else "neutral"
            sent_icon = "↑" if sent_flag == "positive" else ("⚠" if sent_flag == "concern" else "")
            sent_color = "#10b981" if sent_flag == "positive" else ("#f87171" if sent_flag == "concern" else "")
            bk_name = p.get("best_bookmaker", "")
            bk_html = f'&nbsp;<span style="color:#f97316;font-size:10px;opacity:0.8;">@ {bk_name}</span>' if bk_name and bk_name != "Stake" else ""
            opp_rank = p.get("opponent_rank")
            rank_html = f'#{p["rank"]} <span style="color:var(--muted);font-size:10px;">vs #{opp_rank}</span>' if opp_rank else f'#{p["rank"]}'
            picks_html += f"""
                <div class="parlay-pick">
                    <span class="parlay-pick-name">{p['player']}</span>
                    <span class="parlay-pick-meta">
                        {rank_html} &nbsp;·&nbsp;
                        <span style="color:{surf_color};font-weight:600;">{surf_label}</span> &nbsp;·&nbsp;
                        {p['raw_implied']:.0%} mkt &nbsp;·&nbsp;
                        {p['best_price']:.2f}{bk_html}
                        {f'&nbsp;<span style="color:#00a86b;font-weight:700;">S {p["stake_price"]:.2f}</span>' if p.get("stake_price") else ""}
                        {f'&nbsp;<span style="color:{sent_color};font-size:10px;">{sent_icon}</span>' if sent_icon else ""}
                    </span>
                </div>"""

        today_badge = (
            '<span class="today-pick-badge">TODAY\'S BET</span>'
            if is_today else ""
        )

        stake_odds_html = ""
        if parlay.get("stake_total_odds"):
            stake_odds_html = f'<span class="parlay-stake-odds">S&nbsp;{parlay["stake_total_odds"]:.2f}</span>'

        cards_html += f"""
        <div class="parlay-card{' safe-today-pick' if is_today else ''}">
            <div class="parlay-card-header">
                <div class="parlay-legs">{parlay['size']}-leg parlay {today_badge}</div>
                <div class="parlay-header-right">
                    <span class="risk-badge" style="color:{risk_meta['color']};background:{risk_meta['bg']};border:1px solid {risk_meta['border']};">{risk.upper()}</span>
                    {stake_odds_html}
                    <span class="parlay-odds">{parlay['total_odds']:.2f}</span>
                </div>
            </div>
            <div class="parlay-picks">{picks_html}</div>
            <div class="parlay-footer">
                <div class="rating-row">
                    <span class="rating-label">Gemini</span>
                    <div class="rating-track">
                        <div class="rating-fill" style="width:{rating_pct}%;background:{'#10b981' if rating>=7 else '#f59e0b' if rating>=5 else '#f87171'};"></div>
                    </div>
                    <span class="rating-val">{rating}/10</span>
                </div>
                <div class="parlay-cum-prob">Cumulative model prob: <strong>{parlay['cum_prob']:.1%}</strong></div>
            </div>
            {f'<div class="parlay-summary">{summary}</div>' if summary else ""}
        </div>"""

    return f"""
    <details class="parlays-section safe-parlays-section">
        <summary class="parlays-summary">
            <span class="parlays-title">Safe Parlays &mdash; Daily Compounder</span>
            <span class="parlays-count">({len(safe_parlays)})</span>
            <span class="parlays-chevron">▸</span>
        </summary>
        <div class="safe-parlays-intro">
            Strategy: picks with bookmaker implied &gt;65% — highest-probability legs only.
            Reinvest daily winnings. <strong>TODAY'S BET</strong> is the top-rated combination.
        </div>
        <div class="parlays-grid">{cards_html}</div>
    </details>"""


def _month_table_html(days: dict, stake_per_bet: float = 15.0) -> str:
    """Render the day-by-day table for one month."""
    rows_html = ""
    total_won_eur = 0.0
    total_lost_eur = 0.0

    for day_num in range(1, 32):
        day_key = str(day_num)
        day_data = days.get(day_key)
        if not day_data:
            rows_html += (
                f'<tr class="tr-empty"><td>{day_num}</td>'
                '<td>—</td><td>—</td><td>—</td><td>—</td><td>—</td></tr>'
            )
            continue

        parlays_day = day_data.get("parlays", [])
        won_count  = sum(1 for p in parlays_day if p.get("won") is True)
        lost_count = sum(1 for p in parlays_day if p.get("won") is False)
        pending    = sum(1 for p in parlays_day if p.get("won") is None)

        day_won_eur  = sum(
            stake_per_bet * (p.get("stake_odds") or p.get("best_odds") or 1) - stake_per_bet
            for p in parlays_day if p.get("won") is True
        )
        day_lost_eur = lost_count * stake_per_bet
        total_won_eur  += day_won_eur
        total_lost_eur += day_lost_eur

        roi_day   = day_won_eur - day_lost_eur
        roi_color = "#10b981" if roi_day >= 0 else "#f87171"
        pending_badge = (
            f' <span style="color:var(--muted);font-size:10px;">+{pending} pend.</span>'
            if pending else ""
        )

        detail_rows = ""
        for i, p in enumerate(parlays_day, 1):
            legs     = ", ".join(p.get("legs", []))
            odds     = p.get("stake_odds") or p.get("best_odds")
            odds_str = f"{odds:.2f}" if odds else "—"
            if p.get("won") is True:
                result_badge = '<span style="color:#10b981;font-weight:700;">✓ WON</span>'
            elif p.get("won") is False:
                result_badge = '<span style="color:#f87171;font-weight:700;">✗ LOST</span>'
            else:
                result_badge = '<span style="color:var(--muted);">pending</span>'
            detail_rows += (
                f'<tr><td style="color:var(--muted);font-size:11px;">#{i}</td>'
                f'<td style="font-size:11px;">{legs}</td>'
                f'<td style="font-size:11px;">{odds_str}</td>'
                f'<td>{result_badge}</td></tr>'
            )

        detail_html = f"""<details style="margin:0;">
            <summary style="cursor:pointer;list-style:none;color:var(--accent);">▸ {won_count}/{len(parlays_day)}{pending_badge}</summary>
            <table style="margin-top:6px;width:100%;font-size:11px;">
                <thead><tr><th>#</th><th>Parlay</th><th>Cuota</th><th>Resultado</th></tr></thead>
                <tbody>{detail_rows}</tbody>
            </table>
        </details>"""

        day_apostado  = len(parlays_day) * stake_per_bet
        lost_display  = f"-{total_lost_eur:.2f}€" if total_lost_eur > 0 else "0.00€"
        rows_html += f"""<tr>
            <td style="font-weight:600;">{day_num}</td>
            <td>{detail_html}</td>
            <td style="color:var(--muted);">{day_apostado:.0f}€</td>
            <td style="color:#10b981;">+{total_won_eur:.2f}€</td>
            <td style="color:#f87171;">{lost_display}</td>
            <td style="color:{roi_color};font-weight:700;">{roi_day:+.2f}€</td>
        </tr>"""

    net       = total_won_eur - total_lost_eur
    net_color = "#10b981" if net >= 0 else "#f87171"
    total_apostado = sum(
        len(days[d].get("parlays", [])) * stake_per_bet
        for d in days if days[d].get("parlays")
    )
    roi_pct = (net / total_apostado * 100) if total_apostado > 0 else 0.0

    return f"""
    <table style="width:100%;border-collapse:collapse;font-size:13px;">
      <thead>
        <tr style="color:var(--muted);text-align:left;border-bottom:1px solid var(--border);">
          <th style="padding:6px 8px;">Día</th>
          <th style="padding:6px 8px;">Ganadas</th>
          <th style="padding:6px 8px;">Apostado</th>
          <th style="padding:6px 8px;">Llevamos ganados</th>
          <th style="padding:6px 8px;">Llevamos perdidos</th>
          <th style="padding:6px 8px;">ROI día</th>
        </tr>
      </thead>
      <tbody>{rows_html}</tbody>
      <tfoot>
        <tr style="border-top:1px solid var(--border);font-weight:700;">
          <td style="padding:8px;">TOTAL</td>
          <td></td>
          <td style="color:var(--muted);">{total_apostado:.0f}€</td>
          <td style="color:#10b981;">+{total_won_eur:.2f}€</td>
          <td style="color:#f87171;">-{total_lost_eur:.2f}€</td>
          <td style="color:{net_color};">{net:+.2f}€ ({roi_pct:+.1f}%)</td>
        </tr>
      </tfoot>
    </table>""", net, total_apostado, roi_pct


def _track_record_html(track_record: dict) -> str:
    """Generate multi-month track record with tab selector."""
    if not track_record or not track_record.get("months"):
        return ""

    months_data = track_record["months"]
    # Sort months chronologically, most recent last (tabs left→right = oldest→newest)
    sorted_months = sorted(months_data.keys())
    if not sorted_months:
        return ""

    now        = datetime.now(timezone.utc)
    cur_month  = now.strftime("%Y-%m")
    # Default to the most recent month that has data
    active_month = sorted_months[-1]

    _MONTH_NAMES_ES = {
        "01": "Enero", "02": "Febrero", "03": "Marzo", "04": "Abril",
        "05": "Mayo",  "06": "Junio",   "07": "Julio", "08": "Agosto",
        "09": "Septiembre", "10": "Octubre", "11": "Noviembre", "12": "Diciembre",
    }

    def month_label(m: str) -> str:
        parts = m.split("-")
        return f"{_MONTH_NAMES_ES.get(parts[1], parts[1])} {parts[0]}" if len(parts) == 2 else m

    # Build tab buttons
    tab_buttons = ""
    for m in sorted_months:
        days = months_data[m].get("days", {})
        if not days:
            continue
        active_cls = "tr-active" if m == active_month else ""
        tab_buttons += (
            f'<button class="month-tab {active_cls}" '
            f'onclick="switchMonth(\'{m}\')" id="tab-{m}">'
            f'{month_label(m)}</button>'
        )

    # Build month panels
    panels_html = ""
    all_months_net = 0.0
    all_months_apostado = 0.0

    for m in sorted_months:
        days = months_data[m].get("days", {})
        if not days:
            continue
        table_html, net, apostado, roi_pct = _month_table_html(days)
        all_months_net      += net
        all_months_apostado += apostado
        net_color = "#10b981" if net >= 0 else "#f87171"
        display = "block" if m == active_month else "none"
        panels_html += f"""
<div class="month-panel" id="panel-{m}" style="display:{display};">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
    <span style="font-size:12px;color:var(--muted);">{month_label(m)}</span>
    <span style="font-size:13px;font-weight:700;color:{net_color};">{net:+.2f}€ &nbsp; ROI {roi_pct:+.1f}%</span>
  </div>
  {table_html}
</div>"""

    # Cumulative summary across all months
    all_roi_pct   = (all_months_net / all_months_apostado * 100) if all_months_apostado > 0 else 0.0
    all_net_color = "#10b981" if all_months_net >= 0 else "#f87171"
    cumulative_badge = (
        f'<span style="font-size:12px;color:var(--muted);margin-left:12px;">'
        f'Total acumulado: <strong style="color:{all_net_color};">'
        f'{all_months_net:+.2f}€ ({all_roi_pct:+.1f}%)</strong></span>'
        if len(sorted_months) > 1 else ""
    )

    return f"""
<details class="parlays-section" style="margin-top:8px;" open>
  <summary class="parlays-summary">
    <span class="parlays-title">📊 Track Record</span>
    <span class="parlays-count" style="color:{all_net_color};">{all_months_net:+.2f}€ total</span>
    <span class="parlays-chevron">▸</span>
  </summary>
  <div style="padding:12px 0;">
    <div style="display:flex;align-items:center;flex-wrap:wrap;gap:6px;margin-bottom:14px;">
      {tab_buttons}
      {cumulative_badge}
    </div>
    {panels_html}
  </div>
</details>
<style>
.month-tab {{
  background: var(--surface-2);
  border: 1px solid var(--border);
  color: var(--text);
  padding: 5px 14px;
  border-radius: 6px;
  font-size: 12px;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
}}
.month-tab:hover {{ background: var(--surface-3); }}
.month-tab.tr-active {{
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
  font-weight: 600;
}}
</style>
<script>
function switchMonth(m) {{
  document.querySelectorAll('.month-panel').forEach(p => p.style.display = 'none');
  document.querySelectorAll('.month-tab').forEach(b => b.classList.remove('tr-active'));
  var panel = document.getElementById('panel-' + m);
  var tab   = document.getElementById('tab-'   + m);
  if (panel) panel.style.display = 'block';
  if (tab)   tab.classList.add('tr-active');
}}
</script>"""


def generate_html(results: list[dict] | None, parlays: list[dict] | None = None,
                  safe_parlays: list[dict] | None = None,
                  error: str | None = None,
                  track_record: dict | None = None) -> str:
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    parlays = parlays or []
    safe_parlays = safe_parlays or []

    if error:
        content = _error_html(error)
        summary_html = ""
        parlays_html = ""
        safe_parlays_html = ""
    elif not results:
        content = _no_matches_html()
        summary_html = ""
        parlays_html = ""
        safe_parlays_html = ""
    else:
        value_bets = sum(
            1 for m in results if "players" in m
            for p in m["players"] if p["signal"] == "value_bet"
        )
        marginals = sum(
            1 for m in results if "players" in m
            for p in m["players"] if p["signal"] == "marginal"
        )
        total_matches = len(results)
        vb_html = f'<span class="pill pill-green"><strong>{value_bets}</strong> value bet{"s" if value_bets != 1 else ""}</span>' if value_bets else ""
        mg_html = f'<span class="pill pill-amber"><strong>{marginals}</strong> marginal{"s" if marginals != 1 else ""}</span>' if marginals else ""
        summary_html = f"""
        <div class="summary-bar">
            <span class="summary-matches"><strong>{total_matches}</strong> match{'es' if total_matches != 1 else ''}</span>
            <span class="summary-pills">{vb_html}{mg_html}</span>
        </div>"""
        parlays_html = _parlays_html(parlays)
        safe_parlays_html = _safe_parlays_html(safe_parlays)
        content = "\n".join(_match_card_html(m) for m in results)

    track_record_html = _track_record_html(track_record or {})

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>The Model · ATP Predictions</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

  :root {{
    --bg:        #080808;
    --surface:   #111111;
    --surface-2: #181818;
    --surface-3: #1f1f1f;
    --border:    #242424;
    --border-2:  #2e2e2e;
    --orange:    #f97316;
    --orange-dim: rgba(249,115,22,0.12);
    --green:     #10b981;
    --amber:     #f59e0b;
    --red:       #f87171;
    --text:      #ededed;
    --muted:     #6b6b6b;
    --small:     #4a4a4a;
  }}

  /* ── Scrollbar ───────────────────────────────────────────── */
  ::-webkit-scrollbar {{ width: 6px; height: 6px; }}
  ::-webkit-scrollbar-track {{ background: var(--bg); }}
  ::-webkit-scrollbar-thumb {{ background: var(--border-2); border-radius: 3px; }}
  ::-webkit-scrollbar-thumb:hover {{ background: #3a3a3a; }}

  body {{
    background: var(--bg);
    color: var(--text);
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, system-ui, sans-serif;
    font-size: 14px;
    line-height: 1.55;
    min-height: 100vh;
    -webkit-font-smoothing: antialiased;
  }}

  /* ── Header ──────────────────────────────────────────────── */
  header {{
    position: sticky;
    top: 0;
    z-index: 10;
    background: rgba(8,8,8,0.85);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border-bottom: 1px solid var(--border);
    padding: 0 24px;
    height: 56px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 16px;
  }}
  .site-title {{
    font-size: 15px;
    font-weight: 700;
    letter-spacing: -0.5px;
    color: var(--text);
    display: flex;
    align-items: center;
    gap: 8px;
  }}
  .site-title .logo-mark {{
    width: 26px;
    height: 26px;
    background: var(--orange);
    border-radius: 6px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 13px;
    font-weight: 800;
    color: #fff;
    letter-spacing: -1px;
    flex-shrink: 0;
  }}
  .header-right {{
    display: flex;
    align-items: center;
    gap: 16px;
  }}
  .updated {{
    font-size: 11px;
    color: var(--small);
    font-variant-numeric: tabular-nums;
  }}
  .header-tag {{
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.6px;
    text-transform: uppercase;
    color: var(--small);
    background: var(--surface-3);
    border: 1px solid var(--border);
    padding: 3px 8px;
    border-radius: 4px;
  }}

  /* ── Layout ──────────────────────────────────────────────── */
  main {{
    max-width: 880px;
    margin: 0 auto;
    padding: 28px 16px 64px;
  }}

  /* ── Summary bar ─────────────────────────────────────────── */
  .summary-bar {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 10px;
    margin-bottom: 24px;
    padding-bottom: 20px;
    border-bottom: 1px solid var(--border);
  }}
  .summary-matches {{
    font-size: 13px;
    color: var(--muted);
  }}
  .summary-matches strong {{ color: var(--text); font-weight: 600; }}
  .summary-pills {{
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
  }}
  .pill {{
    font-size: 11px;
    font-weight: 600;
    padding: 3px 10px;
    border-radius: 99px;
    letter-spacing: 0.1px;
  }}
  .pill-green {{
    color: var(--green);
    background: rgba(16,185,129,0.10);
    border: 1px solid rgba(16,185,129,0.20);
  }}
  .pill-amber {{
    color: var(--amber);
    background: rgba(245,158,11,0.10);
    border: 1px solid rgba(245,158,11,0.20);
  }}

  /* ── Match card ──────────────────────────────────────────── */
  .match-card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 14px;
    transition: box-shadow 0.2s, border-color 0.2s;
  }}
  .match-card:hover {{
    border-color: var(--border-2);
    box-shadow: 0 0 0 1px var(--border-2),
                0 8px 32px rgba(0,0,0,0.4),
                0 0 20px color-mix(in srgb, var(--card-glow, transparent) 8%, transparent);
  }}
  .match-header {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    margin-bottom: 14px;
    flex-wrap: wrap;
  }}
  .match-teams {{
    font-size: 15px;
    font-weight: 600;
    color: var(--text);
    letter-spacing: -0.2px;
  }}
  .vs {{
    color: var(--small);
    font-weight: 400;
    font-size: 13px;
    margin: 0 7px;
  }}
  .match-meta {{
    display: flex;
    align-items: center;
    gap: 8px;
    flex-shrink: 0;
  }}
  .match-time {{
    font-size: 11px;
    color: var(--muted);
    white-space: nowrap;
    font-variant-numeric: tabular-nums;
  }}
  .surface-badge {{
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.7px;
    padding: 2px 7px;
    border-radius: 4px;
    white-space: nowrap;
    text-transform: uppercase;
  }}

  /* ── H2H bar ─────────────────────────────────────────────── */
  .h2h-bar {{
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 7px 12px;
    margin-bottom: 14px;
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: 8px;
    font-size: 12px;
    flex-wrap: wrap;
    font-variant-numeric: tabular-nums;
  }}
  .h2h-label {{
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.7px;
    color: var(--small);
    text-transform: uppercase;
    padding: 1px 5px;
    background: var(--surface-3);
    border-radius: 3px;
    margin-right: 2px;
  }}
  .h2h-leader  {{ color: var(--orange); font-weight: 700; }}
  .h2h-trailer {{ color: var(--muted);  font-weight: 500; }}
  .h2h-record  {{ color: var(--text);   font-weight: 500; }}
  .h2h-sep     {{ color: var(--small);  margin: 0 2px; }}
  .h2h-total   {{ color: var(--small);  font-size: 11px; }}
  .h2h-divider {{ color: var(--border); margin: 0 6px; }}
  .h2h-surf-label {{ color: var(--muted); }}
  .h2h-no-data {{ color: var(--small); font-style: italic; font-size: 11px; }}

  /* ── Player grid ─────────────────────────────────────────── */
  .players-row {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
  }}
  @media (max-width: 560px) {{
    .players-row {{ grid-template-columns: 1fr; }}
    .match-teams {{ font-size: 14px; }}
  }}

  /* ── Player card ─────────────────────────────────────────── */
  .player-card {{
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 14px;
    display: flex;
    flex-direction: column;
    gap: 0;
  }}
  .player-name {{
    font-weight: 600;
    font-size: 13px;
    color: var(--text);
    margin-bottom: 3px;
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 6px;
  }}
  .sentiment-sep {{ color: var(--border); }}
  .player-meta {{
    font-size: 11px;
    color: var(--muted);
    margin-bottom: 12px;
  }}
  .player-meta strong {{ color: var(--text); font-weight: 600; }}
  .sentiment-flag {{
    font-size: 10px;
    font-weight: 600;
    cursor: default;
    letter-spacing: 0.1px;
  }}

  /* ── Probability bars ────────────────────────────────────── */
  .prob-bars {{
    display: flex;
    flex-direction: column;
    gap: 5px;
    margin-bottom: 12px;
  }}
  .prob-row {{
    display: flex;
    align-items: center;
    gap: 6px;
  }}
  .prob-label {{
    font-size: 9px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.4px;
    color: var(--small);
    width: 26px;
    flex-shrink: 0;
  }}
  .prob-track {{
    flex: 1;
    height: 5px;
    background: var(--surface-3);
    border-radius: 99px;
    overflow: hidden;
  }}
  .prob-fill {{
    height: 100%;
    border-radius: 99px;
    transition: width 0.3s ease;
  }}
  .prob-model {{ background: var(--orange); }}
  .prob-mkt   {{ background: var(--muted); }}
  .prob-val {{
    font-size: 11px;
    font-weight: 600;
    color: var(--muted);
    font-variant-numeric: tabular-nums;
    width: 34px;
    text-align: right;
    flex-shrink: 0;
  }}

  /* ── Stats grid ──────────────────────────────────────────── */
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
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--small);
  }}
  .stat-value {{
    font-size: 14px;
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    color: var(--text);
  }}

  /* ── Signal pill ─────────────────────────────────────────── */
  .signal-pill {{
    display: inline-flex;
    align-items: center;
    gap: 5px;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.6px;
    padding: 4px 10px 4px 7px;
    border-radius: 99px;
    margin-bottom: 9px;
    text-transform: uppercase;
  }}
  .signal-dot {{
    width: 5px;
    height: 5px;
    border-radius: 50%;
    flex-shrink: 0;
  }}
  .recommendation {{
    font-size: 11px;
    color: var(--muted);
    line-height: 1.5;
  }}

  /* ── Bookmaker odds toggle ───────────────────────────────── */
  .odds-details {{
    margin-top: 11px;
    border-top: 1px solid var(--border);
    padding-top: 9px;
  }}
  .odds-summary {{
    font-size: 11px;
    color: var(--small);
    cursor: pointer;
    list-style: none;
    display: flex;
    align-items: center;
    gap: 5px;
    user-select: none;
    transition: color 0.15s;
  }}
  .odds-summary::-webkit-details-marker {{ display: none; }}
  .odds-summary::before {{
    content: "▸";
    font-size: 8px;
    transition: transform 0.15s;
    display: inline-block;
    color: var(--small);
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
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--small);
    padding: 4px 6px;
    border-bottom: 1px solid var(--border);
    font-weight: 600;
  }}
  .odds-table td {{
    padding: 5px 6px;
    border-bottom: 1px solid rgba(36,36,36,0.6);
    font-variant-numeric: tabular-nums;
  }}
  .odds-table tr:last-child td {{ border-bottom: none; }}
  .odds-table tr:hover td {{ background: var(--surface-3); }}
  .bk-name    {{ color: var(--text); }}
  .bk-price   {{ color: var(--muted); font-weight: 500; }}
  .bk-implied {{ color: var(--small); }}

  /* ── Error / empty states ────────────────────────────────── */
  .match-error {{ border-color: rgba(55,65,81,0.6); }}
  .error-msg {{
    font-size: 12px;
    color: var(--amber);
    margin-top: 6px;
    padding: 8px 12px;
    background: rgba(245,158,11,0.06);
    border-radius: 6px;
    border: 1px solid rgba(245,158,11,0.15);
  }}
  .empty-state {{
    text-align: center;
    padding: 72px 24px;
    border: 1px solid var(--border);
    border-radius: 16px;
    margin-top: 24px;
    background: var(--surface);
  }}
  .empty-icon {{
    font-size: 28px;
    color: var(--small);
    margin-bottom: 16px;
    opacity: 0.6;
  }}
  .empty-title {{
    font-size: 15px;
    font-weight: 600;
    color: var(--text);
    margin-bottom: 8px;
    letter-spacing: -0.2px;
  }}
  .empty-body {{
    font-size: 13px;
    color: var(--muted);
    max-width: 360px;
    margin: 0 auto;
    line-height: 1.6;
  }}

  /* ── Parlays section ────────────────────────────────────── */
  .parlays-section {{
    margin-bottom: 24px;
    border: 1px solid var(--border);
    border-radius: 12px;
    overflow: hidden;
    background: var(--surface);
  }}
  .parlays-summary {{
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 14px 18px;
    cursor: pointer;
    list-style: none;
    user-select: none;
    transition: background 0.15s;
  }}
  .parlays-summary::-webkit-details-marker {{ display: none; }}
  .parlays-summary:hover {{ background: var(--surface-2); }}
  .parlays-title {{
    font-size: 13px;
    font-weight: 700;
    color: var(--text);
    letter-spacing: -0.1px;
  }}
  .parlays-count {{
    font-size: 12px;
    color: var(--muted);
  }}
  .parlays-chevron {{
    margin-left: auto;
    font-size: 10px;
    color: var(--small);
    transition: transform 0.2s;
    display: inline-block;
  }}
  details[open] .parlays-chevron {{ transform: rotate(90deg); }}
  .parlays-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
    gap: 12px;
    padding: 0 16px 16px;
  }}
  .parlay-card {{
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 14px;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }}
  .parlay-card-header {{
    display: flex;
    align-items: center;
    justify-content: space-between;
  }}
  .parlay-legs {{
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--muted);
  }}
  .parlay-header-right {{
    display: flex;
    align-items: center;
    gap: 8px;
  }}
  .parlay-odds {{
    font-size: 18px;
    font-weight: 700;
    color: var(--orange);
    font-variant-numeric: tabular-nums;
    letter-spacing: -0.5px;
  }}
  .parlay-stake-odds {{
    font-size: 14px;
    font-weight: 700;
    color: #00a86b;
    font-variant-numeric: tabular-nums;
    background: rgba(0,168,107,0.12);
    border: 1px solid rgba(0,168,107,0.30);
    border-radius: 5px;
    padding: 2px 6px;
  }}
  .risk-badge {{
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.6px;
    padding: 2px 7px;
    border-radius: 99px;
    text-transform: uppercase;
  }}
  .parlay-picks {{
    display: flex;
    flex-direction: column;
    gap: 5px;
  }}
  .parlay-pick {{
    display: flex;
    flex-direction: column;
    gap: 1px;
    padding: 6px 8px;
    background: var(--surface-3);
    border-radius: 6px;
  }}
  .parlay-pick-name {{
    font-size: 12px;
    font-weight: 600;
    color: var(--text);
  }}
  .parlay-pick-meta {{
    font-size: 11px;
    color: var(--muted);
    font-variant-numeric: tabular-nums;
  }}
  .parlay-footer {{
    display: flex;
    flex-direction: column;
    gap: 5px;
    padding-top: 6px;
    border-top: 1px solid var(--border);
  }}
  .rating-row {{
    display: flex;
    align-items: center;
    gap: 8px;
  }}
  .rating-label {{
    font-size: 9px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    color: var(--small);
    width: 40px;
    flex-shrink: 0;
  }}
  .rating-track {{
    flex: 1;
    height: 5px;
    background: var(--surface-3);
    border-radius: 99px;
    overflow: hidden;
  }}
  .rating-fill {{
    height: 100%;
    border-radius: 99px;
  }}
  .rating-val {{
    font-size: 11px;
    font-weight: 700;
    color: var(--text);
    width: 30px;
    text-align: right;
    flex-shrink: 0;
    font-variant-numeric: tabular-nums;
  }}
  .parlay-cum-prob {{
    font-size: 11px;
    color: var(--small);
  }}
  .parlay-cum-prob strong {{ color: var(--muted); }}
  .parlay-summary {{
    font-size: 11px;
    color: var(--muted);
    line-height: 1.5;
    font-style: italic;
    padding-top: 2px;
  }}

  /* ── Stake odds badge ────────────────────────────────────── */
  .stake-badge {{
    display: inline-flex;
    align-items: center;
    gap: 5px;
    background: rgba(0,168,107,0.10);
    border: 1px solid rgba(0,168,107,0.30);
    border-radius: 6px;
    padding: 4px 8px;
    margin: 4px 0 6px;
    font-size: 12px;
    font-weight: 600;
  }}
  .stake-logo {{
    width: 16px;
    height: 16px;
    background: #00a86b;
    border-radius: 3px;
    color: #fff;
    font-size: 10px;
    font-weight: 800;
    display: flex;
    align-items: center;
    justify-content: center;
    flex-shrink: 0;
  }}
  .stake-label {{ color: #00a86b; }}
  .stake-price {{
    color: #fff;
    background: #00a86b;
    border-radius: 4px;
    padding: 1px 6px;
    font-size: 12px;
    font-weight: 700;
    font-variant-numeric: tabular-nums;
  }}

  /* ── Withdrawal alert ───────────────────────────────────── */
  .withdrawal-alert {{
    display: flex;
    align-items: flex-start;
    gap: 8px;
    background: rgba(248,113,113,0.08);
    border: 1px solid rgba(248,113,113,0.35);
    border-radius: 6px;
    padding: 9px 12px;
    margin-bottom: 10px;
    font-size: 12px;
    color: #f87171;
    line-height: 1.45;
  }}
  .withdrawal-alert strong {{ font-weight: 700; }}
  .withdrawal-icon {{
    font-size: 14px;
    flex-shrink: 0;
    margin-top: 1px;
  }}

  /* ── Safe Parlays — Daily Compounder ─────────────────────── */
  .safe-parlays-section {{ margin-top: 8px; }}
  .safe-parlays-intro {{
    font-size: 11px;
    color: var(--small);
    padding: 8px 16px 4px;
    line-height: 1.6;
  }}
  .safe-parlays-intro strong {{ color: var(--muted); }}
  .today-pick-badge {{
    display: inline-block;
    font-size: 9px;
    font-weight: 700;
    letter-spacing: 0.5px;
    color: #fff;
    background: var(--orange);
    border-radius: 4px;
    padding: 1px 6px;
    vertical-align: middle;
    margin-left: 6px;
  }}
  .safe-today-pick {{
    border-color: var(--orange) !important;
    box-shadow: 0 0 0 1px rgba(249,115,22,0.20);
  }}

  /* ── Footer ──────────────────────────────────────────────── */
  footer {{
    border-top: 1px solid var(--border);
    padding: 18px 24px;
    font-size: 11px;
    color: var(--small);
    text-align: center;
    line-height: 1.8;
  }}
  footer a {{ color: var(--muted); text-decoration: none; transition: color 0.15s; }}
  footer a:hover {{ color: var(--text); }}
</style>
</head>
<body>

<header>
  <div class="site-title">
    <div class="logo-mark">tm</div>
    the model
  </div>
  <div class="header-right">
    <span class="header-tag">ATP · Pre-match</span>
    <span class="updated">Updated {now_utc}</span>
  </div>
</header>

<main>
  {summary_html}
  {parlays_html}
  {safe_parlays_html}
  {track_record_html}
  {content}
</main>

<footer>
  Pre-match predictions only &nbsp;·&nbsp;
  Model: logistic regression (63.7% CV) &nbsp;·&nbsp;
  Not financial or betting advice &nbsp;·&nbsp;
  <a href="https://github.com/elouelyt/the-model" target="_blank">Source ↗</a>
</footer>

</body>
</html>
"""


def main() -> None:
    if not os.getenv("THE_ODDS_API_KEY"):
        logger.error("THE_ODDS_API_KEY is not set. Aborting.")
        sys.exit(1)

    results = None
    parlays: list[dict] = []
    safe_parlays: list[dict] = []
    error = None

    try:
        results, parlays, safe_parlays = run_pipeline()
    except Exception as exc:
        logger.error("Pipeline failed: %s", exc, exc_info=True)
        error = str(exc)

    # Save today's predictions for track record (skip if file already exists)
    if parlays:
        _save_predictions(parlays)

    track_record = _load_track_record()
    _inject_all_predictions(track_record)  # inject any predictions file not yet in track_record
    _save_track_record(track_record)       # persist so check_results.py can add won/lost
    html = generate_html(results, parlays=parlays, safe_parlays=safe_parlays, error=error, track_record=track_record)
    out = Path("index.html")
    out.write_text(html, encoding="utf-8")
    logger.info("Written %s (%d bytes)", out, len(html))


def _save_predictions(parlays: list[dict]) -> None:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    preds_dir = Path("data/predictions")
    preds_dir.mkdir(parents=True, exist_ok=True)
    pred_file = preds_dir / f"{today}.json"
    if pred_file.exists():
        logger.info("Predictions for %s already saved — skipping overwrite", today)
        return
    payload = {
        "date": today,
        "parlays": [
            {
                "picks": [{"player": p["player"], "rank": p["rank"], "tournament": p.get("sport_title", "")} for p in parl["picks"]],
                "stake_total_odds": parl.get("stake_total_odds"),
                "total_odds": parl.get("total_odds"),
                "cum_prob": parl.get("cum_prob"),
                "rating": parl.get("rating"),
            }
            for parl in parlays
        ],
    }
    pred_file.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Saved predictions to %s", pred_file)


def _load_track_record() -> dict:
    track_file = Path("data/track_record.json")
    if track_file.exists():
        try:
            return json.loads(track_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"months": {}}


def _save_track_record(track_record: dict) -> None:
    track_file = Path("data/track_record.json")
    track_file.parent.mkdir(parents=True, exist_ok=True)
    track_file.write_text(json.dumps(track_record, indent=2, ensure_ascii=False), encoding="utf-8")


def _inject_all_predictions(track_record: dict) -> None:
    """Scan all data/predictions/*.json files and add any missing days as pending entries.

    Preserves won/lost outcomes already set by check_results.py.
    Skips days that are already fully resolved.
    Deduplicates parlays: if the same leg-set appeared in a previous day, it's stale API data
    (player already eliminated but still showing in odds) and is excluded from the new day.
    """
    preds_dir = Path("data/predictions")
    if not preds_dir.exists():
        return

    # Track leg-sets already seen in earlier days to detect stale API duplicates
    seen_leg_sets: set[frozenset] = set()

    # Pre-populate seen_leg_sets from existing track_record data (before scanning new files)
    for month_data in track_record.get("months", {}).values():
        for day_data in month_data.get("days", {}).values():
            for parl in day_data.get("parlays", []):
                seen_leg_sets.add(frozenset(parl["legs"]))

    for pred_file in sorted(preds_dir.glob("*.json")):
        try:
            pred = json.loads(pred_file.read_text(encoding="utf-8"))
        except Exception:
            continue
        day_str = pred.get("date")
        if not day_str:
            continue
        month_str = day_str[:7]
        day_key = str(int(day_str[8:10]))
        track_record.setdefault("months", {}).setdefault(month_str, {"days": {}})
        existing = track_record["months"][month_str]["days"].get(day_key, {})
        if existing.get("resolved"):
            # Still register its leg-sets as seen so later days can detect duplicates
            for parl in existing.get("parlays", []):
                seen_leg_sets.add(frozenset(parl["legs"]))
            continue
        if existing.get("parlays"):
            for parl in existing.get("parlays", []):
                seen_leg_sets.add(frozenset(parl["legs"]))
            continue  # already has pending data (possibly with partial won/lost from check_results)

        parlays = pred.get("parlays", [])
        if not parlays:
            continue

        # Filter out parlays whose exact leg-set already appeared in a previous day
        new_parlays = []
        for parl in parlays:
            legs = [p["player"] for p in parl.get("picks", [])]
            key = frozenset(legs)
            if key in seen_leg_sets:
                logger.info("Skipping duplicate parlay %s (same legs seen on earlier day)", legs)
                continue
            new_parlays.append({
                "legs": legs,
                "stake_odds": parl.get("stake_total_odds"),
                "best_odds": parl.get("total_odds"),
                "won": None,
            })
            seen_leg_sets.add(key)

        if not new_parlays:
            logger.info("Day %s has no unique parlays after deduplication — skipping", day_str)
            continue

        track_record["months"][month_str]["days"][day_key] = {
            "parlays": new_parlays,
            "resolved": False,
        }


if __name__ == "__main__":
    main()
