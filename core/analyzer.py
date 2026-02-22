"""
Deterministic Analysis Engine — ReviewInsightEngine
=====================================================
All classification, scoring, and prioritization is done here in Python,
with no AI involvement. Identical input always produces identical output.

Priority Formula:
  Priority Score = (Volume × 0.4) + (Avg Sentiment Impact × 0.35) + (Recency Weight × 0.25)

Sentiment Impact:
  Positive = 1.0,  Neutral = 0.5,  Negative = 0.0

Recency Weight:
  Last 30 days = 1.0,  Last 90 days = 0.75,  Older = 0.5,  No date = 0.5

Timeline buckets:
  ≥ 0.75 → Q1 – Immediate
  0.50–0.74 → Q2 – Near-term
  0.30–0.49 → Q3 – Mid-term
  < 0.30 → Q4 / Backlog

Confidence:
  > 20 mentions → High
  10–20 → Medium
  < 10 → Low
"""

# Standard library imports for regex, collection utilities, and date/time handling.
# Integrates with: Input parsing and sentiment trend calculation logic throughout this file.
import re
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Any

# Import of project-specific constants and configuration settings.
# Integrates with: core/analyzer.py logic for classification, sentiment detection, and column mapping.
from config.settings import TAXONOMY, SENTIMENT_KEYWORDS, RATING_COLUMNS, DATE_COLUMNS, COMMON_REVIEW_COLUMNS


# ── Helpers ──────────────────────────────────────────────────────────────────

# Function to standardise input text by stripping whitespace and converting to lowercase.
# Integrates with: All text-dependent matching functions like _classify_review and _derive_sentiment_from_text.
def _normalise(text: str) -> str:
    return text.strip().lower()


# Maps a single review to exactly one taxonomy category using keyword matching.
# Uses: _normalise for text formatting and TAXONOMY from settings.
# Integrates with: Analyzer.run to group reviews into logical categories for the product roadmap.
def _classify_review(text: str) -> str:
    """Map a review to exactly one taxonomy category deterministically.
    Keyword matching; ties broken alphabetically by category name."""
    # Standardise text for matching.
    text_lower = _normalise(text)
    scores: dict[str, int] = {}
    
    # Iterate through each category in the taxonomy to count keyword matches.
    for category, keywords in TAXONOMY.items():
        if category == "Other":
            continue
        count = sum(1 for kw in keywords if kw in text_lower)
        if count > 0:
            scores[category] = count
            
    # Default to "Other" if no keywords match.
    if not scores:
        return "Other"
        
    # Pick the category with the highest match count, tie-breaking alphabetically.
    max_score = max(scores.values())
    candidates = sorted([c for c, s in scores.items() if s == max_score])
    return candidates[0]  # alphabetical tie-break


# Determines sentiment label based strictly on keywords in the text.
# Uses: SENTIMENT_KEYWORDS from settings to identify Positive/Negative tone.
# Integrates with: Analyzer.run when a numeric rating column is absent in the input data.
def _derive_sentiment_from_text(text: str) -> str:
    """Keyword-based sentiment for reviews without a rating column."""
    # Lowercase text for uniform matching.
    text_lower = _normalise(text)
    # Check text against pre-defined lists of positive/negative keywords.
    for sentiment, keywords in SENTIMENT_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            return sentiment
    # Return Neutral if no strong sentiment keywords are detected.
    return "Neutral"


# Maps a numeric rating to a sentiment label based on the scale (e.g., 5-star vs 10-point).
# Integrates with: Analyzer.run parsing logic to provide consistent sentiment metrics from structured data.
def _derive_sentiment_from_rating(rating: float, scale: int) -> str:
    """Convert numeric rating to sentiment using fixed thresholds."""
    # Logic for standard 5-point scales.
    if scale <= 5:
        if rating < 3:
            return "Negative"
        elif rating == 3:
            return "Neutral"
        else:
            return "Positive"
    # Logic for 10-point or larger scales.
    else:  # 1–10 scale
        if rating < 5:
            return "Negative"
        elif rating <= 6:
            return "Neutral"
        else:
            return "Positive"


# Assigns a weight to a review based on how recently it was published.
# Integrates with: Priority Score calculation in Analyzer.run to ensure recent feedback is weighted more heavily.
def _recency_weight(date: datetime | None, now: datetime) -> float:
    # Use baseline weight if no date is available.
    if date is None:
        return 0.5
    # Calculate day difference from 'now'.
    delta = (now - date).days
    # High weight for last month, medium for last quarter, lower for older.
    if delta <= 30:
        return 1.0
    elif delta <= 90:
        return 0.75
    else:
        return 0.5


# Converts text labels into a numeric representation of impact.
# Integrates with: Aggregated scoring in Analyzer.run for ranking roadmap categories.
def _sentiment_impact(sentiment: str) -> float:
    # Positive gives full impact, Neutral middle, Negative zero impact.
    return {"Positive": 1.0, "Neutral": 0.5, "Negative": 0.0}.get(sentiment, 0.5)


# Generates a confidence label based on the volume of data points detected.
# Integrates with: The frontend roadmap UI and meta-reports to indicate statistical significance.
def _confidence_label(volume: int) -> str:
    # High confidence for large samples, Medium for moderate, Low for small samples.
    if volume > 20:
        return "High"
    elif volume >= 10:
        return "Medium"
    else:
        return "Low"


# Maps a priority score to a human-readable timeline bucket.
# Integrates with: The Product Roadmap UI component to group items into time horizons (Q1-Q4).
def _timeline_bucket(score: float) -> str:
    # High scores are immediate (Q1), decreasing scores move further out.
    if score >= 0.75:
        return "Q1 – Immediate"
    elif score >= 0.50:
        return "Q2 – Near-term"
    elif score >= 0.30:
        return "Q3 – Mid-term"
    else:
        return "Q4 / Backlog"


# Identifies the most likely column name for a given purpose (e.g., 'Review') from a list of strings.
# Integrates with: File parsing workflows in Analyzer.run to handle flexible CSV/XLSX schemas.
def _detect_column(columns: list[str], candidates: list[str]) -> str | None:
    """Find first column matching a candidate list (case-insensitive)."""
    # Create a lowercase list of column headers for case-insensitive comparison.
    col_lower = [c.strip().lower() for c in columns]
    # Check for exact case-insensitive matches against candidate names.
    for candidate in candidates:
        if candidate.lower() in col_lower:
            return columns[col_lower.index(candidate.lower())]
    # Fallback to partial matching if no exact match is found.
    for candidate in candidates:
        for i, col in enumerate(col_lower):
            if candidate.lower() in col:
                return columns[i]
    return None


# Identifies the rating column and automatically determines if it's a 5-point or 10-point scale.
# Integrates with: _derive_sentiment_from_rating to ensure sentiment thresholds are scale-aware.
def _detect_rating_column(df_columns: list[str], data: list[list]) -> tuple[str | None, int]:
    """Detect rating column and infer scale (5 or 10)."""
    # Use generic column detection to find the specific rating header.
    col = _detect_column(df_columns, RATING_COLUMNS)
    if col is None:
        return None, 5
    # Inspect the actual data rows to determine the maximum value (scale).
    col_idx = df_columns.index(col)
    vals = []
    for row in data:
        try:
            v = float(row[col_idx])
            vals.append(v)
        except (ValueError, TypeError, IndexError):
            pass
    if not vals:
        return col, 5
    # If any value exceeds 5, assume a 10-point scale; otherwise default to 5.
    scale = 10 if max(vals) > 5 else 5
    return col, scale


# ── Main Analyzer ─────────────────────────────────────────────────────────────

# Main entry point for the deterministic analysis engine.
# Integrates with: main.py API endpoint (/api/analyze) to process raw user uploads.
class Analyzer:
    # Executes the full analysis pipeline: Detection -> Parsing -> Categorization -> Scoring.
    # Integrates with: AIEngine and SynthesisEngine by providing the base data for narrative generation.
    def run(self, columns: list[str], data: list[list]) -> dict[str, Any]:
        """
        Deterministic analysis. Returns fully structured result dict.
        """
        # Capture current time for recency calculations.
        now = datetime.now(tz=timezone.utc)

        # 1. Automated Detection of relevant columns (Review, Rating, Date).
        # Integrates with: Input data mapping to ensure logic targets the correct text and metrics.
        review_col = _detect_column(columns, COMMON_REVIEW_COLUMNS)
        if review_col is None and columns:
            # Fallback: Treat the first column as the review text if no match is found.
            review_col = columns[0]

        rating_col, rating_scale = _detect_rating_column(columns, data)
        date_col = _detect_column(columns, DATE_COLUMNS)

        # Map column names to positional indices for faster row iteration.
        review_idx = columns.index(review_col) if review_col in columns else 0
        rating_idx = columns.index(rating_col) if rating_col and rating_col in columns else None
        date_idx = columns.index(date_col) if date_col and date_col in columns else None

        # 2. Iterate through data rows to parse text, ratings, and dates into structured dicts.
        # Uses: _derive_sentiment_from_rating, _derive_sentiment_from_text, _recency_weight, and _classify_review.
        # Integrates with: The aggregation step to provide clean objects for statistical processing.
        parsed: list[dict] = []
        for row in data:
            # Extract review text, skipping empty or invalid entries.
            text = str(row[review_idx]) if review_idx < len(row) else ""
            if not text or text.strip() in ("", "nan"):
                continue

            # Extract numeric rating if available.
            rating = None
            if rating_idx is not None and rating_idx < len(row):
                try:
                    rating = float(row[rating_idx])
                except (ValueError, TypeError):
                    pass

            # Determine sentiment using either the rating or a keyword scan of the text.
            sentiment = (
                _derive_sentiment_from_rating(rating, rating_scale)
                if rating is not None
                else _derive_sentiment_from_text(text)
            )

            # Extract and parse date strings into timezone-aware datetime objects.
            date: datetime | None = None
            if date_idx is not None and date_idx < len(row):
                try:
                    d = row[date_idx]
                    if d and str(d).strip():
                        import dateutil.parser
                        date = dateutil.parser.parse(str(d))
                        if date.tzinfo is None:
                            date = date.replace(tzinfo=timezone.utc)
                except Exception:
                    date = None

            # Categorise the review into a logical theme (e.g., UI, Performance).
            category = _classify_review(text)

            # Assemble the structured review object with calculated weights.
            parsed.append({
                "text": text,
                "rating": rating,
                "sentiment": sentiment,
                "date": date,
                "category": category,
                "recency_weight": _recency_weight(date, now),
                "sentiment_impact": _sentiment_impact(sentiment),
            })

        # Early exit if no data could be successfully processed.
        if not parsed:
            return {"error": "No valid reviews could be parsed."}

        # 3. Group the parsed reviews by their assigned categories for batch analysis.
        # Integrates with: Priority Score and Roadmap Item generation to compute metrics per theme.
        cat_groups: dict[str, list[dict]] = defaultdict(list)
        for p in parsed:
            cat_groups[p["category"]].append(p)

        # 4. Compute metrics and priority scores for each category to build the roadmap.
        # Uses: _confidence_label, _timeline_bucket, and _sentiment_impact (pre-calculated).
        # Integrates with: The frontend Roadmap card and the high-level executive summary.
        max_vol = max(len(v) for v in cat_groups.values()) or 1

        roadmap_items: list[dict] = []
        for category in sorted(cat_groups.keys()):
            reviews = cat_groups[category]
            volume = len(reviews)
            # Calculate averages for impacts and recency within this specific theme.
            avg_sentiment_impact = sum(r["sentiment_impact"] for r in reviews) / volume
            avg_recency = sum(r["recency_weight"] for r in reviews) / volume
            # Normalize volume relative to the largest category for fair scoring.
            norm_volume = volume / max_vol  # Normalise 0–1

            # The Core Priority Formula: Balances popularity, sentiment severity, and recency.
            # Integrates with: Business decision making and automated roadmap prioritization.
            priority_score = round(
                (norm_volume * 0.4) + (avg_sentiment_impact * 0.35) + (avg_recency * 0.25),
                2
            )
            # Count individual sentiment instances for chart visualizations.
            pos = sum(1 for r in reviews if r["sentiment"] == "Positive")
            neg = sum(1 for r in reviews if r["sentiment"] == "Negative")
            neu = sum(1 for r in reviews if r["sentiment"] == "Neutral")

            # Calculate average rating if numeric data was available.
            avg_rating = (
                round(sum(r["rating"] for r in reviews if r["rating"] is not None) /
                      max(1, sum(1 for r in reviews if r["rating"] is not None)), 2)
                if rating_col else None
            )

            # Assemble the final roadmap item with all necessary flags for the UI.
            roadmap_items.append({
                "category": category,
                "volume": volume,
                "sentiment_breakdown": {"Positive": pos, "Neutral": neu, "Negative": neg},
                "avg_rating": avg_rating,
                "priority_score": priority_score,
                "confidence": _confidence_label(volume),
                "timeline": _timeline_bucket(priority_score),
                "norm_volume": norm_volume,
            })

        # Ensure items are ordered by priority score (descending) so the most critical items appear first.
        roadmap_items.sort(key=lambda x: (-x["priority_score"], x["category"]))

        # Assign a numerical rank to each item for clear sequential reading.
        for i, item in enumerate(roadmap_items):
            item["rank"] = i + 1

        # 5. Extract verbatim quotes for the top 3 roadmap items to provide qualitative context.
        # Integrates with: The 'Verbatim Highlights' section of the UI to show 'the voice of the customer'.
        top_3_verbatims: list[dict] = []
        for item in roadmap_items[:3]:
            reviews = cat_groups[item["category"]]
            # Heuristic for the 'best' quotes: prioritize Negative (to see pain points) and longer text for detail.
            scored = sorted(
                reviews,
                key=lambda r: (
                    0 if r["sentiment"] == "Negative" else
                    1 if r["sentiment"] == "Neutral" else 2,
                    -len(r["text"])
                )
            )
            # Take the top 3 scored quotes for this category.
            quotes = []
            for r in scored[:3]:
                quotes.append({
                    "text": r["text"][:500],
                    "sentiment": r["sentiment"],
                    "rating": r["rating"],
                    "date": r["date"].strftime("%Y-%m-%d") if r["date"] else None,
                })
            top_3_verbatims.append({"category": item["category"], "quotes": quotes})

        # 6. Calculate total sentiment distribution across the entire dataset.
        # Integrates with: The global Sentiment Score donut chart on the dashboard.
        total = len(parsed)
        pos_total = sum(1 for r in parsed if r["sentiment"] == "Positive")
        neg_total = sum(1 for r in parsed if r["sentiment"] == "Negative")
        neu_total = total - pos_total - neg_total

        # 7. Aggregate sentiment trends over time into buckets (Monthly or Weekly).
        # Integrates with: The 'Sentiment Trend Over Time' line chart in the report.
        sentiment_trend = {}
        if date_col:
            dated = [r for r in parsed if r["date"] is not None]
            if dated:
                min_date = min(r["date"] for r in dated)
                max_date = max(r["date"] for r in dated)
                date_range_days = (max_date - min_date).days
                # Choose Monthly buckets for long ranges, Weekly for short ones.
                bucket_fmt = "%Y-%m" if date_range_days > 90 else "%Y-W%W"

                # Aggregate counts per bucket.
                buckets: dict[str, dict] = defaultdict(lambda: {"Positive": 0, "Neutral": 0, "Negative": 0})
                for r in dated:
                    key = r["date"].strftime(bucket_fmt)
                    buckets[key][r["sentiment"]] += 1

                # Format data for Chart.js (labels and data arrays).
                sorted_keys = sorted(buckets.keys())
                sentiment_trend = {
                    "labels": sorted_keys,
                    "positive": [buckets[k]["Positive"] for k in sorted_keys],
                    "neutral": [buckets[k]["Neutral"] for k in sorted_keys],
                    "negative": [buckets[k]["Negative"] for k in sorted_keys],
                }

        # 8. Risk detection: Identifies potential statistical biases or data quality issues.
        # Integrates with: The 'Potential Risks' warning panel in the UI to alert analysts of data skew.
        risks: list[str] = []
        # Check for categories with low mention counts.
        low_conf_cats = [i["category"] for i in roadmap_items if i["confidence"] == "Low"]
        if low_conf_cats:
            risks.append(
                f"Low data confidence in: {', '.join(low_conf_cats)}. "
                "These categories have fewer than 10 mentions and may be underrepresented."
            )

        # Check for extreme recency bias in the dataset.
        if date_col:
            dated = [r for r in parsed if r["date"] is not None]
            if dated:
                last_30 = sum(1 for r in dated if (now - r["date"]).days <= 30)
                if last_30 / max(1, len(dated)) > 0.7:
                    risks.append("Recency bias detected: over 70% of reviews are from the last 30 days.")

        # Check for rating ceiling/floor effects (responses clustered at extremes).
        if rating_col and total >= 5:
            ratings_all = [r["rating"] for r in parsed if r["rating"] is not None]
            if ratings_all:
                high = sum(1 for r in ratings_all if r >= (4 if rating_scale == 5 else 8))
                low = sum(1 for r in ratings_all if r <= (2 if rating_scale == 5 else 3))
                if high / len(ratings_all) > 0.8:
                    risks.append("Rating ceiling effect: over 80% of ratings are at the top of the scale.")
                if low / len(ratings_all) > 0.8:
                    risks.append("Rating floor effect: over 80% of ratings are at the bottom of the scale.")

        # Identify reviews that didn't match any specific taxonomy categories.
        unclassified = [r for r in parsed if r["category"] == "Other"]

        # 9. Extract the start and end dates of the processed review period.
        # Integrates with: The 'Analysis Period' badge in the report header.
        all_dated = [r for r in parsed if r["date"] is not None]
        date_range = None
        if all_dated:
            date_range = {
                "from": min(r["date"] for r in all_dated).strftime("%Y-%m-%d"),
                "to": max(r["date"] for r in all_dated).strftime("%Y-%m-%d"),
            }

        # 10. Identify the top 3 themes by mentions.
        # Integrates with: Executive summary and narrative prose generation.
        top_themes = [item["category"] for item in roadmap_items[:3]]

        # 11. Generate a descriptive table of the keywords used for categorization.
        # Integrates with: The 'Methodology' panel in the UI to explain how themes were mapped.
        keyword_table = [
            {"category": cat, "keywords": ", ".join(kws[:8])}
            for cat, kws in TAXONOMY.items()
            if cat != "Other"
        ]

        # Final assembly of the analysis report dictionary.
        # Integrates with: main.py response model and subsequent AIEngine and SynthesisEngine calls.
        return {
            "meta": {
                "total_reviews": total,
                "date_range": date_range,
                "top_themes": top_themes,
                "sentiment_distribution": {
                    "Positive": round(pos_total / total * 100, 1),
                    "Neutral": round(neu_total / total * 100, 1),
                    "Negative": round(neg_total / total * 100, 1),
                },
                "has_date_col": bool(date_col),
                "has_rating_col": bool(rating_col),
                "rating_scale": rating_scale if rating_col else None,
                "sentiment_source": "rating" if rating_col else "keyword",
                "unclassified_count": len(unclassified),
                "unclassified_samples": [r["text"][:100] for r in unclassified[:3]],
                "low_review_warning": total < 10,
            },
            "taxonomy_info": {
                "keyword_table": keyword_table,
                "priority_formula": "Priority Score = (Norm. Volume × 0.4) + (Avg Sentiment Impact × 0.35) + (Avg Recency Weight × 0.25)",
                "sentiment_scale": "Rating < 3 (or <5 on 10pt) = Negative; = 3 = Neutral; > 3 = Positive" if rating_col else "Keyword-based: see SENTIMENT_KEYWORDS in settings",
            },
            "sentiment_distribution": {
                "labels": ["Positive", "Neutral", "Negative"],
                "values": [pos_total, neu_total, neg_total],
            },
            "sentiment_trend": sentiment_trend,
            "roadmap_items": roadmap_items,
            "verbatim_quotes": top_3_verbatims,
            "risks": risks,
            # Structured summary specifically pruned for the LLM prompt to minimize token usage.
            # Integrates with: core/ai_engine.py narrative generation.
            "_for_ai": {
                "total": total,
                "top_themes": top_themes,
                "sentiment_distribution": {"Positive": pos_total, "Neutral": neu_total, "Negative": neg_total},
                "roadmap_summary": [
                    {"category": i["category"], "volume": i["volume"], "priority_score": i["priority_score"],
                     "timeline": i["timeline"], "sentiment": i["sentiment_breakdown"]}
                    for i in roadmap_items[:5]
                ],
                "risks": risks,
            }
        }
