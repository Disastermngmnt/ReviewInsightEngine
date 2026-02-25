"""
Financial Impact Engine — ReviewInsightEngine (Dispatch v3.0)
===============================================================
Computes revenue-at-risk, revenue opportunity, cost of inaction, and ROI
for each roadmap theme using review-derived signal rates and user-provided
business inputs.

All formulas are deterministic. No AI is used in this module.
Formula strings are returned alongside dollar values for evidence tagging [F].
If business inputs are missing, all dollar values are None with status
"pending_calibration" — never fabricated.

Dispatch v3.0 Formulas:
  A — Revenue at Risk = (churn_rate) × Users × ARPU × 12
  B — Cost of Inaction @ N months = Risk × (1 + monthly_rate)^N
      monthly_rate = (urgency_velocity_score / 10) × 0.5%
  C — Revenue Opportunity = (expansion_rate) × Users × ARPU × 12
  D — ROI = (Risk + Opportunity) / (Sprint Cost × Sprints)
      Sprints: Pain ≥ 8 → 1; Pain 5–7 → 3; Pain < 5 → 6

Integrates with:
  - core/signal_extractor.py aggregate_theme_signals() as data source
  - core/prioritization_engine.py for urgency_velocity_score and pain score
  - main.py for user-provided FinancialInputs
  - Frontend financial impact tables and charts
"""

from __future__ import annotations
from dataclasses import dataclass, field
import math


@dataclass
class FinancialInputs:
    """User-provided business parameters for financial modelling."""
    total_users: int | None = None
    monthly_arpu: float | None = None
    segment_weights: dict[str, float] | None = field(default=None)
    sprint_cost: float | None = None

    @property
    def is_calibrated(self) -> bool:
        """Financial outputs require at least total_users and monthly_arpu."""
        return self.total_users is not None and self.monthly_arpu is not None


def _confidence_level(mention_count: int) -> str:
    """Assign confidence based on evidence volume (Dispatch thresholds)."""
    if mention_count >= 20:
        return "High"
    elif mention_count >= 10:
        return "Medium"
    else:
        return "Low ⚠"


def _compute_revenue_at_risk(
    churn_signal_count: int,
    total_reviews: int,
    total_users: int,
    monthly_arpu: float,
) -> tuple[float, str]:
    """
    Dispatch v3.0 Model A — Revenue at Risk.
    Formula: (churn_signal_count / total_reviews) × total_users × monthly_arpu × 12
    Returns (dollar_value, formula_string_with_substituted_values).
    """
    if total_reviews == 0:
        return 0.0, "0 reviews — cannot compute"
    churn_rate = churn_signal_count / total_reviews
    result = round(churn_rate * total_users * monthly_arpu * 12, 2)
    formula_str = (
        f"({churn_signal_count} / {total_reviews}) × {total_users:,} × ${monthly_arpu:,.2f} × 12 = ${result:,.2f}"
    )
    return result, formula_str


def _compute_revenue_opportunity(
    expansion_signal_count: int,
    total_reviews: int,
    total_users: int,
    monthly_arpu: float,
) -> tuple[float, str]:
    """
    Dispatch v3.0 Model C — Revenue Opportunity.
    Formula: (expansion_rate) × total_users × monthly_arpu × 12
    """
    if total_reviews == 0:
        return 0.0, "0 reviews — cannot compute"
    opportunity_rate = expansion_signal_count / total_reviews
    result = round(opportunity_rate * total_users * monthly_arpu * 12, 2)
    formula_str = (
        f"({expansion_signal_count} / {total_reviews}) × {total_users:,} × ${monthly_arpu:,.2f} × 12 = ${result:,.2f}"
    )
    return result, formula_str


def _compute_cost_of_inaction(
    revenue_at_risk: float,
    urgency_velocity_score: float | None,
) -> dict[str, float | str]:
    """
    Dispatch v3.0 Model B — Cost of Inaction Over Time.
    monthly_rate = (urgency_velocity_score / 10) × 0.5%
    Cost at N months = Revenue at Risk × (1 + monthly_rate)^N
    Returns dict with 3mo, 6mo, 12mo projections + formula strings.
    """
    if urgency_velocity_score is None:
        # No velocity data — use conservative flat rate
        monthly_rate = 0.005 * 0.5
        rate_note = "[D: velocity N/A — 0.25% monthly rate used]"
    else:
        monthly_rate = (urgency_velocity_score / 10) * 0.005
        rate_note = f"[F: ({urgency_velocity_score}/10) × 0.5% = {round(monthly_rate*100, 3)}% /mo]"

    result_3mo = round(revenue_at_risk * ((1 + monthly_rate) ** 3), 2)
    result_6mo = round(revenue_at_risk * ((1 + monthly_rate) ** 6), 2)
    result_12mo = round(revenue_at_risk * ((1 + monthly_rate) ** 12), 2)

    return {
        "3_months": result_3mo,
        "6_months": result_6mo,
        "12_months": result_12mo,
        "monthly_rate_pct": round(monthly_rate * 100, 4),
        "formula_note": rate_note,
        "3mo_formula": f"${revenue_at_risk:,.2f} × (1 + {round(monthly_rate*100,4)}%)^3 = ${result_3mo:,.2f}",
        "6mo_formula": f"${revenue_at_risk:,.2f} × (1 + {round(monthly_rate*100,4)}%)^6 = ${result_6mo:,.2f}",
        "12mo_formula": f"${revenue_at_risk:,.2f} × (1 + {round(monthly_rate*100,4)}%)^12 = ${result_12mo:,.2f}",
    }


def _compute_roi(
    revenue_at_risk: float,
    revenue_opportunity: float,
    sprint_cost: float | None,
    pain_intensity_score: float,
) -> tuple[float | None, str]:
    """
    Dispatch v3.0 Model D — ROI.
    Sprints: Pain ≥ 8 → 1; Pain 5–7 → 3; Pain < 5 → 6
    ROI = (Revenue at Risk + Opportunity) / (Sprint Cost × Sprints)
    """
    if sprint_cost is None or sprint_cost <= 0:
        return None, "ROI: LOCKED — sprint cost not provided [U]"

    if pain_intensity_score >= 8:
        sprints = 1
    elif pain_intensity_score >= 5:
        sprints = 3
    else:
        sprints = 6

    total_value = revenue_at_risk + revenue_opportunity
    total_cost = sprint_cost * sprints
    roi = round(total_value / total_cost, 2) if total_cost > 0 else 0.0
    formula_str = (
        f"(${revenue_at_risk:,.2f} + ${revenue_opportunity:,.2f}) / "
        f"(${sprint_cost:,.2f} × {sprints} sprints) = {roi}x"
    )
    return roi, formula_str


# ── Main Entry Point ──────────────────────────────────────────────────────────

def compute_financial_impact(
    theme_signals: dict[str, dict],
    financial_inputs: FinancialInputs,
    total_reviews: int,
    priority_scores: list[dict] | None = None,
) -> list[dict]:
    """
    Compute Dispatch v3.0 financial impact metrics for each theme.

    Args:
        theme_signals: dict from signal_extractor.aggregate_theme_signals().
        financial_inputs: user-provided business parameters.
        total_reviews: total review count (post-dedup).
        priority_scores: list from prioritization_engine (for velocity and pain scores).

    Returns:
        List of dicts, one per theme, each containing revenue_at_risk, formula strings,
        revenue_opportunity, cost_of_inaction (3/6/12mo), roi_score, confidence, status.
        If financial_inputs lacks calibration, dollar fields are None with status
        "pending_calibration".
    """
    # Build lookup for AI-computed axis scores
    score_lookup: dict[str, dict] = {}
    if priority_scores:
        for ps in priority_scores:
            score_lookup[ps["theme"]] = ps

    results: list[dict] = []

    for theme, signals in sorted(theme_signals.items()):
        churn_count = signals.get("churn_signal_count", 0)
        expansion_count = signals.get("expansion_signal_count", 0)
        volume = signals.get("volume", 0)
        confidence = _confidence_level(volume)

        # Get AI-computed scores for this theme (if available)
        ai_scores = score_lookup.get(theme, {})
        pain_score = 0.0
        if isinstance(ai_scores.get("pain_intensity"), dict):
            pain_score = float(ai_scores["pain_intensity"].get("score", 0) or 0)
        velocity_entry = ai_scores.get("urgency_velocity", {})
        velocity_score = None
        if isinstance(velocity_entry, dict):
            v = velocity_entry.get("score")
            velocity_score = float(v) if v is not None else None

        if not financial_inputs.is_calibrated:
            results.append({
                "theme": theme,
                "revenue_at_risk": None,
                "revenue_at_risk_formula": "LOCKED — financial inputs required [U]",
                "revenue_opportunity": None,
                "revenue_opportunity_formula": "LOCKED",
                "cost_of_inaction": None,
                "roi_score": None,
                "roi_formula": "LOCKED",
                "confidence": confidence,
                "status": "pending_calibration",
                "churn_signal_count": churn_count,
                "expansion_signal_count": expansion_count,
            })
            continue

        # Calibrated path
        total_users = financial_inputs.total_users
        monthly_arpu = financial_inputs.monthly_arpu

        rev_risk, risk_formula = _compute_revenue_at_risk(
            churn_count, total_reviews, total_users, monthly_arpu
        )
        rev_opp, opp_formula = _compute_revenue_opportunity(
            expansion_count, total_reviews, total_users, monthly_arpu
        )
        cost_inaction = _compute_cost_of_inaction(rev_risk, velocity_score)
        roi, roi_formula = _compute_roi(rev_risk, rev_opp, financial_inputs.sprint_cost, pain_score)

        results.append({
            "theme": theme,
            "revenue_at_risk": rev_risk,
            "revenue_at_risk_formula": risk_formula,
            "revenue_opportunity": rev_opp,
            "revenue_opportunity_formula": opp_formula,
            "cost_of_inaction": cost_inaction,
            "roi_score": roi,
            "roi_formula": roi_formula,
            "confidence": confidence,
            "status": "calibrated",
            "churn_signal_count": churn_count,
            "expansion_signal_count": expansion_count,
            "pain_intensity_score": pain_score,
            "velocity_score_used": velocity_score,
        })

    # Sort by total financial impact (risk + opportunity) descending
    def _sort_key(item):
        if item["status"] == "pending_calibration":
            return 0
        return (item.get("revenue_at_risk") or 0) + (item.get("revenue_opportunity") or 0)

    results.sort(key=_sort_key, reverse=True)
    return results
