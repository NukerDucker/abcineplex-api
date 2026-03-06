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


def calc_demand_badge(available_seats: int, total_seats: int) -> dict:
    """Compute demand badge from seat availability.

    Returns badge slug and display label.
    """
    if total_seats == 0:
        return {"demand_badge": "available", "badge_label": None, "seats_remaining_percent": 0.0}

    pct = (available_seats / total_seats) * 100

    if pct < 15:
        badge = "selling_fast"
        label = "Selling Fast! 🔥"
    elif pct < 40:
        badge = "filling_up"
        label = "Filling Up"
    elif pct <= 80:
        badge = "available"
        label = None  # no badge shown for normal availability
    else:
        badge = "plenty_of_space"
        label = "Plenty of Space 🎉"

    return {
        "demand_badge": badge,
        "badge_label": label,
        "seats_remaining_percent": round(pct, 1),
    }


def calc_consensus_score(
    avg_user_rating: float,
    total_bookings: int,
    bookings_scale: int = 2000,
    weight_rating: float = 0.6,
    weight_bookings: float = 0.4,
) -> float:
    """Consensus AI Top Picks score (0–100).

    Combines normalised user rating and booking volume into a single score:
        rating_norm   = (avg_user_rating / 5.0) * 100
        bookings_norm = min((total_bookings / bookings_scale) * 100, 100)
        score         = rating_norm * w_r + bookings_norm * w_b
    """
    if avg_user_rating <= 0 and total_bookings <= 0:
        return 0.0
    rating_norm = (avg_user_rating / 5.0) * 100
    bookings_norm = min((total_bookings / bookings_scale) * 100, 100)
    return round((rating_norm * weight_rating) + (bookings_norm * weight_bookings), 2)


def calc_ttc(
    runtime_minutes: int,
    credits_minutes: int = 5,
    travel_minutes: int = TTC_TRAVEL_MIN,
) -> int:
    """Total Time Commitment in minutes.

    TTC = travel_to + pre_show_ads + runtime + credits + travel_from
    """
    return travel_minutes + TTC_PRE_SHOW_MIN + runtime_minutes + credits_minutes + travel_minutes
