"""Streamlit UI for the Tennis AI Prediction Engine.

Local demo for Sprint 3. Fetches live ATP pre-match odds, retrieves current
ATP rankings via Gemini Flash, computes ranking-based win probabilities, and
compares them against bookmaker pricing to surface value bets.

Run with: streamlit run app.py
"""

from datetime import datetime, timezone

import streamlit as st

from src.ingestion.extract_odds import fetch_odds
from src.processing.transform import flatten_odds, filter_upcoming
from src.agents.ranking_agent import fetch_atp_rankings
from src.agents.probability_calculator import calculate_win_probability, compare_with_bookmaker


st.set_page_config(page_title="Tennis AI Predictions", layout="centered")

st.title("Tennis AI Prediction Engine")
st.caption(
    "ATP match predictions — ranking-based model vs bookmaker odds. "
    "Pre-match only: in-play matches are excluded because live odds reflect "
    "current match state, not pre-match probability."
)

# --- Session state ---------------------------------------------------------
if "results" not in st.session_state:
    st.session_state.results = None
if "last_run" not in st.session_state:
    st.session_state.last_run = None

# --- Controls --------------------------------------------------------------
col_btn, col_meta = st.columns([3, 2])
with col_btn:
    run = st.button("Run Prediction Pipeline", type="primary", use_container_width=True)
with col_meta:
    if st.session_state.last_run:
        st.caption(f"Last fetched: {st.session_state.last_run}")

# --- Pipeline --------------------------------------------------------------
if run:
    try:
        with st.spinner("Fetching live ATP odds..."):
            data = fetch_odds()

        if not data:
            st.warning("No active ATP tournaments found. Try again when a tournament is active.")
            st.stop()

        df = flatten_odds(data)
        n_total = df["event_id"].nunique()
        df = filter_upcoming(df)
        n_filtered = n_total - df["event_id"].nunique()

        if df.empty:
            st.warning("All current matches are in progress. No pre-match odds available.")
            st.stop()

        players = df["outcome_name"].unique().tolist()

        with st.spinner(f"Fetching ATP rankings for {len(players)} players via Gemini..."):
            rankings = fetch_atp_rankings(player_names=players)

        # Build one result dict per match
        results = []
        for (event_id, home, away), group in df.groupby(["event_id", "home_team", "away_team"]):
            commence_time = group["commence_time"].iloc[0]
            missing = [p for p in [home, away] if p not in rankings]

            if missing:
                results.append({
                    "home": home,
                    "away": away,
                    "commence_time": commence_time,
                    "error": f"Rankings not found for: {', '.join(missing)}",
                })
                continue

            prob_home, prob_away = calculate_win_probability(
                rankings[home]["points"], rankings[away]["points"]
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
                players_data.append(rec)

            results.append({
                "home": home,
                "away": away,
                "commence_time": commence_time,
                "players": players_data,
            })

        st.session_state.results = results
        st.session_state.last_run = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        if n_filtered:
            st.info(
                f"{n_filtered} in-play match(es) excluded — "
                "live odds are not valid inputs for the ranking model."
            )

    except Exception as exc:
        st.error(f"Pipeline error: {exc}")

# --- Display ---------------------------------------------------------------
_SIGNAL_LABEL = {
    "value_bet": "VALUE BET",
    "marginal": "MARGINAL",
    "no_bet": "NO BET",
}

if st.session_state.results:
    st.divider()
    st.subheader(f"Predictions — {st.session_state.last_run}")

    for match in st.session_state.results:
        ct_str = match["commence_time"].strftime("%a %d %b · %H:%M UTC")

        with st.container(border=True):
            st.markdown(f"### {match['home']} vs {match['away']}")
            st.caption(ct_str)

            if "error" in match:
                st.warning(match["error"])
                continue

            col_home, col_away = st.columns(2)
            for col, p in zip([col_home, col_away], match["players"]):
                with col:
                    st.markdown(f"**{p['player']}**")
                    st.caption(f"Rank #{p['rank']} · {p['points']:,} pts")
                    # delta shows the edge (model prob minus bookmaker raw implied).
                    # Positive delta = model sees more value than the market prices in.
                    st.metric("Model prob", f"{p['model_prob']:.1%}")
                    st.metric(
                        "Bookmaker raw",
                        f"{p['raw_implied']:.1%}",
                        delta=f"{p['edge']:+.1%}",
                        delta_color="normal",
                    )
                    st.markdown(f"**{_SIGNAL_LABEL[p['signal']]}**")

            # Surface actionable recommendations below the player columns
            for p in match["players"]:
                if p["signal"] == "value_bet":
                    st.success(p["recommendation"])
                elif p["signal"] == "marginal":
                    st.warning(p["recommendation"])
