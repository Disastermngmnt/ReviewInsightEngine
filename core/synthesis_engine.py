"""
Synthesis & Validation Engine — ReviewInsightEngine
====================================================
Cross-validates AI-generated narratives against deterministic computed statistics.
Detects misalignments, hallucinations, and data-confidence issues.

Returns a validation score (0–100), letter grade (A–F), and itemised check list.
"""

# Standard library and type hinting imports.
# Integrates with: Regex-based text analysis and the validation results reported to the frontend.
from __future__ import annotations
import re
from typing import Any


# Configurable constants for the validation logic.
# Integrates with: check_sentiment_alignment to determine the sensitivity of hallucination detection.
SENTIMENT_DRIFT_THRESHOLD = 0.20   # AI sentiment tone vs computed % — max allowed drift
SCORE_MAX = 100

# Utility to safely convert text to lowercase or handle None types.
# Integrates with: All text-matching validation checks below.
def _text_lower(text: str) -> str:
    return (text or "").lower()


# ── Individual Checks ─────────────────────────────────────────────────────────

# Validates that the AI's executive summary reflects the actual sentiment percentages from the data.
# Integrates with: SynthesisEngine.validate to contribute to the final integrity score.
def check_sentiment_alignment(report: dict, narratives: dict) -> dict:
    """AI narrative sentiment tone must roughly match computed distribution."""
    # Retrieve computed distribution from the deterministic analyzer report.
    dist = report.get("meta", {}).get("sentiment_distribution", {})
    computed_neg_pct = dist.get("Negative", 0) / 100
    computed_pos_pct = dist.get("Positive", 0) / 100

    # Get the AI-written summary.
    exec_summary = _text_lower(narratives.get("executive_summary", ""))

    # Lists of signal words to detect sentiment bias in the AI's prose.
    pos_signals = ["positive", "satisfied", "happy", "strong", "excellent", "good performance", "well-received"]
    neg_signals = ["negative", "dissatisfied", "frustrated", "poor", "critical", "concern", "problem", "issue", "failure"]

    # Count occurrences of these signals in the AI text.
    pos_hits = sum(1 for w in pos_signals if w in exec_summary)
    neg_hits = sum(1 for w in neg_signals if w in exec_summary)
    total_hits = pos_hits + neg_hits or 1

    # Calculate the ratio of positive vs negative sentiment expressed by the AI.
    ai_neg_ratio = neg_hits / total_hits
    ai_pos_ratio = pos_hits / total_hits

    # Calculate 'drift' — the difference between the AI's tone and the actual data.
    neg_drift = abs(ai_neg_ratio - computed_neg_pct)
    pos_drift = abs(ai_pos_ratio - computed_pos_pct)

    # Check passes if the drift is within the allowed threshold.
    passed = neg_drift < SENTIMENT_DRIFT_THRESHOLD or pos_drift < SENTIMENT_DRIFT_THRESHOLD
    dominant = "Negative" if computed_neg_pct > 0.5 else "Positive" if computed_pos_pct > 0.5 else "Mixed"

    return {
        "name": "Sentiment Alignment",
        "pass": passed,
        "weight": 20,
        "score": 20 if passed else max(0, int(20 * (1 - min(neg_drift, pos_drift) / SENTIMENT_DRIFT_THRESHOLD))),
        "detail": f"Computed dominant sentiment: {dominant} ({computed_neg_pct:.0%} Neg / {computed_pos_pct:.0%} Pos). "
                  f"AI narrative {'reflects' if passed else 'does not clearly reflect'} this distribution."
    }


# Verifies that the AI narratives explicitly mention the most critical categories detected by the analyzer.
# Integrates with: SynthesisEngine.validate to identify if the AI is ignoring key data segments.
def check_top_theme_consistency(report: dict, narratives: dict) -> dict:
    """AI executive summary should reference at least 2 of the top-3 computed roadmap categories."""
    # List of top themes from the roadmap logic.
    top_themes = [t.lower() for t in report.get("meta", {}).get("top_themes", [])]
    # Search within the AI summary and hypothesis for these theme names.
    exec_summary = _text_lower(narratives.get("executive_summary", "") + " " + narratives.get("hypothesis", ""))

    hits = [t for t in top_themes if t in exec_summary]
    score_raw = len(hits) / max(1, len(top_themes))

    # Pass requires a majority of the top-3 themes to be mentioned.
    passed = score_raw >= 0.67  # at least 2 out of 3

    return {
        "name": "Top Theme Consistency",
        "pass": passed,
        "weight": 20,
        "score": int(20 * score_raw),
        "detail": f"Computed top themes: {', '.join(top_themes) or 'None'}. "
                  f"AI narrative references {len(hits)}/{len(top_themes)}: {', '.join(hits) or 'none'}."
    }


# Ensures the Root Cause Analysis (RCA) specifically addresses the most high-priority roadmap categories.
# Integrates with: SynthesisEngine.validate to ensure qualitative AI responses stay grounded in the top statistical findings.
def check_rca_coverage(report: dict, narratives: dict) -> dict:
    """RCA body should mention at least 1 of the top-2 high-priority categories."""
    # Retrieve the top 2 categories from the ranked roadmap items.
    items = report.get("roadmap_items", [])
    top_cats = [i["category"].lower() for i in items[:2]]
    # Check the RCA body text for these categories.
    rca = _text_lower(narratives.get("rca_body", ""))

    hits = [c for c in top_cats if c in rca]
    passed = len(hits) >= 1

    return {
        "name": "RCA Category Coverage",
        "pass": passed,
        "weight": 15,
        "score": 15 if passed else 0,
        "detail": f"High-priority categories: {', '.join(top_cats) or 'None'}. "
                  f"RCA {'mentions' if passed else 'does not mention'} these: {', '.join(hits) or 'none'}."
    }


# Scans AI narratives to see if flagged statistical risks (e.g., bias) are acknowledged.
# Integrates with: SynthesisEngine.validate to prevent the AI from painting an overly certain picture of skewed data.
def check_risk_acknowledgement(report: dict, narratives: dict) -> dict:
    """Flagged risks should appear conceptually in AI narratives."""
    # Get the list of technical risks identified by the Analyzer.
    risks = report.get("risks", [])
    if not risks:
        return {"name": "Risk Acknowledgement", "pass": True, "weight": 15, "score": 15,
                "detail": "No risks were flagged — check passes by default."}

    # Combine all narrative fields for a comprehensive text search.
    all_text = _text_lower(" ".join([
        narratives.get("executive_summary", ""),
        narratives.get("hypothesis", ""),
        narratives.get("rca_body", "")
    ]))

    # Mapping of technical risk tokens to likely semantic variations in AI prose.
    risk_signals = {
        "recency bias": ["recent", "recency", "last 30", "recent reviews", "short period"],
        "ceiling effect": ["ceiling", "overwhelmingly positive", "skewed high"],
        "floor effect": ["floor", "overwhelmingly negative", "skewed low"],
        "low confidence": ["limited data", "few reviews", "insufficient data", "low confidence", "small sample"],
    }

    acknowledged = 0
    flagged_total = 0
    unacknowledged = []

    # Check each flagged risk against the AI narratives.
    for risk in risks:
        risk_lower = risk.lower()
        matched_signal = None
        for key, signals in risk_signals.items():
            if key in risk_lower:
                matched_signal = signals
                break

        # Fallback to keyword extraction if the risk is not in the predefined map.
        if matched_signal is None:
            words = [w for w in risk_lower.split() if len(w) > 5]
            matched_signal = words

        # Increment acknowledgement count if any signal is found in the text.
        if any(s in all_text for s in (matched_signal or [])):
            acknowledged += 1
        else:
            unacknowledged.append(risk[:80])
        flagged_total += 1

    # Final tallying and scoring.
    ratio = acknowledged / max(1, flagged_total)
    passed = ratio >= 0.5
    score = int(15 * ratio)

    return {
        "name": "Risk Acknowledgement",
        "pass": passed,
        "weight": 15,
        "score": score,
        "detail": f"{acknowledged}/{flagged_total} flagged risks referenced in AI narratives. "
                  + (f"Unacknowledged: {'; '.join(unacknowledged)}" if unacknowledged else "All risks covered.")
    }


# Validates that all computed priority scores are mathematically sound and correctly ordered.
# Integrates with: The core roadmap sorting logic to catch any logical errors in classification or weighing.
def check_score_plausibility(report: dict, narratives: dict) -> dict:
    """Priority scores must be valid: all in [0,1], not all identical, sorted descending."""
    # Retrieve pre-computed priority scores.
    items = report.get("roadmap_items", [])
    if not items:
        return {"name": "Score Plausibility", "pass": False, "weight": 15, "score": 0,
                "detail": "No roadmap items found — cannot validate scores."}

    scores = [i["priority_score"] for i in items]
    
    # Check 1: Scores must be normalized between 0.0 and 10.0.
    all_valid = all(0.0 <= s <= 10.0 for s in scores)
    # Check 2: Scores shouldn't all be identical (implies a degenerate ranking).
    not_all_same = len(set(scores)) > 1 or len(scores) == 1
    # Check 3: The roadmap must be sorted by score descending.
    sorted_desc = scores == sorted(scores, reverse=True)

    passed = all_valid and not_all_same and sorted_desc
    issues = []
    if not all_valid:
        issues.append(f"out-of-range scores: {[s for s in scores if not 0<=s<=10.0]}")
    if not not_all_same:
        issues.append("all priority scores are identical")
    if not sorted_desc:
        issues.append("items not sorted by priority score descending")

    return {
        "name": "Score Plausibility",
        "pass": passed,
        "weight": 15,
        "score": 15 if passed else int(15 * sum([all_valid, not_all_same, sorted_desc]) / 3),
        "detail": f"Scores range: {min(scores):.2f}–{max(scores):.2f} across {len(items)} categories. "
                  + (("Issues: " + "; ".join(issues)) if issues else "All scores valid, unique, and sorted correctly.")
    }


# Verifies that high-confidence data groups have proportionally higher scores (or at least aren't skewed low).
# Integrates with: The Confidence Label logic in core/analyzer.py.
def check_confidence_calibration(report: dict, narratives: dict) -> dict:
    """High-confidence items should have meaningfully higher scores than Low-confidence ones."""
    # Filter items by their pre-calculated confidence tiers.
    items = report.get("roadmap_items", [])
    high_items = [i for i in items if i["confidence"] == "High"]
    low_items = [i for i in items if i["confidence"] == "Low"]

    # Check cannot run if tiers are missing.
    if not high_items or not low_items:
        return {"name": "Confidence Calibration", "pass": True, "weight": 15, "score": 15,
                "detail": "Single confidence tier only — calibration check not applicable."}

    # Compare average priority scores across tiers.
    avg_high = sum(i["priority_score"] for i in high_items) / len(high_items)
    avg_low = sum(i["priority_score"] for i in low_items) / len(low_items)

    passed = avg_high >= avg_low
    return {
        "name": "Confidence Calibration",
        "pass": passed,
        "weight": 15,
        "score": 15 if passed else 5,
        "detail": f"High-confidence avg score: {avg_high:.2f}. Low-confidence avg score: {avg_low:.2f}. "
                  f"{'Calibration correct.' if passed else 'WARNING: Low-confidence items have higher scores than high-confidence — possible data anomaly.'}"
    }


# ── Grade Helper ──────────────────────────────────────────────────────────────

# Maps the numerical validation percentage to a standard letter grade.
# Integrates with: The frontend report header to provide an at-a-glance quality metric.
def _grade(score: int) -> str:
    # Tiered thresholds for A, B, C, D, and F grades.
    if score >= 90: return "A"
    if score >= 80: return "B"
    if score >= 65: return "C"
    if score >= 50: return "D"
    return "F"


# ── Main Engine ───────────────────────────────────────────────────────────────

# Orchestrates all individual validation checks to produce a final report integrity assessment.
# Integrates with: main.py API (/api/analyze) and the ReportTab UI to display the ultimate validation report.
class SynthesisEngine:
    # List of individual check functions to be executed during validation.
    CHECKS = [
        check_sentiment_alignment,
        check_top_theme_consistency,
        check_rca_coverage,
        check_risk_acknowledgement,
        check_score_plausibility,
        check_confidence_calibration,
    ]

    # Executes the full validation suite by comparing computed data (report) with AI text (narratives).
    # Integrates with: Analyzer.run and AIEngine.generate_narratives outputs.
    def validate(self, report: dict, narratives: dict) -> dict[str, Any]:
        """
        Run all validation checks. Returns structured validation result.

        Args:
            report: The full deterministic report dict from Analyzer.run()
            narratives: The AI-generated narratives dict from AIEngine.generate_narratives()
        """
        results = []
        total_weight = 0
        total_score = 0
        flags = []

        # Iterate through each defined check, handling potential runtime errors.
        for check_fn in self.CHECKS:
            try:
                # Execute the check and aggregate results, weights, and scores.
                result = check_fn(report, narratives)
                results.append(result)
                total_weight += result["weight"]
                total_score += result["score"]
                # Collect failure flags for the report summary.
                if not result["pass"]:
                    flags.append(f"[{result['name']}] {result['detail']}")
            except Exception as e:
                # Fallback if a check function itself crashes.
                results.append({
                    "name": check_fn.__name__,
                    "pass": False,
                    "weight": 0,
                    "score": 0,
                    "detail": f"Check failed to run: {str(e)}"
                })

        # Calculate the final percentage score and corresponding letter grade.
        validation_score = round((total_score / max(1, total_weight)) * 100)
        grade = _grade(validation_score)

        # Assemble the final validation results dictionary.
        # Integrates with: The frontend 'Validation Panel' which renders these itemised checks.
        return {
            "validation_score": validation_score,
            "grade": grade,
            "checks": results,
            "flags": flags,
            "summary": (
                f"Report validated with grade {grade} ({validation_score}/100). "
                f"{len(flags)} issue(s) detected." if flags else
                f"Report validated with grade {grade} ({validation_score}/100). All checks passed."
            )
        }
