"""Unique feature calculations: RAQS and TTC."""
from datetime import date, datetime, timezone

# Tunable constants (can be moved to Settings if needed)
RAQS_C = 1500           # minimum-vote confidence constant
TTC_TRAVEL_MIN = 30     # default one-way travel time (minutes)
TTC_PRE_SHOW_MIN = 15   # fixed pre-show ads duration


def calc_raqs(rating: float, vote_count: int, release_date: date | None) -> float:
    """Risk-Adjusted Quality Score.

    Penalises high ratings with low vote counts and applies a mild recency
    factor.  Formula:
        confidence_weight = votes / (votes + C)
        recency_factor    = 1.0 | 0.95 | 0.90
        RAQS              = rating * confidence_weight * recency_factor
    """
    if not rating or rating <= 0:
        return 0.0

    confidence = vote_count / (vote_count + RAQS_C) if vote_count > 0 else 0.0

    recency = 1.0
    if release_date:
        today = date.today()
        months_old = (today.year - release_date.year) * 12 + (today.month - release_date.month)
        if months_old > 18:
            recency = 0.90
        elif months_old > 6:
            recency = 0.95

    return round(rating * confidence * recency, 2)


def calc_ttc(
    runtime_minutes: int,
    credits_minutes: int = 5,
    travel_minutes: int = TTC_TRAVEL_MIN,
) -> int:
    """Total Time Commitment in minutes.

    TTC = travel_to + pre_show_ads + runtime + credits + travel_from
    """
    return travel_minutes + TTC_PRE_SHOW_MIN + runtime_minutes + credits_minutes + travel_minutes
