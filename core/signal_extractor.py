"""
Signal Extraction Engine — ReviewInsightEngine
================================================
Rule-based signal enrichment layer. Processes each parsed review to extract
structured signals (polarity, urgency, churn intent, expansion opportunity,
feature specificity) WITHOUT any AI involvement.

These signals are then aggregated per theme and fed into the AI scoring model
as structured inputs — never raw text.

Integrates with:
  - core/analyzer.py parsed review dicts as input
  - core/ai_engine.py score_themes() as the consumer of aggregated signals
  - config/settings.py for keyword lists
"""

import re
from collections import defaultdict
from config.settings import (
    URGENCY_KEYWORDS,
    CHURN_KEYWORDS,
    EXPANSION_KEYWORDS,
    TAXONOMY,
)


# ── Feature Name Detection ───────────────────────────────────────────────────
# Heuristic patterns that indicate a review mentions a concrete, named feature
# rather than a vague complaint. Integrates with: extract_signals.
_FEATURE_PATTERNS = [
    re.compile(r"\b(api|sdk|integration|export|import|webhook|sso|oauth)\b", re.I),
    re.compile(r"\b(dashboard|dark mode|search|filter|sort|notification)\b", re.I),
    re.compile(r"\b(mobile app|android|ios|desktop|chrome extension)\b", re.I),
    re.compile(r"\b(slack|jira|salesforce|hubspot|zapier|stripe|github)\b", re.I),
    re.compile(r"\b(csv|pdf|excel|report|chart|graph|analytics)\b", re.I),
]


def _has_concrete_feature(text_lower: str) -> bool:
    """Check if text mentions a specific, named feature or integration."""
    return any(p.search(text_lower) for p in _FEATURE_PATTERNS)


def _match_keyword_count(text_lower: str, keywords: list[str]) -> tuple[int, list[str]]:
    """Count how many keywords from a list appear in the text. Returns (count, matched)."""
    matched = [kw for kw in keywords if kw in text_lower]
    return len(matched), matched


def _polarity_from_rating(rating: float | None, scale: int = 5) -> float:
    """
    Convert a numeric rating to a polarity score on [-1.0, +1.0].
    Linear mapping: min of scale → -1.0, mid → 0.0, max → +1.0.
    """
    if rating is None:
        return 0.0
    mid = (1 + scale) / 2.0
    half_range = (scale - 1) / 2.0
    if half_range == 0:
        return 0.0
    return round(max(-1.0, min(1.0, (rating - mid) / half_range)), 3)


def _polarity_from_sentiment(sentiment: str) -> float:
    """Fallback polarity when no numeric rating is available."""
    return {"Positive": 0.7, "Neutral": 0.0, "Negative": -0.7}.get(sentiment, 0.0)


# ── Main Extraction ──────────────────────────────────────────────────────────

def extract_signals(
    parsed_reviews: list[dict],
    segment_weights: dict[str, float] | None = None,
    rating_scale: int = 5,
) -> list[dict]:
    """
    Enrich each parsed review dict with structured signal fields.

    Args:
        parsed_reviews: list of dicts from Analyzer parsing (must have 'text',
                        'rating', 'sentiment', 'category' keys).
        segment_weights: optional mapping of segment name → weight multiplier
                         (e.g. {"enterprise": 10, "pro": 3, "free": 1}).
        rating_scale: the detected rating scale (5 or 10).

    Returns:
        The same list, with each dict enriched with:
          polarity_score, urgency_flags, urgency_score, feature_specificity,
          churn_signal, expansion_signal, segment_weight.
    """
    for review in parsed_reviews:
        text_lower = review["text"].strip().lower()

        # 1. Polarity score (-1 to +1)
        if review.get("rating") is not None:
            review["polarity_score"] = _polarity_from_rating(review["rating"], rating_scale)
        else:
            review["polarity_score"] = _polarity_from_sentiment(review.get("sentiment", "Neutral"))

        # 2. Urgency detection
        urg_count, urg_matched = _match_keyword_count(text_lower, URGENCY_KEYWORDS)
        review["urgency_flags"] = urg_matched
        review["urgency_score"] = round(min(1.0, urg_count / max(1, len(URGENCY_KEYWORDS) * 0.1)), 3)

        # 3. Churn signal
        churn_count, _ = _match_keyword_count(text_lower, CHURN_KEYWORDS)
        review["churn_signal"] = churn_count > 0

        # 4. Expansion signal
        exp_count, _ = _match_keyword_count(text_lower, EXPANSION_KEYWORDS)
        review["expansion_signal"] = exp_count > 0

        # 5. Feature specificity
        review["feature_specificity"] = "concrete" if _has_concrete_feature(text_lower) else "vague"

        # 6. Segment weight (default 1.0 if no segment data)
        review["segment_weight"] = 1.0
        if segment_weights and review.get("segment"):
            seg = review["segment"].strip().lower()
            for seg_name, weight in segment_weights.items():
                if seg_name.lower() == seg:
                    review["segment_weight"] = weight
                    break

    return parsed_reviews


# ── Theme-Level Aggregation ──────────────────────────────────────────────────

def aggregate_theme_signals(
    parsed_reviews: list[dict],
    total_reviews: int,
) -> dict[str, dict]:
    """
    Group enriched reviews by category and compute per-theme signal aggregates.

    Args:
        parsed_reviews: list of signal-enriched review dicts.
        total_reviews:  total number of reviews in the dataset.

    Returns:
        Dict keyed by category name, each value containing:
          volume, volume_pct, churn_signal_count, expansion_signal_count,
          avg_polarity, urgency_density, concrete_feature_ratio,
          avg_segment_weight, negative_count, positive_count, neutral_count.
    """
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in parsed_reviews:
        groups[r["category"]].append(r)

    aggregates: dict[str, dict] = {}
    for category, reviews in sorted(groups.items()):
        vol = len(reviews)
        churn_count = sum(1 for r in reviews if r.get("churn_signal"))
        expansion_count = sum(1 for r in reviews if r.get("expansion_signal"))
        avg_polarity = round(sum(r.get("polarity_score", 0) for r in reviews) / max(1, vol), 3)
        urgency_density = round(
            sum(r.get("urgency_score", 0) for r in reviews) / max(1, vol), 3
        )
        concrete_count = sum(1 for r in reviews if r.get("feature_specificity") == "concrete")
        avg_seg_weight = round(sum(r.get("segment_weight", 1.0) for r in reviews) / max(1, vol), 3)

        neg = sum(1 for r in reviews if r.get("sentiment") == "Negative")
        pos = sum(1 for r in reviews if r.get("sentiment") == "Positive")
        neu = vol - neg - pos

        aggregates[category] = {
            "volume": vol,
            "volume_pct": round(vol / max(1, total_reviews) * 100, 1),
            "churn_signal_count": churn_count,
            "expansion_signal_count": expansion_count,
            "avg_polarity": avg_polarity,
            "urgency_density": urgency_density,
            "concrete_feature_ratio": round(concrete_count / max(1, vol), 3),
            "avg_segment_weight": avg_seg_weight,
            "negative_count": neg,
            "positive_count": pos,
            "neutral_count": neu,
        }

    return aggregates
