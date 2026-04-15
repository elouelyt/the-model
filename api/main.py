"""FastAPI prediction API for the Tennis AI Platform.

Exposes GET /health and POST /predict endpoints. The predict endpoint runs
the full ATP pre-match prediction pipeline via the LangGraph coordinator:
fetches live odds, filters in-play matches, retrieves ATP rankings, computes
LR model probabilities, surfaces H2H history, sentiment signals, and per-
bookmaker odds.

Deploy to GCP Cloud Run. Secrets are injected as environment variables via
Cloud Run's Secret Manager integration — no .env file in the container image.

Run locally:
    uvicorn api.main:app --host 0.0.0.0 --port 8080 --reload
"""

import logging
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request, Security, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security.api_key import APIKeyHeader
from pydantic import BaseModel
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

# no-op on Cloud Run (env vars injected by Secret Manager integration)
load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s — %(levelname)s — %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Rate limiter — 20 requests/minute per IP
# ---------------------------------------------------------------------------

limiter = Limiter(key_func=get_remote_address)


# ---------------------------------------------------------------------------
# App + CORS
# ---------------------------------------------------------------------------

app = FastAPI(title="Tennis AI Prediction API", version="0.2.0")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

_CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------

_API_KEY_HEADER = APIKeyHeader(name="X-API-Key", auto_error=False)


def _require_api_key(api_key: str = Security(_API_KEY_HEADER)) -> str:
    """Validate the X-API-Key request header against TENNIS_API_KEY env var.

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


class BookmakerOdds(BaseModel):
    """Per-bookmaker price and implied probability for one player."""

    bookmaker_title: str
    price: float
    raw_implied: float


class SentimentResult(BaseModel):
    """News sentiment signal for a player."""

    available: bool
    flag: str        # "positive" | "concern" | "neutral"
    label: str | None = None
    headline: str | None = None


class H2HResult(BaseModel):
    """Head-to-head historical record between two players."""

    available: bool
    total: int
    a_wins: int
    b_wins: int
    total_surface: int
    a_wins_surface: int
    b_wins_surface: int
    leader: str | None = None          # "a" | "b" | None (tied)
    leader_surface: str | None = None


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
    signal: str          # "value_bet" | "marginal" | "no_bet"
    recommendation: str
    sentiment: SentimentResult | None = None
    bookmakers: list[BookmakerOdds] = []


class MatchPrediction(BaseModel):
    """Prediction for a single pre-match ATP event."""

    home: str
    away: str
    commence_time: datetime
    surface: str = "hard"
    h2h: H2HResult | None = None
    players: list[PlayerPrediction] | None = None
    error: str | None = None


class PredictResponse(BaseModel):
    """Full pipeline response returned by POST /predict."""

    fetched_at: str
    matches_total: int
    predictions: list[MatchPrediction]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
def health() -> dict:
    """Cloud Run liveness/readiness health check."""
    return {"status": "ok", "version": "0.2.0"}


@app.post("/predict", response_model=PredictResponse)
@limiter.limit("20/minute")
def predict(request: Request, api_key: str = Depends(_require_api_key)) -> PredictResponse:
    """Run the full ATP pre-match prediction pipeline.

    Delegates to the LangGraph coordinator which executes:
      fetch_odds → fetch_rankings (retry ×2) → fetch_sentiment → compute_predictions

    Returns a structured response with match predictions including LR model
    probabilities, surface info, H2H history, sentiment signals, and per-
    bookmaker odds for each player.

    Rate limit: 20 requests/minute per IP.

    Raises:
        HTTPException 503: If the pipeline fails unexpectedly.
        HTTPException 401: If X-API-Key is missing or invalid.
        HTTPException 429: If the rate limit is exceeded.
    """
    from src.pipeline.coordinator import run_pipeline

    logger.info("POST /predict — running LangGraph pipeline")
    fetched_at = datetime.now(timezone.utc).isoformat()

    try:
        raw_results, _parlays, _safe_parlays = run_pipeline()
    except Exception as exc:
        logger.error("Pipeline failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Pipeline error: {exc}",
        )

    predictions: list[MatchPrediction] = []
    for match in raw_results:
        if "error" in match:
            predictions.append(
                MatchPrediction(
                    home=match["home"],
                    away=match["away"],
                    commence_time=match["commence_time"],
                    surface=match.get("surface", "hard"),
                    error=match["error"],
                )
            )
            continue

        h2h_raw = match.get("h2h", {})
        h2h = H2HResult(
            available=h2h_raw.get("available", False),
            total=h2h_raw.get("total", 0),
            a_wins=h2h_raw.get("a_wins", 0),
            b_wins=h2h_raw.get("b_wins", 0),
            total_surface=h2h_raw.get("total_surface", 0),
            a_wins_surface=h2h_raw.get("a_wins_surface", 0),
            b_wins_surface=h2h_raw.get("b_wins_surface", 0),
            leader=h2h_raw.get("leader"),
            leader_surface=h2h_raw.get("leader_surface"),
        ) if h2h_raw else None

        players_out: list[PlayerPrediction] = []
        for p in match.get("players", []):
            sent_raw = p.get("sentiment", {})
            players_out.append(
                PlayerPrediction(
                    player=p["player"],
                    rank=p["rank"],
                    points=p["points"],
                    model_prob=p["model_prob"],
                    raw_implied=p["raw_implied"],
                    true_implied=p["true_implied"],
                    vig_per_player=p["vig_per_player"],
                    edge=p["edge"],
                    signal=p["signal"],
                    recommendation=p["recommendation"],
                    sentiment=SentimentResult(
                        available=sent_raw.get("available", False),
                        flag=sent_raw.get("flag", "neutral"),
                        label=sent_raw.get("label"),
                        headline=sent_raw.get("headline"),
                    ) if sent_raw else None,
                    bookmakers=[
                        BookmakerOdds(**bk) for bk in p.get("bookmakers", [])
                    ],
                )
            )

        predictions.append(
            MatchPrediction(
                home=match["home"],
                away=match["away"],
                commence_time=match["commence_time"],
                surface=match.get("surface", "hard"),
                h2h=h2h,
                players=players_out,
            )
        )

    logger.info("POST /predict — returning %d matches", len(predictions))
    return PredictResponse(
        fetched_at=fetched_at,
        matches_total=len(predictions),
        predictions=predictions,
    )
