"""Ranking-based win probability calculator using ATP points ratio."""

import logging

logger = logging.getLogger(__name__)


def blend_with_market(model_prob: float, raw_implied: float) -> float:
    """Blend model probability with market implied probability.

    The pure LR model (trained on ATP points/rank only) is systematically wrong
    for heavy favourites — it sees similar-ranked players as near 50/50 while the
    market correctly prices in form, surface specialisation, and recent results.

    This function gives the market progressively more weight as its conviction
    diverges from 0.5 (i.e. as the favourite becomes heavier):

        |raw_implied - 0.5| ≤ 0.10  → 0 % market weight (pure model)
        0.10 → 0.40 away from 0.5  → linear ramp up to 70 % market weight
        |raw_implied - 0.5| ≥ 0.40  → capped at 70 % market weight

    Concrete examples:
        raw_implied = 0.50  → 0 % market  (toss-up, trust the model)
        raw_implied = 0.65  → ~17 % market
        raw_implied = 0.75  → ~38 % market
        raw_implied = 0.82  → ~52 % market  (Jodar case: 51 % → 67 %)
        raw_implied = 0.90  → 70 % market   (cap)

    Args:
        model_prob: Raw output from the LR model (0–1).
        raw_implied: Average bookmaker raw implied probability (0–1).

    Returns:
        Blended probability (0–1).
    """
    conviction = max(0.0, (abs(raw_implied - 0.5) - 0.10) / 0.30)
    market_weight = min(0.70, conviction * 0.70)
    blended = (1.0 - market_weight) * model_prob + market_weight * raw_implied
    logger.debug(
        "blend_with_market: model=%.3f mkt=%.3f weight=%.2f → blended=%.3f",
        model_prob, raw_implied, market_weight, blended,
    )
    return blended


def calculate_win_probability(points_a: int, points_b: int) -> tuple[float, float]:
    """Calculate win probabilities for two players using ATP ranking points ratio.

    Uses the formula: P(A wins) = points_A / (points_A + points_B).
    This provides a baseline probability derived purely from official ATP
    ranking points, independent of bookmaker pricing.

    Args:
        points_a: ATP ranking points for player A.
        points_b: ATP ranking points for player B.

    Returns:
        A tuple of (prob_a, prob_b) where both values sum to 1.0.

    Raises:
        ValueError: If either points value is zero or negative.
    """
    if points_a <= 0 or points_b <= 0:
        raise ValueError(f"Points must be positive. Got: points_a={points_a}, points_b={points_b}")

    prob_a = points_a / (points_a + points_b)
    prob_b = 1.0 - prob_a

    logger.debug("Points ratio: %d vs %d → %.1f%% / %.1f%%", points_a, points_b, prob_a * 100, prob_b * 100)
    return prob_a, prob_b


def compare_with_bookmaker(
    model_prob: float,
    raw_implied: float,
    true_implied: float,
    player_name: str,
) -> dict:
    """Compare model probability against bookmaker pricing to identify value bets.

    The key threshold is ``raw_implied`` (1 / decimal_odds), not ``true_implied``.
    ``raw_implied`` is what the bookmaker actually pays out — it already includes
    their margin (vig). A bet only has positive expected value when:

        model_prob > raw_implied

    If model_prob > true_implied but <= raw_implied, the apparent edge exists in
    theory but is fully consumed by the vig — not a value bet.

    ``true_implied`` is included for transparency: it shows the vig-free market
    probability and helps the user understand how much margin the bookmaker
    is charging.

    Args:
        model_prob: Win probability from the ranking-based model (0–1).
        raw_implied: Average raw implied probability (1 / price) across bookmakers (0–1).
        true_implied: Average vig-removed implied probability across bookmakers (0–1).
        player_name: Player name for labelling the output.

    Returns:
        A dict with:
            - ``player``: player name
            - ``model_prob``: ranking-based model probability
            - ``raw_implied``: bookmaker raw implied probability (includes vig)
            - ``true_implied``: bookmaker vig-removed probability
            - ``vig_per_player``: estimated vig contribution (true_implied - raw_implied)
            - ``edge``: model_prob - raw_implied (positive = value bet)
            - ``signal``: ``"value_bet"``, ``"no_bet"``, or ``"marginal"``
            - ``recommendation``: plain-language betting advice
    """
    # Blend the raw model output with market conviction before computing edge.
    # This corrects systematic under/over-estimation for heavy favourites where
    # the LR model (points/rank only) disagrees strongly with the market.
    blended_prob = blend_with_market(model_prob, raw_implied)

    edge = blended_prob - raw_implied
    vig_per_player = true_implied - raw_implied

    if edge > 0.05:
        signal = "value_bet"
        recommendation = (
            f"Bet on {player_name}. Blended model gives {blended_prob:.1%} vs bookmaker raw price of "
            f"{raw_implied:.1%} — edge of {edge:.1%} survives the vig."
        )
    elif edge > 0:
        signal = "marginal"
        recommendation = (
            f"Marginal edge on {player_name} ({edge:.1%}). Blended model ({blended_prob:.1%}) barely "
            f"beats the raw price ({raw_implied:.1%}). Proceed with caution."
        )
    else:
        signal = "no_bet"
        recommendation = (
            f"No bet on {player_name}. Blended model ({blended_prob:.1%}) does not beat the "
            f"bookmaker's raw price ({raw_implied:.1%}). Vig would erase any edge."
        )

    return {
        "player": player_name,
        "model_prob": round(blended_prob, 4),
        "raw_implied": round(raw_implied, 4),
        "true_implied": round(true_implied, 4),
        "vig_per_player": round(vig_per_player, 4),
        "edge": round(edge, 4),
        "signal": signal,
        "recommendation": recommendation,
    }
