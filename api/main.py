"""FastAPI prediction API for the Tennis AI Platform.

Exposes GET /health and POST /predict endpoints. The predict endpoint runs
the full ATP pre-match prediction pipeline: fetches live odds, filters in-play
matches, retrieves current rankings via Gemini Flash, and returns model
probabilities vs bookmaker pricing with value signals.

Deploy to GCP Cloud Run. Secrets are injected as environment variables via
Cloud Run's Secret Manager integration — no .env file in the container image.

Run locally:
    uvicorn api.main:app --host 0.0.0.0 --port 8080 --reload
"""

import logging
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Security, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel

from src.agents.probability_calculator import calculate_win_probability, compare_with_bookmaker
from src.agents.ranking_agent import fetch_atp_rankings
from src.ingestion.extract_odds import fetch_odds
from src.processing.transform import filter_upcoming, flatten_odds

# no-op on Cloud Run (env vars injected by Secret Manager integration)
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s — %(levelname)s — %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# App + CORS
# ---------------------------------------------------------------------------

app = FastAPI(title="Tennis AI Prediction API", version="0.1.0")

# CORS origins configured via env var — wildcard acceptable locally,
# must be restricted to the frontend origin in production (Story 3).
_CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def _require_api_key(api_key: str = Security(_API_KEY_HEADER)) -> str:
    """Validate the X-API-Key request header against TENNIS_API_KEY env var.

    Args:
        api_key: Value from the X-API-Key header (injected by FastAPI).

    Returns:
        The validated API key string.

    Raises:
        HTTPException 503: If TENNIS_API_KEY is not configured on the server.
        HTTPException 401: If the provided key is missing or does not match.
    """
    expected = os.getenv("TENNIS_API_KEY")
    if not expected:
        logger.error("TENNIS_API_KEY is not configured — rejecting request.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API key not configured on server.",
        )
    if api_key != expected:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key.",
        )
    return api_key


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class PlayerPrediction(BaseModel):
    """Prediction for a single player within a match."""

    player: str
    rank: int
    points: int
    model_prob: float
    raw_implied: float
    true_implied: float
    vig_per_player: float
    edge: float
    signal: str  # "value_bet" | "marginal" | "no_bet"
    recommendation: str


class MatchPrediction(BaseModel):
    """Prediction for a single pre-match ATP event."""

    home: str
    away: str
    commence_time: datetime
    players: list[PlayerPrediction] | None = None
    error: str | None = None


class PredictResponse(BaseModel):
    """Full pipeline response returned by POST /predict."""

    fetched_at: str
    matches_total: int
    matches_filtered_inplay: int
    predictions: list[MatchPrediction]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
def health() -> dict:
    """Cloud Run liveness/readiness health check."""
    return {"status": "ok"}


@app.post("/predict", response_model=PredictResponse)
def predict(api_key: str = Depends(_require_api_key)) -> PredictResponse:
    """Run the full ATP pre-match prediction pipeline.

    Fetches live H2H odds from The-Odds-API, strips in-play matches, retrieves
    current ATP rankings via Gemini Flash, and computes ranking-based win
    probabilities against bookmaker raw implied probabilities.

    Args:
        api_key: Validated API key injected by the _require_api_key dependency.

    Returns:
        PredictResponse containing match-level predictions with value signals.

    Raises:
        HTTPException 503: If the odds API or ranking agent call fails.
        HTTPException 401: If the X-API-Key header is missing or invalid.
    """
    try:
        data = fetch_odds()
    except Exception as exc:
        logger.error("Odds fetch failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Odds API error: {exc}",
        )

    fetched_at = datetime.now(timezone.utc).isoformat()

    if not data:
        return PredictResponse(
            fetched_at=fetched_at,
            matches_total=0,
            matches_filtered_inplay=0,
            predictions=[],
        )

    df = flatten_odds(data)
    matches_total = df["event_id"].nunique()
    df = filter_upcoming(df)
    matches_filtered_inplay = matches_total - df["event_id"].nunique()

    if df.empty:
        return PredictResponse(
            fetched_at=fetched_at,
            matches_total=matches_total,
            matches_filtered_inplay=matches_filtered_inplay,
            predictions=[],
        )

    players = df["outcome_name"].unique().tolist()

    try:
        rankings = fetch_atp_rankings(player_names=players)
    except Exception as exc:
        logger.error("Rankings fetch failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Rankings agent error: {exc}",
        )

    predictions: list[MatchPrediction] = []
    for (event_id, home, away), group in df.groupby(["event_id", "home_team", "away_team"]):
        commence_time = group["commence_time"].iloc[0]
        missing = [p for p in [home, away] if p not in rankings]

        if missing:
            predictions.append(
                MatchPrediction(
                    home=home,
                    away=away,
                    commence_time=commence_time,
                    error=f"Rankings not found for: {', '.join(missing)}",
                )
            )
            continue

        prob_home, prob_away = calculate_win_probability(
            rankings[home]["points"], rankings[away]["points"]
        )

        players_data: list[PlayerPrediction] = []
        for player, model_prob in [(home, prob_home), (away, prob_away)]:
            rows = group[group["outcome_name"] == player]
            rec = compare_with_bookmaker(
                model_prob,
                rows["raw_implied"].mean(),
                rows["true_implied"].mean(),
                player,
            )
            players_data.append(
                PlayerPrediction(
                    **rec,
                    rank=rankings[player]["rank"],
                    points=rankings[player]["points"],
                )
            )

        predictions.append(
            MatchPrediction(
                home=home,
                away=away,
                commence_time=commence_time,
                players=players_data,
            )
        )

    return PredictResponse(
        fetched_at=fetched_at,
        matches_total=matches_total,
        matches_filtered_inplay=matches_filtered_inplay,
        predictions=predictions,
    )
