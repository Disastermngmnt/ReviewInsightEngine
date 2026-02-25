"""
Deterministic Analysis Engine — ReviewInsightEngine (Dispatch v3.0)
=====================================================================
All classification, scoring, and prioritization is done here in Python,
with no AI involvement. Identical input always produces identical output.

Dispatch v3.0 Pre-computed Axes:
  Pain Intensity = (avg_rating_inverse × 0.5) + (urgency_rate × 0.3) + (churn_rate × 0.2)
  Impact Breadth = (unique_reviews / total_classified) × 10
  Urgency Velocity = velocity_ratio mapped to 0–10 (requires date data)

Timeline buckets (applied to Normalized Score = Priority Score / 10):
  ≥ 0.80 → Q1 – Ship Now
  0.60–0.79 → Q2 – Next Quarter
  0.40–0.59 → Q3 – Mid-term
  < 0.40 → Q4 / Backlog

Confidence:
  ≥ 20 unique reviews → High
  10–19 → Medium
  < 10 → Low ⚠
"""

import hashlib
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from config.settings import (
    TAXONOMY, SENTIMENT_KEYWORDS, RATING_COLUMNS, DATE_COLUMNS,
    COMMON_REVIEW_COLUMNS, URGENCY_KEYWORDS, CHURN_KEYWORDS,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _normalise(text: str) -> str:
    """Standardise input text for keyword matching."""
    return text.strip().lower()


def _hash_text(text: str) -> str:
    """SHA-256 hash of a review body — used for duplicate detection and quote integrity."""
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def _classify_review_with_counts(text: str, taxonomy: dict | None = None) -> tuple[str, dict[str, int]]:
    """
    Dispatch v3.0 multi-category conflict resolution.
    Returns (primary_category, {category: match_count}) for all matched categories.
    Tie-break: alphabetical by category name (deterministic).
    'Other' is returned only if no keywords match.
    """
    if taxonomy is None:
        taxonomy = TAXONOMY

    text_lower = _normalise(text)
    scores: dict[str, int] = {}

    for category, keywords in taxonomy.items():
        if category == "Other":
            continue
        count = sum(1 for kw in keywords if kw in text_lower)
        if count > 0:
            scores[category] = count

    if not scores:
        return "Other", {}

    max_score = max(scores.values())
    candidates = sorted([c for c, s in scores.items() if s == max_score])
    return candidates[0], scores


def _classify_review(text: str) -> str:
    """Simple classification wrapper — returns primary category only."""
    category, _ = _classify_review_with_counts(text)
    return category


def _derive_sentiment_from_text(text: str) -> str:
    """Keyword-based sentiment for reviews without a rating column."""
    text_lower = _normalise(text)
    for sentiment, keywords in SENTIMENT_KEYWORDS.items():
        if any(kw in text_lower for kw in keywords):
            return sentiment
    return "Neutral"


def _derive_sentiment_from_rating(rating: float, scale: int) -> str:
    """Convert numeric rating to sentiment using fixed thresholds."""
    if scale <= 5:
        if rating < 3:
            return "Negative"
        elif rating == 3:
            return "Neutral"
        else:
            return "Positive"
    else:
        if rating < 5:
            return "Negative"
        elif rating <= 6:
            return "Neutral"
        else:
            return "Positive"


def _recency_weight(date: datetime | None, now: datetime) -> float:
    """Weight a review by recency for AI signal context (not used in Dispatch scoring axes)."""
    if date is None:
        return 0.5
    delta = (now - date).days
    if delta <= 30:
        return 1.0
    elif delta <= 90:
        return 0.75
    else:
        return 0.5


def _sentiment_impact(sentiment: str) -> float:
    """Converts sentiment label to numeric impact for legacy score."""
    return {"Positive": 1.0, "Neutral": 0.5, "Negative": 0.0}.get(sentiment, 0.5)


def _confidence_label(volume: int) -> str:
    """Dispatch v3.0 confidence thresholds: ≥20 High, 10-19 Medium, <10 Low."""
    if volume >= 20:
        return "High"
    elif volume >= 10:
        return "Medium"
    else:
        return "Low ⚠"


def _timeline_bucket(normalized_score: float) -> str:
    """
    Dispatch v3.0 timeline assignment applied to Normalized Score (0–1).
    ≥ 0.80 → Q1 – Ship Now
    0.60–0.79 → Q2 – Next Quarter
    0.40–0.59 → Q3 – Mid-term
    < 0.40 → Q4 / Backlog
    """
    if normalized_score >= 0.80:
        return "Q1 – Ship Now"
    elif normalized_score >= 0.60:
        return "Q2 – Next Quarter"
    elif normalized_score >= 0.40:
        return "Q3 – Mid-term"
    else:
        return "Q4 / Backlog"


def _detect_column(columns: list[str], candidates: list[str]) -> str | None:
    """Find first column matching a candidate list (case-insensitive)."""
    col_lower = [c.strip().lower() for c in columns]
    for candidate in candidates:
        if candidate.lower() in col_lower:
            return columns[col_lower.index(candidate.lower())]
    for candidate in candidates:
        for i, col in enumerate(col_lower):
            if candidate.lower() in col:
                return columns[i]
    return None


def _detect_rating_column(df_columns: list[str], data: list[list]) -> tuple[str | None, int]:
    """Detect rating column and infer scale (5 or 10)."""
    col = _detect_column(df_columns, RATING_COLUMNS)
    if col is None:
        return None, 5
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
    scale = 10 if max(vals) > 5 else 5
    return col, scale


# ── Dispatch v3.0 Formula Helpers ─────────────────────────────────────────────

def _compute_pain_intensity(reviews: list[dict], rating_scale: int = 5) -> tuple[float, dict]:
    """
    Dispatch v3.0 Pain Intensity (0–10):
    Formula: (avg_rating_inverse × 0.5) + (urgency_language_rate × 0.3) + (churn_signal_rate × 0.2)
    avg_rating_inverse = (5 - avg_rating) / 4 × 10  [clamped to scale=5 reference]
    """
    total = len(reviews)
    if total == 0:
        return 0.0, {}

    rated = [r for r in reviews if r.get("rating") is not None]
    if rated:
        avg_rating = sum(r["rating"] for r in rated) / len(rated)
        # Normalise to 5-star reference for the Dispatch formula
        if rating_scale == 10:
            avg_rating_5 = avg_rating / 2.0
        else:
            avg_rating_5 = avg_rating
        avg_rating_inverse = ((5 - avg_rating_5) / 4) * 10
        avg_rating_inverse = max(0.0, min(10.0, avg_rating_inverse))
    else:
        avg_rating = None
        avg_rating_5 = None
        avg_rating_inverse = 5.0  # neutral default

    text_lower_list = [r["text"].strip().lower() for r in reviews]

    urgency_count = sum(
        1 for t in text_lower_list
        if any(kw in t for kw in URGENCY_KEYWORDS)
    )
    churn_count = sum(
        1 for t in text_lower_list
        if any(kw in t for kw in CHURN_KEYWORDS)
    )

    urgency_rate = urgency_count / total
    churn_rate = churn_count / total

    pain = (avg_rating_inverse * 0.5) + (urgency_rate * 10 * 0.3) + (churn_rate * 10 * 0.2)
    pain = round(max(0.0, min(10.0, pain)), 2)

    # Flag extremes
    extreme_flag = None
    if avg_rating_5 is not None and avg_rating_5 <= 1.5 and churn_rate > 0.20:
        extreme_flag = "[EXTREME — verify manually]"
    elif avg_rating is not None and avg_rating == (5.0 if rating_scale == 5 else 10.0) and urgency_count == 0 and churn_count == 0:
        extreme_flag = "[EXTREME — verify manually]"

    audit = {
        "avg_rating": round(avg_rating, 2) if avg_rating is not None else None,
        "avg_rating_5ref": round(avg_rating_5, 2) if avg_rating_5 is not None else None,
        "avg_rating_inverse": round(avg_rating_inverse, 2),
        "rated_reviews": len(rated),
        "urgency_count": urgency_count,
        "urgency_rate_pct": round(urgency_rate * 100, 1),
        "churn_count": churn_count,
        "churn_rate_pct": round(churn_rate * 100, 1),
        "formula": f"Pain: ({round(avg_rating_inverse,2)} × 0.5) + ({round(urgency_rate*10,2)} × 0.3) + ({round(churn_rate*10,2)} × 0.2)",
        "extreme_flag": extreme_flag,
    }
    return pain, audit


def _compute_impact_breadth(item_review_count: int, total_classified: int) -> tuple[float, str]:
    """
    Dispatch v3.0 Impact Breadth (0–10):
    Formula: (unique reviews for item / total classified reviews) × 10
    """
    if total_classified == 0:
        return 0.0, "Impact: 0.0 — 0 classified reviews"
    breadth = min(10.0, (item_review_count / total_classified) * 10)
    breadth = round(breadth, 2)
    pct = round(item_review_count / total_classified * 100, 1)
    audit = f"Impact: {breadth} — {item_review_count} of {total_classified} classified reviews ({pct}%)"
    return breadth, audit


def _compute_urgency_velocity(reviews: list[dict]) -> tuple[float | None, dict]:
    """
    Dispatch v3.0 Urgency Velocity (0–10) — requires date data.
    Split reviews at date midpoint; compare first vs second half mention counts.
    velocity_ratio = (second_half - first_half) / first_half
    Mapping: ratio > 0.20 → 8–10; -0.20 to 0.20 → 4–7; < -0.20 → 0–3
    Returns None if no date data is available.
    """
    dated = [r for r in reviews if r.get("date") is not None]
    if len(dated) < 2:
        return None, {"reason": "Insufficient date data — axis excluded"}

    dates = [r["date"] for r in dated]
    min_d = min(dates)
    max_d = max(dates)
    mid_d = min_d + (max_d - min_d) / 2

    first_half = [r for r in dated if r["date"] <= mid_d]
    second_half = [r for r in dated if r["date"] > mid_d]

    first_count = len(first_half)
    second_count = len(second_half)

    if first_count == 0:
        # All reviews in second half — treat as accelerating
        velocity_ratio = 1.0
    else:
        velocity_ratio = (second_count - first_count) / first_count

    # Map velocity_ratio to 0–10 score
    if velocity_ratio > 0.20:
        # Map linearly 8–10
        score = 8.0 + min(2.0, (velocity_ratio - 0.20) / 0.80 * 2.0)
    elif velocity_ratio >= -0.20:
        # Map linearly 4–7
        score = 4.0 + ((velocity_ratio + 0.20) / 0.40) * 3.0
    else:
        # Map linearly 0–3
        score = max(0.0, 3.0 + ((velocity_ratio + 0.20) / 0.20) * 3.0)

    score = round(max(0.0, min(10.0, score)), 2)
    change_pct = round(velocity_ratio * 100, 1)
    sign = "+" if change_pct >= 0 else ""

    audit = {
        "score": score,
        "first_half_count": first_count,
        "second_half_count": second_count,
        "first_half_range": f"{min_d.strftime('%Y-%m-%d')}–{mid_d.strftime('%Y-%m-%d')}",
        "second_half_range": f"{mid_d.strftime('%Y-%m-%d')}–{max_d.strftime('%Y-%m-%d')}",
        "change_pct": f"{sign}{change_pct}%",
        "velocity_ratio": round(velocity_ratio, 3),
    }
    return score, audit


# ── Pre-Flight Validation ──────────────────────────────────────────────────────

def run_preflight_checks(
    parsed: list[dict],
    raw_data: list[list],
    date_col_present: bool,
) -> dict:
    """
    Dispatch v3.0 Pre-Flight Validation (all 6 checks).
    Returns structured result dict with status per check.
    """
    total = len(parsed)
    checks = {}

    # CHECK 1 — Classification Coverage
    other_count = sum(1 for r in parsed if r["category"] == "Other")
    other_pct = round(other_count / max(1, total) * 100, 1)
    if other_pct < 15:
        cov_status = "PASS"
    elif other_pct <= 25:
        cov_status = "WARN"
    else:
        cov_status = "FAIL"
    checks["check_1_classification_coverage"] = {
        "status": cov_status,
        "other_count": other_count,
        "other_pct": other_pct,
        "threshold_warn": 15,
        "threshold_fail": 25,
        "message": f"Other category: {other_count} reviews ({other_pct}%)",
    }

    # CHECK 2 — Duplicate Review Detection
    hashes: dict[str, int] = {}
    for r in parsed:
        h = _hash_text(r["text"])
        hashes[h] = hashes.get(h, 0) + 1
    dup_count = sum(v - 1 for v in hashes.values() if v > 1)
    dup_pct = round(dup_count / max(1, total) * 100, 1)
    checks["check_2_duplicate_detection"] = {
        "status": "WARN" if dup_count > 0 else "PASS",
        "duplicates_found": dup_count,
        "duplicates_pct": dup_pct,
        "pre_dedup_count": total,
        "post_dedup_count": total - dup_count,
        "message": f"{dup_count} duplicates found ({dup_pct}% of total). Removed before scoring.",
    }

    # CHECK 3 — Quote Integrity (no duplicate quotes across categories)
    # Assign each quote text to its highest-confidence category only
    quote_hash_to_category: dict[str, str] = {}
    quote_conflicts = 0
    for r in parsed:
        h = _hash_text(r["text"])
        if h in quote_hash_to_category:
            if quote_hash_to_category[h] != r["category"]:
                quote_conflicts += 1
        else:
            quote_hash_to_category[h] = r["category"]
    checks["check_3_quote_integrity"] = {
        "status": "WARN" if quote_conflicts > 0 else "PASS",
        "conflict_count": quote_conflicts,
        "message": f"Quote assignment conflicts resolved: {quote_conflicts}",
    }

    # CHECK 4 — Sentiment Acceleration Alert (WoW comparison)
    acceleration_alert = None
    if date_col_present:
        dated = [r for r in parsed if r.get("date") is not None]
        if dated:
            max_date = max(r["date"] for r in dated)
            # Most recent week vs prior week
            week_start_current = max_date - __import__("datetime").timedelta(days=7)
            week_start_prior = max_date - __import__("datetime").timedelta(days=14)

            current_week = [r for r in dated if r["date"] >= week_start_current]
            prior_week = [r for r in dated if week_start_prior <= r["date"] < week_start_current]

            if current_week and prior_week:
                curr_neg_pct = sum(1 for r in current_week if r["sentiment"] == "Negative") / len(current_week) * 100
                prior_neg_pct = sum(1 for r in prior_week if r["sentiment"] == "Negative") / len(prior_week) * 100
                delta = curr_neg_pct - prior_neg_pct
                if delta > 15:
                    # Find top driving category for current week
                    cat_neg = defaultdict(int)
                    for r in current_week:
                        if r["sentiment"] == "Negative":
                            cat_neg[r["category"]] += 1
                    top_cat = max(cat_neg, key=cat_neg.get) if cat_neg else "Unknown"
                    acceleration_alert = {
                        "triggered": True,
                        "prior_neg_pct": round(prior_neg_pct, 1),
                        "current_neg_pct": round(curr_neg_pct, 1),
                        "delta": round(delta, 1),
                        "week_id": max_date.strftime("%Y-W%W"),
                        "top_driving_category": top_cat,
                        "top_cat_negative_count": cat_neg.get(top_cat, 0),
                    }

    checks["check_4_sentiment_acceleration"] = {
        "status": "ALERT" if acceleration_alert and acceleration_alert.get("triggered") else "PASS",
        "alert_data": acceleration_alert,
        "message": (
            f"ALERT: Negative sentiment increased from {acceleration_alert['prior_neg_pct']}% "
            f"to {acceleration_alert['current_neg_pct']}% (+{acceleration_alert['delta']}%) WoW"
            if acceleration_alert and acceleration_alert.get("triggered")
            else "No significant negative sentiment acceleration detected."
        ),
    }

    # CHECK 5 — Score Auditability (date data presence)
    checks["check_5_score_auditability"] = {
        "status": "WARN" if not date_col_present else "PASS",
        "has_date_data": date_col_present,
        "urgency_velocity_available": date_col_present,
        "weights_rebalanced": not date_col_present,
        "message": (
            "Date column detected — Urgency Velocity axis active."
            if date_col_present
            else "No date column — Urgency Velocity N/A. Weights rebalanced: Pain×0.375, Impact×0.3125, Strategic×0.1875, Effort×0.125 [No Velocity Axis]"
        ),
    }

    # CHECK 6 — Minimum Data Threshold
    non_other_total = sum(1 for r in parsed if r["category"] != "Other")
    low_conf_categories = []
    cat_counts: dict[str, int] = defaultdict(int)
    for r in parsed:
        if r["category"] != "Other":
            cat_counts[r["category"]] += 1
    for cat, cnt in cat_counts.items():
        if cnt < 10:
            low_conf_categories.append({"category": cat, "count": cnt})

    if non_other_total < 30:
        min_status = "WARN"
        min_msg = f"Only {non_other_total} classified reviews — results directional only. Minimum recommended: 30."
    else:
        min_status = "PASS"
        min_msg = f"{non_other_total} classified reviews — sufficient for analysis."

    checks["check_6_minimum_data"] = {
        "status": min_status,
        "classified_count": non_other_total,
        "watch_list_categories": low_conf_categories,
        "message": min_msg,
    }

    # Overall summary
    statuses = [v["status"] for v in checks.values()]
    passed = statuses.count("PASS")
    warned = statuses.count("WARN")
    failed = statuses.count("FAIL")
    alerted = statuses.count("ALERT")

    return {
        "checks": checks,
        "summary": {
            "passed": passed,
            "warned": warned,
            "failed": failed,
            "alerted": alerted,
            "halt": failed > 0,
            "display": f"{passed} passed / {warned} warned / {failed} failed / {alerted} alerted",
        },
    }


# ── Quote Selection (Dispatch v3.0) ────────────────────────────────────────────

def _select_quotes(reviews: list[dict], n: int = 3, used_hashes: set | None = None) -> list[dict]:
    """
    Dispatch v3.0 quote selection priority:
    1. Churn-signal language
    2. Urgency language
    3. Lowest star rating
    4. Most specific feature reference
    No quote may appear in more than one location (enforced via used_hashes).
    """
    if used_hashes is None:
        used_hashes = set()

    def _quote_priority(r: dict) -> tuple:
        text_lower = r["text"].strip().lower()
        has_churn = any(kw in text_lower for kw in CHURN_KEYWORDS)
        has_urgency = any(kw in text_lower for kw in URGENCY_KEYWORDS)
        rating = r.get("rating") or 5.0
        text_len = len(r["text"])
        # Lower tuple value = higher priority
        return (
            0 if has_churn else 1,       # churn first
            0 if has_urgency else 1,      # then urgency
            round(rating, 1),             # lower rating = higher priority
            -text_len,                    # longer = more specific
        )

    selected = []
    for r in sorted(reviews, key=_quote_priority):
        h = _hash_text(r["text"])
        if h in used_hashes:
            continue
        used_hashes.add(h)

        text_lower = r["text"].strip().lower()
        has_churn = any(kw in text_lower for kw in CHURN_KEYWORDS)
        has_urgency = any(kw in text_lower for kw in URGENCY_KEYWORDS)

        signal_type = "churn" if has_churn else ("urgency" if has_urgency else "low-rating")

        selected.append({
            "text": r["text"][:500],
            "sentiment": r.get("sentiment", "Neutral"),
            "rating": r.get("rating"),
            "date": r["date"].strftime("%Y-%m-%d") if r.get("date") else None,
            "signal_type": signal_type,
            "hash": h,
        })
        if len(selected) >= n:
            break

    return selected


# ── Main Analyzer ──────────────────────────────────────────────────────────────

class Analyzer:
    """
    Deterministic analysis engine — Dispatch v3.0 compliant.
    Integrates with: main.py API endpoint (/api/analyze).
    """

    def run(self, columns: list[str], data: list[list], custom_taxonomy: dict | None = None) -> dict[str, Any]:
        """
        Dispatch v3.0 deterministic analysis.
        Returns fully structured result dict including preflight checks,
        Dispatch axis scores, and deduplicated quote pools.
        """
        now = datetime.now(tz=timezone.utc)
        active_taxonomy = custom_taxonomy if custom_taxonomy else TAXONOMY

        # 1. Column detection
        review_col = _detect_column(columns, COMMON_REVIEW_COLUMNS)
        if review_col is None and columns:
            review_col = columns[0]

        rating_col, rating_scale = _detect_rating_column(columns, data)
        date_col = _detect_column(columns, DATE_COLUMNS)

        review_idx = columns.index(review_col) if review_col in columns else 0
        rating_idx = columns.index(rating_col) if rating_col and rating_col in columns else None
        date_idx = columns.index(date_col) if date_col and date_col in columns else None

        # 2. Parse rows
        parsed: list[dict] = []
        seen_hashes: set[str] = set()  # for duplicate detection
        for row in data:
            text = str(row[review_idx]) if review_idx < len(row) else ""
            if not text or text.strip() in ("", "nan"):
                continue

            rating = None
            if rating_idx is not None and rating_idx < len(row):
                try:
                    rating = float(row[rating_idx])
                except (ValueError, TypeError):
                    pass

            sentiment = (
                _derive_sentiment_from_rating(rating, rating_scale)
                if rating is not None
                else _derive_sentiment_from_text(text)
            )

            date: datetime | None = None
            if date_idx is not None and date_idx < len(row):
                try:
                    d = str(row[date_idx]).strip()
                    if d and d not in ("nan", ""):
                        col_name = columns[date_idx].strip().lower()
                        if col_name == "reviewed at":
                            # Strict parsing for specific schema, bypass dateutil fallback
                            date = datetime.strptime(d, '%Y-%m-%d %H:%M:%S')
                            if date.tzinfo is None:
                                date = date.replace(tzinfo=timezone.utc)
                        else:
                            # Primary: the exact ISO subset formatting
                            try:
                                date = datetime.strptime(d, '%Y-%m-%d %H:%M:%S')
                                if date.tzinfo is None:
                                    date = date.replace(tzinfo=timezone.utc)
                            except ValueError:
                                # Fallback
                                import dateutil.parser
                                date = dateutil.parser.parse(d)
                                if date.tzinfo is None:
                                    date = date.replace(tzinfo=timezone.utc)
                except Exception:
                    date = None

            # Multi-category classification with match counts
            category, match_counts = _classify_review_with_counts(text, taxonomy=active_taxonomy)
            review_hash = _hash_text(text)

            parsed.append({
                "text": text,
                "rating": rating,
                "sentiment": sentiment,
                "date": date,
                "category": category,
                "match_counts": match_counts,
                "recency_weight": _recency_weight(date, now),
                "sentiment_impact": _sentiment_impact(sentiment),
                "hash": review_hash,
                "is_duplicate": review_hash in seen_hashes,
            })
            seen_hashes.add(review_hash)

        if not parsed:
            return {"error": "No valid reviews could be parsed."}

        # 3. Deduplicate (keep first occurrence)
        deduped: list[dict] = []
        seen: set[str] = set()
        for r in parsed:
            if r["hash"] not in seen:
                deduped.append(r)
                seen.add(r["hash"])
        dup_removed = len(parsed) - len(deduped)

        total = len(deduped)

        # 4. Pre-flight validation
        preflight = run_preflight_checks(deduped, data, date_col_present=bool(date_col))

        # OTHER ELIMINATION (Dispatch v3.0) — Reclassify or noise
        for r in deduped:
            if r["category"] == "Other":
                text_lower = _normalise(r["text"])
                reclassified = False
                for cat, keywords in active_taxonomy.items():
                    if cat == "Other": continue
                    # Expanded signal matching: check partial matches from multi-word keywords
                    for kw in keywords:
                        kw_words = kw.split()
                        if len(kw_words) > 1 and any(w in text_lower for w in kw_words if len(w) > 4):
                            r["category"] = cat
                            reclassified = True
                            break
                    if reclassified: break
                if not reclassified:
                    r["category"] = "NOISE POOL"

        # 5. Group by category (excluding Other/NOISE from roadmap but keep for stats)
        cat_groups: dict[str, list[dict]] = defaultdict(list)
        for r in deduped:
            cat_groups[r["category"]].append(r)

        total_classified = sum(len(v) for k, v in cat_groups.items() if k not in ("Other", "NOISE POOL"))

        # Ensure all taxonomy categories are processed (Zero-Review block check)
        for cat in active_taxonomy.keys():
            if cat not in ("Other", "NOISE POOL") and cat not in cat_groups:
                cat_groups[cat] = []

        # 6. Compute Dispatch axes per category
        roadmap_items: list[dict] = []
        watch_list: list[dict] = []

        for category in sorted(cat_groups.keys()):
            if category in ("Other", "NOISE POOL"):
                continue  # Never appears in roadmap — Dispatch rule

            reviews = cat_groups[category]
            volume = len(reviews)
            
            if volume == 0:
                # ZERO-REVIEW SCORING BLOCK (Dispatch v3.0)
                watch_list.append({
                    "category": category,
                    "volume": 0,
                    "confidence": "None",
                    "message": "No reviews classified — cannot score. Expand taxonomy or collect more data before actioning.",
                    "sentiment_breakdown": {"Positive": 0, "Neutral": 0, "Negative": 0},
                    "avg_rating": None,
                    "churn_signal_count": 0,
                    "expansion_signal_count": 0,
                    "urgency_density": 0,
                    "pain_intensity_precomputed": None,
                    "impact_breadth_precomputed": None,
                    "urgency_velocity_precomputed": None
                })
                continue

            confidence = _confidence_label(volume)

            # Pain Intensity [F: Pain Intensity formula]
            pain_score, pain_audit = _compute_pain_intensity(reviews, rating_scale)

            # Impact Breadth [F: Impact Breadth formula]
            impact_score, impact_audit_str = _compute_impact_breadth(volume, total_classified)

            # Urgency Velocity [F: Urgency Velocity formula] or N/A
            velocity_score, velocity_audit = _compute_urgency_velocity(reviews)
            velocity_available = velocity_score is not None

            # Sentiment breakdown
            pos = sum(1 for r in reviews if r["sentiment"] == "Positive")
            neg = sum(1 for r in reviews if r["sentiment"] == "Negative")
            neu = volume - pos - neg

            avg_rating = (
                round(sum(r["rating"] for r in reviews if r["rating"] is not None) /
                      max(1, sum(1 for r in reviews if r["rating"] is not None)), 2)
                if rating_col else None
            )

            # Churn signal count for financial model
            churn_count = sum(
                1 for r in reviews
                if any(kw in r["text"].strip().lower() for kw in CHURN_KEYWORDS)
            )

            # Expansion signal count for financial model
            from config.settings import EXPANSION_KEYWORDS
            expansion_count = sum(
                1 for r in reviews
                if any(kw in r["text"].strip().lower() for kw in EXPANSION_KEYWORDS)
            )

            item_data = {
                "category": category,
                "volume": volume,
                "confidence": confidence,
                "message": f"Low volume ({volume}) — scores may be volatile." if volume < 10 else "Sufficient data",
                "sentiment_breakdown": {"Positive": pos, "Neutral": neu, "Negative": neg},
                "avg_rating": avg_rating,
                # Dispatch axes (pre-computed deterministically for AI context)
                "pain_intensity_precomputed": pain_score,
                "impact_breadth_precomputed": impact_score,
                "urgency_velocity_precomputed": velocity_score,
                "velocity_audit": velocity_audit,
                "pain_audit": pain_audit,
                "impact_audit": impact_audit_str,
                "velocity_available": velocity_available,
                # Financial model signals
                "churn_signal_count": churn_count,
                "expansion_signal_count": expansion_count,
                "urgency_density": round(
                    sum(1 for r in reviews if any(kw in r["text"].strip().lower() for kw in URGENCY_KEYWORDS)) / max(1, volume),
                    3
                ),
            }

            # Watch list for low-confidence categories
            if volume < 10:
                watch_list.append(item_data)
            else:
                roadmap_items.append(item_data)

        # 7. Legacy priority score (for initial sort before AI axes) — will be replaced by Dispatch scorer
        max_vol = max((len(cat_groups[c]) for c in cat_groups if c not in ("Other", "NOISE POOL")), default=1)
        for item in roadmap_items:
            vol = item["volume"]
            reviews = cat_groups[item["category"]]
            avg_si = sum(r["sentiment_impact"] for r in reviews) / max(1, vol)
            avg_rec = sum(r["recency_weight"] for r in reviews) / max(1, vol)
            norm_vol = vol / max_vol
            item["_legacy_priority"] = round((norm_vol * 0.4) + (avg_si * 0.35) + (avg_rec * 0.25), 2)

        roadmap_items.sort(key=lambda x: (-x["_legacy_priority"], x["category"]))
        for i, item in enumerate(roadmap_items):
            item["rank"] = i + 1

        # 8. Sentiment distribution
        pos_total = sum(1 for r in deduped if r["sentiment"] == "Positive")
        neg_total = sum(1 for r in deduped if r["sentiment"] == "Negative")
        neu_total = total - pos_total - neg_total

        # 9. Sentiment trend (weekly or monthly)
        sentiment_trend: dict = {}
        if date_col:
            dated = [r for r in deduped if r.get("date") is not None]
            if dated:
                min_date = min(r["date"] for r in dated)
                max_date = max(r["date"] for r in dated)
                date_range_days = (max_date - min_date).days
                bucket_fmt = "%Y-%m" if date_range_days > 90 else "%Y-W%W"

                buckets: dict[str, dict] = defaultdict(
                    lambda: {"Positive": 0, "Neutral": 0, "Negative": 0}
                )
                for r in dated:
                    key = r["date"].strftime(bucket_fmt)
                    buckets[key][r["sentiment"]] += 1

                sorted_keys = sorted(buckets.keys())
                sentiment_trend = {
                    "labels": sorted_keys,
                    "positive": [buckets[k]["Positive"] for k in sorted_keys],
                    "neutral": [buckets[k]["Neutral"] for k in sorted_keys],
                    "negative": [buckets[k]["Negative"] for k in sorted_keys],
                }

        # 10. Date range
        all_dated = [r for r in deduped if r.get("date") is not None]
        date_range = None
        if all_dated:
            date_range = {
                "from": min(r["date"] for r in all_dated).strftime("%Y-%m-%d"),
                "to": max(r["date"] for r in all_dated).strftime("%Y-%m-%d"),
            }

        # 11. Representative quotes per top-5 categories (deduplicated)
        used_quote_hashes: set[str] = set()
        representative_quotes: list[dict] = []
        for item in roadmap_items[:5]:
            reviews = cat_groups[item["category"]]
            quotes = _select_quotes(reviews, n=3, used_hashes=used_quote_hashes)
            available = len(quotes)
            representative_quotes.append({
                "category": item["category"],
                "quotes": quotes,
                "insufficient": available < 3,
                "available_count": available,
            })

        # 12. Top themes
        top_themes = [item["category"] for item in roadmap_items[:3]]

        # 13. Taxonomy keyword table
        keyword_table = [
            {"category": cat, "keywords": ", ".join(kws[:8])}
            for cat, kws in TAXONOMY.items()
            if cat != "Other"
        ]

        # 14. Legacy risks (kept for synthesis engine)
        risks: list[str] = []
        other_count = len(cat_groups.get("Other", []))
        other_pct = round(other_count / max(1, total) * 100, 1)
        if other_pct > 15:
            risks.append(f"Other category is {other_pct}% of reviews — taxonomy may need expansion.")
        low_conf = [item["category"] for item in roadmap_items if "Low" in item["confidence"]]
        if low_conf:
            risks.append(f"Low data confidence in: {', '.join(low_conf)}.")

        noise_count = len(cat_groups.get("NOISE POOL", []))
        other_total = other_count + noise_count
        other_pct = round(other_total / max(1, total) * 100, 1)

        return {
            "meta": {
                "total_reviews": total,
                "pre_dedup_count": len(parsed),
                "duplicates_removed": dup_removed,
                "date_range": date_range,
                "top_themes": top_themes,
                "sentiment_distribution": {
                    "Positive": round(pos_total / max(1, total) * 100, 1),
                    "Neutral": round(neu_total / max(1, total) * 100, 1),
                    "Negative": round(neg_total / max(1, total) * 100, 1),
                },
                "has_date_col": bool(date_col),
                "has_rating_col": bool(rating_col),
                "rating_scale": rating_scale if rating_col else None,
                "sentiment_source": "rating" if rating_col else "keyword",
                "unclassified_count": other_total,
                "noise_pool_count": noise_count,
                "unclassified_pct": other_pct,
                "total_classified": total_classified,
                "low_review_warning": total < 30,
            },
            "preflight": preflight,
            "taxonomy_info": {
                "keyword_table": keyword_table,
                "dispatch_weights": {
                    "Pain Intensity": "0.30",
                    "Impact Breadth": "0.25",
                    "Urgency Velocity": "0.20 (or rebalanced if N/A)",
                    "Strategic Leverage": "0.15",
                    "Effort Inverse": "0.10",
                },
            },
            "sentiment_distribution": {
                "labels": ["Positive", "Neutral", "Negative"],
                "values": [pos_total, neu_total, neg_total],
            },
            "sentiment_trend": sentiment_trend,
            "roadmap_items": roadmap_items,
            "watch_list": watch_list,
            "representative_quotes": representative_quotes,
            "risks": risks,
            "_for_ai": {
                "total": total,
                "top_themes": top_themes,
                "sentiment_distribution": {
                    "Positive": pos_total,
                    "Neutral": neu_total,
                    "Negative": neg_total,
                },
                "roadmap_summary": [
                    {
                        "category": i["category"],
                        "volume": i["volume"],
                        "priority_score": i.get("_legacy_priority", 0),
                        "timeline": "TBD",
                        "sentiment": i["sentiment_breakdown"],
                    }
                    for i in roadmap_items[:5]
                ],
                "risks": risks,
            },
            "_parsed_reviews": [
                {
                    "text": r["text"],
                    "rating": r["rating"],
                    "sentiment": r["sentiment"],
                    "category": r["category"],
                    "date": r["date"],
                    "recency_weight": r["recency_weight"],
                }
                for r in deduped
            ],
        }
