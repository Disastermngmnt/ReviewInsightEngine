"""
Prioritization Engine — ReviewInsightEngine (Dispatch v3.0)
=============================================================
Computes final Dispatch v3.0 priority scores from AI-generated 5-axis scores.

Priority Score = (Pain Intensity × 0.30) + (Impact Breadth × 0.25) +
                 (Urgency Velocity × 0.20) + (Strategic Leverage × 0.15) +
                 (Effort Inverse × 0.10)

Normalized Score = Priority Score / 10  [used for timeline assignment only]

Integrates with:
  - core/ai_engine.py score_themes() output as input
  - core/financial_engine.py for quadrant classification
  - config/settings.py DEFAULT_PRIORITY_WEIGHTS
"""

from config.settings import (
    DEFAULT_PRIORITY_WEIGHTS,
    REBALANCED_WEIGHTS_NO_VELOCITY,
    REBALANCED_WEIGHTS_NO_EFFORT,
    EFFORT_HEURISTIC_SCORES,
)

# Dispatch v3.0 axes — must match AI output keys.
AXES = ["pain_intensity", "impact_breadth", "urgency_velocity", "strategic_leverage", "effort_inverse"]


# ── Effort Scoring ─────────────────────────────────────────────────────────────

def classify_effort_type(theme_name: str, ai_rationale: str = "") -> str:
    """
    Heuristic classification of item type for effort method (B).
    Returns one of: bug_fix, ui_change, new_feature, architecture.
    """
    combined = (theme_name + " " + ai_rationale).lower()
    bug_signals = ["bug", "crash", "fix", "broken", "regression", "error", "glitch", "fail"]
    ui_signals = ["ui", "ux", "layout", "design", "navigation", "color", "theme", "font", "config"]
    arch_signals = ["infrastructure", "architecture", "database", "backend", "api redesign", "migration", "scalab"]

    for s in arch_signals:
        if s in combined:
            return "architecture"
    for s in bug_signals:
        if s in combined:
            return "bug_fix"
    for s in ui_signals:
        if s in combined:
            return "ui_change"
    return "new_feature"


def get_effort_score(
    theme_name: str,
    effort_method: str,
    user_estimates: dict | None = None,
    ai_rationale: str = "",
) -> tuple[float, str]:
    """
    Return (effort_inverse_score, audit_string) based on selected method.
    Method A: use user_estimates dict {theme_name: score}
    Method B: classify item type and apply heuristic
    Method C: axis excluded — return 0.0 (weights rebalanced separately)
    """
    if effort_method == "C":
        return 0.0, "Effort Inverse: N/A — Axis excluded [C]. Weights rebalanced."

    if effort_method == "A" and user_estimates and theme_name in user_estimates:
        score = float(user_estimates[theme_name])
        score = max(0.0, min(10.0, score))
        return score, f"Effort Inverse: {score} — User estimate applied [U]"

    # Default: method B heuristic
    item_type = classify_effort_type(theme_name, ai_rationale)
    score = float(EFFORT_HEURISTIC_SCORES.get(item_type, 3))
    type_labels = {
        "bug_fix": "Bug fix / regression",
        "ui_change": "UI change / configuration",
        "new_feature": "New feature / integration",
        "architecture": "Architecture / infra",
    }
    label = type_labels.get(item_type, "New feature / integration")
    return score, f"Effort Inverse: {score} — classified as {label}. Heuristic [B] applied."


# ── Main Priority Computation ──────────────────────────────────────────────────

def compute_priority_scores(
    theme_scores: list[dict],
    weights: dict[str, float] | None = None,
    effort_method: str = "B",
    user_effort_estimates: dict | None = None,
    velocity_available: bool = True,
) -> list[dict]:
    """
    Apply Dispatch v3.0 weighted formula to AI axis scores and produce a ranked list.

    Args:
        theme_scores: list of dicts from AIEngine.score_themes()['theme_scores'].
            Each must have keys for each axis containing {"score": float, "rationale": str}.
        weights: optional custom weight dict (falls back to Dispatch defaults).
        effort_method: "A", "B", or "C" — determines Effort Inverse computation.
        user_effort_estimates: dict {theme_name: score} used only if effort_method == "A".
        velocity_available: if False, rebalance weights (no date data).

    Returns:
        Ranked list of dicts, each containing theme, priority_score (0–10),
        normalized_score (0–1), timeline, rank, and all axis scores with rationales.
    """
    # Determine weight set
    if weights:
        w = weights
        label_suffix = "[Custom weights]"
    elif effort_method == "C":
        w = REBALANCED_WEIGHTS_NO_EFFORT
        label_suffix = "[No Effort Axis]"
    elif not velocity_available:
        w = REBALANCED_WEIGHTS_NO_VELOCITY
        label_suffix = "[No Velocity Axis]"
    else:
        w = DEFAULT_PRIORITY_WEIGHTS
        label_suffix = ""

    # Normalise weights so they sum to 1.0
    active_axes = [a for a in AXES if w.get(a, 0) > 0]
    total_w = sum(w.get(axis, 0) for axis in active_axes) or 1.0
    norm_w = {axis: w.get(axis, 0) / total_w for axis in AXES}

    scored: list[dict] = []
    for ts in theme_scores:
        theme_name = ts.get("theme", "Unknown")
        
        # ENFORCEMENT (Dispatch v3.0): Other and NOISE POOL must never receive scores or ranks
        if theme_name in ("Other", "NOISE POOL"):
            continue

        axis_data = {}
        weighted_sum = 0.0

        for axis in AXES:
            if axis == "effort_inverse":
                # Apply selected effort method
                entry = ts.get(axis, {})
                ai_rationale = entry.get("rationale", "") if isinstance(entry, dict) else ""
                effort_score, effort_audit = get_effort_score(
                    theme_name, effort_method, user_effort_estimates, ai_rationale
                )
                axis_data[axis] = {
                    "score": round(effort_score, 1),
                    "rationale": effort_audit,
                }
                weighted_sum += effort_score * norm_w.get(axis, 0)
                continue

            if axis == "urgency_velocity" and not velocity_available:
                # Axis excluded — score doesn't contribute (weight = 0)
                axis_data[axis] = {
                    "score": None,
                    "rationale": "Urgency Velocity: N/A — no date data. Axis excluded [No Velocity Axis]",
                }
                continue

            entry = ts.get(axis, {})
            if isinstance(entry, dict):
                score = entry.get("score")
                rationale = entry.get("rationale", "No rationale provided")
                if score is None:
                    score = 5.0
                    rationale = "5.0 [D: null returned by AI — default applied]"
            else:
                score = 5.0
                rationale = "5.0 [D: unexpected AI response format]"

            score = max(0.0, min(10.0, float(score)))
            axis_data[axis] = {
                "score": round(score, 1),
                "rationale": rationale,
            }
            weighted_sum += score * norm_w.get(axis, 0)

        priority_score = round(max(0.0, min(10.0, weighted_sum)), 2)
        normalized_score = round(priority_score / 10.0, 3)

        scored.append({
            "theme": theme_name,
            "priority_score": priority_score,
            "normalized_score": normalized_score,
            "timeline": _timeline_bucket(normalized_score),
            "weight_label": label_suffix,
            **axis_data,
        })

    # Sort descending by priority score; tie-break alphabetically
    scored.sort(key=lambda x: (-x["priority_score"], x["theme"]))

    # Assign ranks
    for i, item in enumerate(scored):
        item["rank"] = i + 1

    return scored


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


def classify_quadrant(priority_score: float, financial_impact: float | None) -> str:
    """
    Classify a theme into one of four Dispatch decision quadrants.
    Thresholds: priority ≥ 5.0 = High, financial > 0 = meaningful.
    """
    if financial_impact is None:
        if priority_score >= 5.0:
            return "High Priority (Financial data pending)"
        return "Backlog/Drop (Financial data pending)"

    high_priority = priority_score >= 5.0
    high_impact = financial_impact > 0

    if high_priority and high_impact:
        return "Build Now — High Priority + High Revenue Impact"
    elif high_priority and not high_impact:
        return "Fix Fast — High Priority, Lower Revenue"
    elif not high_priority and high_impact:
        return "Investigate — Low Priority Signal, High Revenue Impact"
    else:
        return "Deprioritize or Drop"
