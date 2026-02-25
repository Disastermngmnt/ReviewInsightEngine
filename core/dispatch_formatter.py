"""
Dispatch v3.0 Formatter — ReviewInsightEngine
================================================
Assembles the full Dispatch v3.0 Product Intelligence Report in strict
document order (sections 0–12). This module is a pure data transformation
layer — no AI calls, no database access.

Evidence Tags Applied Throughout:
  [R] = derived from review data
  [F: formula] = computed by formula (formula name given)
  [U] = user-provided input
  [H: heuristic] = heuristic estimate
  [D: reason] = default value applied

Document Order (Dispatch spec, never deviate):
  0. Run Identity Header
  1. Effort Scoring Input (collected by frontend — echoed here)
  2. Synthesis Status Panel
  3. Pre-Flight Validation (6 checks)
  4. Sentiment Acceleration Alert (if triggered)
  5. Data Quality Alert — Other Category (if triggered)
  6. Financial Input Panel (echoed here)
  7. AI Priority Matrix + Feature Roadmap Table
  8. Action Cards (top 5) — HARD INTERRUPT enforced
  9. Financial Impact Model
  10. Sentiment Analysis Charts data
  11. Representative Quotes
  12. Risks & Blind Spots

Integrates with:
  - core/analyzer.py for report dict and preflight data
  - core/ai_engine.py for generate_run_id and narrative output
  - core/prioritization_engine.py for priority_scores list
  - core/financial_engine.py for financial_impact list
  - core/synthesis_engine.py for risks_blind_spots checks
"""

from __future__ import annotations
from datetime import datetime, timezone
from config.settings import DISPATCH_PROMPT_VERSION, MODEL_NAME, ACTION_CARD_BANNED_PHRASES


# ── Evidence Tag Helpers ───────────────────────────────────────────────────────

def _r(value) -> str:
    """Tag: [R] — value derived from review data."""
    return f"{value} [R]"


def _f(value, formula: str) -> str:
    """Tag: [F] — value computed by formula."""
    return f"{value} [F: {formula}]"


def _u(value) -> str:
    """Tag: [U] — user-provided input."""
    return f"{value} [U]"


def _h(value, heuristic: str) -> str:
    """Tag: [H] — heuristic estimate."""
    return f"{value} [H: {heuristic}]"


def _d(value, reason: str) -> str:
    """Tag: [D] — default value applied."""
    return f"{value} [D: {reason}]"


# ── Section 0: Run Identity Header ────────────────────────────────────────────

def build_run_identity_header(
    run_id: str,
    filename: str,
    total_reviews: int,
    generated_at: datetime | None = None,
) -> dict:
    """
    Dispatch Section 0 — Run Identity Header.
    Every field is traceable — makes every run comparable.
    """
    if generated_at is None:
        generated_at = datetime.now(tz=timezone.utc)
    return {
        "section": 0,
        "title": "DISPATCH · PRODUCT INTELLIGENCE REPORT",
        "run_id": run_id,
        "file": filename,
        "reviews": total_reviews,
        "generated": generated_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "model": MODEL_NAME,
        "prompt_version": DISPATCH_PROMPT_VERSION,
        "display_line": (
            f"Run ID: {run_id} | File: {filename} | Reviews: {total_reviews} | "
            f"Generated: {generated_at.strftime('%Y-%m-%d %H:%M UTC')} | "
            f"Model: {MODEL_NAME} | Prompt Version: {DISPATCH_PROMPT_VERSION}"
        ),
    }


# ── Section 1: Effort Scoring Input (echoed) ──────────────────────────────────

def build_effort_scoring_input(effort_method: str) -> dict:
    """
    Dispatch Section 1 — Effort Scoring Input echo.
    The frontend collects this; we echo back the selected method and its label.
    """
    labels = {
        "A": "Manual — user will provide estimates per item",
        "B": "Default complexity heuristic (recommended): Bug fix → 8, UI change → 6, New feature → 3, Architecture → 1",
        "C": "Effort scoring skipped — remaining 4 axes rebalanced",
    }
    return {
        "section": 1,
        "title": "EFFORT SCORING METHOD",
        "selected_method": effort_method,
        "description": labels.get(effort_method, labels["B"]),
        "weights_active": effort_method != "C",
    }


# ── Section 2: Synthesis Status Panel ─────────────────────────────────────────

def build_synthesis_status_panel(
    report: dict,
    priority_scores: list[dict],
    financial_impact: list[dict],
    preflight: dict,
    action_cards_count: int,
) -> dict:
    """
    Dispatch Section 2 — Synthesis Status Panel.
    Every value must be computed from actual data — no placeholders.
    """
    meta = report.get("meta", {})
    total = meta.get("total_reviews", 0)
    pre_dedup = meta.get("pre_dedup_count", total)
    dups = meta.get("duplicates_removed", 0)
    classified = meta.get("total_classified", 0)
    unclassified = meta.get("unclassified_count", 0)
    unclassified_pct = meta.get("unclassified_pct", 0.0)

    # Category breakdown
    roadmap_items = report.get("roadmap_items", [])
    cat_breakdown = {item["category"]: item["volume"] for item in roadmap_items}
    if unclassified > 0:
        cat_breakdown["Other"] = unclassified

    # Preflight summary
    pf_summary = preflight.get("summary", {})
    pf_display = pf_summary.get("display", "N/A")

    # Financial status
    if financial_impact and financial_impact[0].get("status") == "calibrated":
        financial_status = f"{len(financial_impact)} items"
    else:
        financial_status = "LOCKED"

    # Other flag
    other_flag = " ← ⚠ FLAG" if unclassified_pct > 15 else ""

    return {
        "section": 2,
        "title": "SYNTHESIS STATUS",
        "rows": {
            "reviews_ingested": _r(total),
            "duplicates_removed": f"{_r(dups)} → {_r(total - dups)} remaining",
            "reviews_classified": f"{_r(classified)} ({_r(round(classified / max(1, total) * 100, 1))}% of total)",
            "breakdown_by_category": cat_breakdown,
            "reviews_in_other": f"{_r(unclassified)} ({_r(unclassified_pct)}%){other_flag}",
            "feature_items_extracted": _r(len(roadmap_items)),
            "items_scored": _r(len(priority_scores)),
            "financial_model_status": financial_status,
            "action_cards_generated": _r(action_cards_count),
            "validation_checks": pf_display,
        },
    }


# ── Section 3: Pre-Flight Validation ──────────────────────────────────────────

def build_preflight_validation(preflight: dict) -> dict:
    """
    Dispatch Section 3 — Pre-Flight Validation (all 6 checks).
    If any check is FAIL: halt flag is set.
    """
    checks = preflight.get("checks", {})
    summary = preflight.get("summary", {})

    formatted_checks = []
    for key, data in checks.items():
        check_num = key.split("_")[1]
        name_parts = key.split("_")[2:]
        name = " ".join(w.capitalize() for w in name_parts)
        formatted_checks.append({
            "check": f"CHECK {check_num} — {name}",
            "status": data.get("status", "UNKNOWN"),
            "message": data.get("message", ""),
            "raw": data,
        })

    return {
        "section": 3,
        "title": "PRE-FLIGHT VALIDATION",
        "checks": formatted_checks,
        "summary": summary,
        "halt": summary.get("halt", False),
    }


# ── Section 4: Sentiment Acceleration Alert ───────────────────────────────────

def build_sentiment_acceleration_alert(preflight: dict) -> dict | None:
    """
    Dispatch Section 4 — Sentiment Acceleration Alert.
    Returns None if not triggered (section omitted per spec).
    """
    check_4 = preflight.get("checks", {}).get("check_4_sentiment_acceleration", {})
    if check_4.get("status") != "ALERT":
        return None

    alert = check_4.get("alert_data", {})
    return {
        "section": 4,
        "title": "⚠ SENTIMENT ACCELERATION ALERT",
        "triggered": True,
        "delta": f"+{alert.get('delta', 0)}% [R]",
        "prior_neg_pct": f"{alert.get('prior_neg_pct', 0)}% [R]",
        "current_neg_pct": f"{alert.get('current_neg_pct', 0)}% [R]",
        "week": alert.get("week_id", "N/A"),
        "top_driving_category": alert.get("top_driving_category", "Unknown"),
        "top_cat_negative_count": _r(alert.get("top_cat_negative_count", 0)),
        "banner_text": (
            f"⚠ RED ALERT: Negative sentiment increased from "
            f"{alert.get('prior_neg_pct', 0)}% to {alert.get('current_neg_pct', 0)}% "
            f"(+{alert.get('delta', 0)}%) WoW in {alert.get('week_id', 'N/A')}. "
            f"Top driver: {alert.get('top_driving_category', 'Unknown')} — "
            f"{alert.get('top_cat_negative_count', 0)} negative reviews this week."
        ),
    }


# ── Section 5: Data Quality Alert ────────────────────────────────────────────

def build_data_quality_alert(preflight: dict) -> dict | None:
    """
    Dispatch Section 5 — Data Quality Alert for Other > 15%.
    Returns None if not triggered.
    """
    check_1 = preflight.get("checks", {}).get("check_1_classification_coverage", {})
    status = check_1.get("status", "PASS")
    other_pct = check_1.get("other_pct", 0.0)
    other_count = check_1.get("other_count", 0)

    if status == "PASS":
        return None

    return {
        "section": 5,
        "title": "DATA QUALITY ALERT — OTHER CATEGORY",
        "status": status,
        "other_pct": _r(other_pct),
        "other_count": _r(other_count),
        "message": (
            f"{status}: Other category represents {other_pct}% of reviews — "
            f"taxonomy may need expansion. Scoring accuracy may be impacted. "
            f"'Other' will NOT appear as a roadmap item."
        ),
    }


# ── Section 6: Financial Input Panel (echoed) ─────────────────────────────────

def build_financial_input_panel(
    total_users: int | None,
    monthly_arpu: float | None,
    segment_weights: dict | None,
    sprint_cost: float | None,
) -> dict:
    """Dispatch Section 6 — Financial Input Panel echo."""
    calibrated = total_users is not None and monthly_arpu is not None
    return {
        "section": 6,
        "title": "FINANCIAL MODEL INPUTS",
        "calibrated": calibrated,
        "total_users": _u(total_users) if total_users else "NOT PROVIDED",
        "monthly_arpu": _u(f"${monthly_arpu:,.2f}") if monthly_arpu else "NOT PROVIDED",
        "segment_weights": _u(segment_weights) if segment_weights else "Not provided (all users weighted equally)",
        "sprint_cost": _u(f"${sprint_cost:,.2f}") if sprint_cost else "Not provided (ROI will show LOCKED)",
        "status": "CALIBRATED — financial model active" if calibrated else "LOCKED — provide total_users and monthly_arpu to unlock",
    }


# ── Section 7: AI Priority Matrix + Roadmap Table ─────────────────────────────

def build_priority_matrix(
    priority_scores: list[dict],
    report: dict,
    velocity_available: bool,
    effort_method: str,
) -> dict:
    """
    Dispatch Section 7 — AI Priority Matrix + Feature Roadmap Table (single unified ranking).
    This is the ONLY ranked list in the document.
    """
    roadmap = report.get("roadmap_items", [])
    meta = report.get("meta", {})
    total_classified = meta.get("total_classified", 1)

    # Build lookup from analyzer data
    analyzer_lookup = {item["category"]: item for item in roadmap}

    rows = []
    for ps in priority_scores:
        theme = ps["theme"]
        ai_data = analyzer_lookup.get(theme, {})
        volume = ai_data.get("volume", 0)
        churn_count = ai_data.get("churn_signal_count", 0)
        expansion_count = ai_data.get("expansion_signal_count", 0)

        # Build evidence-tagged audit rows
        pain_entry = ps.get("pain_intensity", {})
        impact_entry = ps.get("impact_breadth", {})
        velocity_entry = ps.get("urgency_velocity", {})
        strategic_entry = ps.get("strategic_leverage", {})
        effort_entry = ps.get("effort_inverse", {})

        pain_score = pain_entry.get("score", 0) if isinstance(pain_entry, dict) else 0
        impact_score = impact_entry.get("score", 0) if isinstance(impact_entry, dict) else 0
        velocity_score = velocity_entry.get("score") if isinstance(velocity_entry, dict) else None
        strategic_score = strategic_entry.get("score", 0) if isinstance(strategic_entry, dict) else 0
        effort_score = effort_entry.get("score", 0) if isinstance(effort_entry, dict) else 0

        pct = round(volume / max(1, total_classified) * 100, 1)
        churn_pct = round(churn_count / max(1, volume) * 100, 1)
        expansion_pct = round(expansion_count / max(1, volume) * 100, 1)

        row = {
            "rank": ps["rank"],
            "item_name": theme,
            "category": theme,
            "volume": _r(volume),
            "pain_score": _f(pain_score, "Pain Intensity"),
            "priority_score": _f(ps["priority_score"], "Dispatch Priority Score"),
            "normalized_score": _f(ps["normalized_score"], "Priority/10"),
            "timeline": ps["timeline"],
            "confidence": ai_data.get("confidence", "Low ⚠"),
            "churn_signals": f"{_r(churn_count)} ({_r(churn_pct)}%)",
            "expansion_signals": f"{_r(expansion_count)} ({_r(expansion_pct)}%)",
            "weight_label": ps.get("weight_label", ""),
            # 5-axis breakdown for expandable row
            "axis_breakdown": {
                "pain_intensity": {
                    "score": _f(pain_score, "Pain Intensity formula"),
                    "rationale": pain_entry.get("rationale", "") if isinstance(pain_entry, dict) else "",
                    "audit": ai_data.get("pain_audit", {}).get("formula", ""),
                },
                "impact_breadth": {
                    "score": _f(impact_score, "Impact Breadth formula"),
                    "rationale": impact_entry.get("rationale", "") if isinstance(impact_entry, dict) else "",
                    "audit": ai_data.get("impact_audit", ""),
                },
                "urgency_velocity": {
                    "score": _f(velocity_score, "Urgency Velocity") if velocity_score is not None else "N/A [No Velocity Axis]",
                    "rationale": velocity_entry.get("rationale", "N/A") if isinstance(velocity_entry, dict) else "N/A",
                    "audit": str(ai_data.get("velocity_audit", {}).get("change_pct", "N/A")),
                },
                "strategic_leverage": {
                    "score": _f(strategic_score, "Strategic Leverage"),
                    "rationale": strategic_entry.get("rationale", "") if isinstance(strategic_entry, dict) else "",
                },
                "effort_inverse": {
                    "score": _f(effort_score, f"Effort Inverse [{effort_method}]"),
                    "rationale": effort_entry.get("rationale", "") if isinstance(effort_entry, dict) else "",
                },
            },
        }
        rows.append(row)

    weight_display = (
        "Pain×0.375, Impact×0.3125, Strategic×0.1875, Effort×0.125 [No Velocity Axis]"
        if not velocity_available
        else "Pain×0.30, Impact×0.25, Velocity×0.20, Strategic×0.15, Effort×0.10"
        if effort_method != "C"
        else "Pain×0.375, Impact×0.3125, Velocity×0.25, Strategic×0.1875 [No Effort Axis]"
    )

    return {
        "section": 7,
        "title": "AI PRIORITY MATRIX + FEATURE ROADMAP TABLE",
        "note": "This is the ONLY ranked list in this document.",
        "weights_active": weight_display,
        "velocity_available": velocity_available,
        "effort_method": effort_method,
        "rows": rows,
    }


# ── Action Card Hard Interrupt Checklist Helpers ──────────────────────────────
# Dispatch spec: before writing each action card, complete Q1/Q2/Q3 internally.
# If any Q cannot be answered from data: emit INSUFFICIENT SIGNAL instead.


def _check_banned_text(text: str) -> bool:
    """True if the text contains any explicitly banned placeholder phrase."""
    t = text.lower()
    return any(phrase.lower() in t for phrase in ACTION_CARD_BANNED_PHRASES)


def _derive_specific_issue(theme: str, quotes: list[dict], ai_data: dict) -> str | None:
    """
    Q1: Extract the specific named issue for this category from quote evidence.
    Analyses the most frequent complaint words from negative/churn quotes.
    Returns a descriptive string, or None if the signal is too vague.
    """
    if not quotes:
        return None
    STOPWORDS = {"this", "that", "with", "have", "they", "from", "just",
                 "when", "what", "your", "very", "been", "more", "than",
                 "there", "their", "also", "some", "into", "each", "will"}
    neg_quotes = [q for q in quotes if q.get("sentiment") == "Negative"
                  or q.get("signal_type") == "churn"]
    source = neg_quotes if neg_quotes else quotes
    counts: dict[str, int] = {}
    for q in source:
        for w in str(q.get("text", "")).lower().split():
            w = w.strip(".,!?;:'\"")
            if len(w) >= 4 and w not in STOPWORDS:
                counts[w] = counts.get(w, 0) + 1
    if not counts:
        return None
    top_words = sorted(counts, key=counts.get, reverse=True)[:3]  # type: ignore[arg-type]
    issue_words = [w for w in top_words if w not in theme.lower()] or top_words
    churn = ai_data.get("churn_signal_count", 0)
    volume = ai_data.get("volume", 1)
    severity = f" ({round(churn / max(1, volume) * 100)}% churn-signal reviews)" if churn else ""
    return f"{' + '.join(issue_words[:2])}{severity}"


def _suggest_deliverable(theme: str, quotes: list[dict], ai_data: dict) -> str | None:
    """
    Q3: Derive a concrete, measurable deliverable from category + evidence.
    Returns a specific build task, never a generic investigation statement.
    Returns None if signal is insufficient to name a deliverable.
    """
    theme_lower = theme.lower()
    volume = ai_data.get("volume", 0)
    avg_rating = ai_data.get("avg_rating", 3.0)
    churn = ai_data.get("churn_signal_count", 0)
    neg_quotes = [q for q in quotes if q.get("sentiment") == "Negative"]
    best_quote = (neg_quotes or quotes or [None])[0]
    snippet = f": \u201c{str(best_quote.get('text', ''))[:110]}\u2026\u201d" if best_quote else ""

    if any(t in theme_lower for t in ["performance", "speed", "crash", "lag", "slow", "freeze"]):
        return (f"Profile and fix the top crash/freeze path in {theme} "
                f"({volume} reports, avg {avg_rating:.1f}\u2605){snippet}. "
                f"Deliverable: crash-free session rate \u2265 99.5% on next release.")
    if any(t in theme_lower for t in ["ui", "ux", "design", "navigation", "layout", "interface"]):
        return (f"Run a navigation usability audit and fix the top 3 dead-end flows in {theme} "
                f"({volume} reports){snippet}. "
                f"Deliverable: task-completion rate improvement measurable in next UX test.")
    if any(t in theme_lower for t in ["pricing", "billing", "cost", "payment", "subscription"]):
        return (f"Add a clear per-plan pricing comparison page addressing billing confusion "
                f"cited in {volume} reviews{snippet}. "
                f"Deliverable: pricing-page bounce rate < 40% within 30 days of launch.")
    if any(t in theme_lower for t in ["support", "customer service", "response", "help"]):
        return (f"Implement first-response SLA \u2264 4 hours for {theme} tickets "
                f"({volume} reports, {churn} churn-signal reviews){snippet}. "
                f"Deliverable: support CSAT \u2265 4.0 within 60 days.")
    if any(t in theme_lower for t in ["onboard", "setup", "tutorial", "getting started"]):
        return (f"Build an interactive onboarding checklist eliminating the confusion "
                f"cited in {volume} reviews{snippet}. "
                f"Deliverable: time-to-first-value \u2264 5 minutes for new accounts.")
    if any(t in theme_lower for t in ["feature", "missing", "integration", "export", "import", "api"]):
        return (f"Ship the most-requested missing capability in {theme} ({volume} requests){snippet}. "
                f"Deliverable: feature released behind flag; 10% adoption within 4 weeks.")
    if any(t in theme_lower for t in ["reliability", "bug", "error", "glitch", "stable", "broken"]):
        return (f"Triage and fix the top-reported reliability issue in {theme} "
                f"({volume} reports, avg {avg_rating:.1f}\u2605){snippet}. "
                f"Deliverable: error rate for affected flow < 0.1% within next sprint.")
    if churn > 0:
        return (f"Address the {churn} churn-signal reviews in {theme}: "
                f"identify and ship a fix for the blocking issue{snippet}. "
                f"Deliverable: churn-signal mention rate falls by \u2265 30% in next cohort.")
    return None


def _check_q1_q2_q3(theme: str, quotes: list[dict], ai_data: dict, volume: int) -> dict:
    """
    Pre-card internal checklist (Dispatch Action Card Hard Interrupt).
    Returns {"ok": bool, "q1": str|None, "q2": quote|None, "q3": str|None}.
    If any Q is None: the card must show INSUFFICIENT SIGNAL instead.
    """
    q1 = _derive_specific_issue(theme, quotes, ai_data)
    q2 = next(
        (q for q in quotes if q.get("signal_type") in ("churn", "urgency", "expansion")),
        quotes[0] if quotes else None,
    )
    if q2 and not str(q2.get("text", "")).strip():
        q2 = None
    q3 = _suggest_deliverable(theme, quotes, ai_data)
    return {"ok": all([q1, q2, q3]), "q1": q1, "q2": q2, "q3": q3}


def _format_insufficient_signal(theme: str, volume: int) -> str:
    """Standard INSUFFICIENT SIGNAL message when Q1/Q2/Q3 checklist fails."""
    return (
        f"INSUFFICIENT SIGNAL \u2014 {volume} reviews classified under {theme} "
        f"but no specific feature item extractable from available quote evidence. "
        f"Recommend collecting more targeted feedback before actioning."
    )


# ── Section 8: Action Cards ────────────────────────────────────────────────────

def build_action_cards(
    priority_scores: list[dict],
    report: dict,
    financial_impact: list[dict],
    representative_quotes: list[dict],
) -> dict:
    """
    Dispatch Section 8 — Action Cards (top 5 items only).
    All metrics inherited directly from AI Priority Matrix — never recomputed.

    HARD INTERRUPT: Each card passes a Q1/Q2/Q3 pre-card checklist:
      Q1: What is the specific named issue? (not a category — a concrete complaint)
      Q2: What quote evidence with signal type supports this?
      Q3: What exactly should the team build? (a deliverable, not an investigation)
    If any Q fails: INSUFFICIENT SIGNAL is emitted instead of the card.
    Banned placeholder text (ACTION_CARD_BANNED_PHRASES) can never appear here.
    """
    roadmap = report.get("roadmap_items", [])
    analyzer_lookup = {item["category"]: item for item in roadmap}
    financial_lookup = {f["theme"]: f for f in (financial_impact or [])}

    # Build quote lookup (already deduped by analyzer)
    quote_lookup: dict[str, list[dict]] = {}
    for q_item in (representative_quotes or []):
        quote_lookup[q_item["category"]] = q_item.get("quotes", [])

    cards = []
    for ps in priority_scores[:5]:
        theme = ps["theme"]
        ai_data = analyzer_lookup.get(theme, {})
        fin_data = financial_lookup.get(theme, {})
        quotes = quote_lookup.get(theme, [])
        volume = ai_data.get("volume", 0)

        pain_entry = ps.get("pain_intensity", {})
        pain_score = pain_entry.get("score", 0) if isinstance(pain_entry, dict) else 0
        churn_count = ai_data.get("churn_signal_count", 0)
        churn_pct = round(churn_count / max(1, volume) * 100, 1)

        # Revenue at risk (LOCKED if not calibrated)
        if fin_data.get("status") == "calibrated":
            risk_val = f"${fin_data.get('revenue_at_risk', 0):,.2f} [F: Revenue at Risk formula]"
            risk_6mo = fin_data.get("cost_of_inaction", {}).get("6_months")
            risk_6mo_str = f"${risk_6mo:,.2f} [F: Cost of Inaction 6mo]" if risk_6mo else "LOCKED"
        else:
            risk_val = "LOCKED — financial inputs required [U]"
            risk_6mo_str = "LOCKED — financial inputs required [U]"

        # ── ACTION CARD HARD INTERRUPT ──
        # Run Q1/Q2/Q3 pre-card checklist before writing any text.
        qcheck = _check_q1_q2_q3(theme, quotes, ai_data, volume)

        if qcheck["ok"]:
            # All three Qs satisfied — write card with specific evidence-backed content.
            what_to_build = qcheck["q3"]
            # Final safety net: reject if banned text somehow crept in.
            if _check_banned_text(what_to_build):
                what_to_build = _format_insufficient_signal(theme, volume)
            problem_statement = (
                f"{theme} — specific issue: {qcheck['q1']}. "
                f"{_r(volume)} reviews, avg rating {_r(ai_data.get('avg_rating', 'N/A'))}\u2605."
            )
            success_metric = (
                f"Verified measurable improvement in {theme} metrics within 2 sprints of shipping."
            )
        else:
            # Q1, Q2, or Q3 failed — emit INSUFFICIENT SIGNAL, never a placeholder.
            what_to_build = _format_insufficient_signal(theme, volume)
            problem_statement = (
                f"{theme} — {_r(volume)} reviews classified, "
                f"but no specific actionable issue could be extracted from quote evidence."
            )
            success_metric = "Not available — insufficient signal for this category."

        item_name = ps.get("specific_feature", theme)
        if not item_name or item_name.strip() == "":
            item_name = theme

        card = {
            "rank": ps["rank"],
            "item_name": item_name,
            "priority_score": _f(ps["priority_score"], "Dispatch Priority Score"),
            "normalized_score": _f(ps["normalized_score"], "Priority/10"),
            "timeline": ps["timeline"],
            "problem_statement": problem_statement,
            "who_is_affected": "All users — no segment data in input",
            "what_data_says": [
                f"Pain Intensity: {_f(pain_score, 'Pain Intensity formula')} [F]",
                f"Impact Breadth: {_r(volume)} reviews ({_r(round(volume / max(1, report.get('meta', {}).get('total_classified', 1)) * 100, 1))}%) [R]",
                f"Churn signals: {_r(churn_count)} reviews ({_r(churn_pct)}%) [R]",
            ],
            "what_to_build": what_to_build,
            "success_metric": success_metric,
            "risk_if_ignored": {
                "revenue_at_risk": risk_val,
                "at_6_months": risk_6mo_str,
                "churn_signal_line": f"{_r(churn_count)} reviews contain churn-signal language",
            },
            "suggested_owner": _suggest_owner(theme),
            "q_check": {"passed": qcheck["ok"], "q1": qcheck["q1"], "q3": qcheck["q3"]},
            "quotes": quotes[:3],
        }
        cards.append(card)

    return {
        "section": 8,
        "title": "ACTION CARDS — TOP 5 ITEMS",
        "cards": cards,
    }


def _suggest_owner(theme: str) -> str:
    """Heuristic owner suggestion based on theme name."""
    theme_lower = theme.lower()
    if any(t in theme_lower for t in ["ux", "ui", "design", "navigation", "layout"]):
        return "Design — theme directly touches visual/interaction surface"
    if any(t in theme_lower for t in ["performance", "reliability", "bug", "crash", "error"]):
        return "Engineering — bug fix or reliability issue requiring code change"
    if any(t in theme_lower for t in ["pricing", "billing", "subscription"]):
        return "Product — pricing changes require cross-functional alignment"
    if any(t in theme_lower for t in ["support", "customer service"]):
        return "Customer Success — direct support quality ownership"
    if any(t in theme_lower for t in ["onboard", "setup", "tutorial"]):
        return "Product — onboarding directly impacts activation rate"
    return "Product — theme spans multiple surfaces; Product coordination recommended"


# ── Section 9: Financial Impact Model ─────────────────────────────────────────

def build_financial_impact_model(financial_impact: list[dict]) -> dict:
    """Dispatch Section 9 — Financial Impact Model with all 4 formulas."""
    if not financial_impact or financial_impact[0].get("status") == "pending_calibration":
        return {
            "section": 9,
            "title": "FINANCIAL IMPACT MODEL",
            "status": "LOCKED — provide total_users and monthly_arpu to unlock",
            "items": [],
        }

    rows = []
    for item in financial_impact[:10]:  # Top 10 roadmap items per spec
        coi = item.get("cost_of_inaction", {}) or {}
        rows.append({
            "theme": item["theme"],
            "revenue_at_risk": item.get("revenue_at_risk"),
            "revenue_at_risk_formula": item.get("revenue_at_risk_formula", ""),
            "revenue_opportunity": item.get("revenue_opportunity"),
            "revenue_opportunity_formula": item.get("revenue_opportunity_formula", ""),
            "cost_of_inaction_3mo": coi.get("3_months"),
            "cost_of_inaction_6mo": coi.get("6_months"),
            "cost_of_inaction_12mo": coi.get("12_months"),
            "coi_3mo_formula": coi.get("3mo_formula", ""),
            "coi_6mo_formula": coi.get("6mo_formula", ""),
            "coi_12mo_formula": coi.get("12mo_formula", ""),
            "roi_score": item.get("roi_score"),
            "roi_formula": item.get("roi_formula", ""),
            "confidence": item.get("confidence", "Low ⚠"),
            "status": item.get("status"),
        })

    # Insight: largest risk item
    top = max(financial_impact, key=lambda x: x.get("revenue_at_risk") or 0, default=None)
    insight_text = ""
    if top and top.get("revenue_at_risk") is not None:
        insight_text = (
            f"{top['theme']} represents the largest revenue risk at "
            f"${top['revenue_at_risk']:,.2f} [F: Revenue at Risk formula], "
            f"driven by {_r(top.get('churn_signal_count', 0))} churn-signal reviews."
        )

    return {
        "section": 9,
        "title": "FINANCIAL IMPACT MODEL",
        "status": "calibrated",
        "items": rows,
        "chart_insight_waterfall": insight_text,
    }


# ── Section 10: Sentiment Analysis Charts Data ────────────────────────────────

def build_sentiment_charts_data(report: dict, priority_scores: list[dict], financial_impact: list[dict]) -> dict:
    """
    Dispatch Section 10 — Data payloads for all 7 interactive charts.
    Chart 1: Waterfall — Risk vs Opportunity
    Chart 2: Scatter — Priority vs Financial Impact
    Chart 3: Cost of Inaction line (top 3 items)
    Chart 4: Sentiment Donut
    Chart 5: Sentiment Trend by Week
    Chart 6: Volume by Category
    Chart 7: Category × Sentiment Bubble Matrix
    """
    meta = report.get("meta", {})
    dist = report.get("sentiment_distribution", {})
    trend = report.get("sentiment_trend", {})
    roadmap = report.get("roadmap_items", [])

    # Chart 4 — Sentiment Donut
    total = meta.get("total_reviews", 1)
    values = dist.get("values", [0, 0, 0])
    labels = dist.get("labels", ["Positive", "Neutral", "Negative"])
    donut_pcts = [round(v / max(1, total) * 100, 1) for v in values]
    dominant_idx = donut_pcts.index(max(donut_pcts)) if donut_pcts else 0
    dominant_label = labels[dominant_idx] if labels else "Unknown"
    dominant_pct = donut_pcts[dominant_idx] if donut_pcts else 0

    chart4 = {
        "type": "donut",
        "labels": labels,
        "values": values,
        "percentages": donut_pcts,
        "insight": f"Dominant sentiment: {dominant_label} at {dominant_pct}% [R] of all reviews.",
    }

    # Chart 5 — Sentiment Trend
    accel_check = report.get("preflight", {}).get("checks", {}).get("check_4_sentiment_acceleration", {})
    alert_week = None
    if accel_check.get("status") == "ALERT":
        alert_data = accel_check.get("alert_data", {})
        alert_week = alert_data.get("week_id")

    latest_neg = 0
    latest_label = ""
    if trend.get("labels") and trend.get("negative"):
        latest_label = trend["labels"][-1]
        latest_neg = trend["negative"][-1]

    chart5 = {
        "type": "line",
        "labels": trend.get("labels", []),
        "positive": trend.get("positive", []),
        "neutral": trend.get("neutral", []),
        "negative": trend.get("negative", []),
        "alert_week": alert_week,
        "insight": (
            f"Most recent period ({latest_label}): {_r(latest_neg)} negative reviews."
            if latest_label else "No trend data available."
        ),
    }

    # Chart 6 — Volume by Category (horizontal bar, descending)
    sorted_roadmap = sorted(roadmap, key=lambda x: -x["volume"])
    cat_labels = [item["category"] for item in sorted_roadmap]
    cat_volumes = [item["volume"] for item in sorted_roadmap]
    chart6_insight = ""
    if len(sorted_roadmap) >= 2:
        top1 = sorted_roadmap[0]
        top2 = sorted_roadmap[1]
        margin = top1["volume"] - top2["volume"]
        chart6_insight = (
            f"{top1['category']} dominates with {_r(top1['volume'])} reviews, "
            f"{_r(margin)} more than second-place {top2['category']} ({_r(top2['volume'])})."
        )

    chart6 = {
        "type": "horizontal_bar",
        "labels": cat_labels,
        "values": cat_volumes,
        "insight": chart6_insight,
    }

    # Chart 7 — Category × Sentiment Bubble Matrix
    bubble_data = []
    for item in roadmap:
        sbd = item.get("sentiment_breakdown", {})
        vol = item["volume"]
        pos = sbd.get("Positive", 0)
        neg = sbd.get("Negative", 0)
        pos_score = round(pos / max(1, vol) * 100, 1)
        neg_score = round(neg / max(1, vol) * 100, 1)
        bubble_data.append({
            "label": item["category"],
            "x": pos_score,  # positivity score
            "y": neg_score,  # negativity score
            "r": vol,         # bubble size = volume
        })

    # Most polarized: highest sum of both axes
    if bubble_data:
        most_polarized = max(bubble_data, key=lambda b: b["x"] + b["y"])
        chart7_insight = (
            f"{most_polarized['label']} has the most polarized sentiment "
            f"(positive: {most_polarized['x']}% [R], negative: {most_polarized['y']}% [R])."
        )
    else:
        chart7_insight = "Insufficient data for polarization analysis."

    chart7 = {
        "type": "bubble",
        "data": bubble_data,
        "insight": chart7_insight,
    }

    # Charts 1–3: Financial (only if calibrated)
    fin_calibrated = financial_impact and financial_impact[0].get("status") == "calibrated"

    # Chart 1 — Waterfall: Risk vs Opportunity
    chart1 = {"type": "waterfall", "status": "LOCKED", "items": []}
    # Chart 2 — Scatter: Priority vs Financial Impact
    chart2 = {"type": "scatter", "status": "LOCKED", "items": []}
    # Chart 3 — Line: Cost of Inaction, top 3 items
    chart3 = {"type": "line_coi", "status": "LOCKED", "items": []}

    if fin_calibrated:
        ps_lookup = {ps["theme"]: ps for ps in (priority_scores or [])}

        # Chart 1
        chart1_items = []
        for fi in financial_impact[:10]:
            chart1_items.append({
                "theme": fi["theme"],
                "revenue_at_risk": fi.get("revenue_at_risk", 0),
                "revenue_opportunity": fi.get("revenue_opportunity", 0),
            })
        top_risk_item = max(chart1_items, key=lambda x: x["revenue_at_risk"], default=None)
        chart1 = {
            "type": "waterfall",
            "status": "calibrated",
            "items": chart1_items,
            "insight": (
                f"{top_risk_item['theme']} represents the largest revenue risk at "
                f"${top_risk_item['revenue_at_risk']:,.2f} [F: Revenue at Risk formula]."
                if top_risk_item else ""
            ),
        }

        # Chart 2
        chart2_items = []
        for fi in financial_impact[:10]:
            pss = ps_lookup.get(fi["theme"], {})
            total_impact = (fi.get("revenue_at_risk") or 0) + (fi.get("revenue_opportunity") or 0)
            chart2_items.append({
                "theme": fi["theme"],
                "priority_score": pss.get("priority_score", 0),
                "financial_impact": total_impact,
                "quadrant": _classify_quadrant_label(
                    pss.get("priority_score", 0), total_impact
                ),
            })
        # Count quadrant distribution
        quadrant_counts: dict[str, int] = {}
        for item in chart2_items:
            q = item["quadrant"]
            quadrant_counts[q] = quadrant_counts.get(q, 0) + 1
        most_common_q = max(quadrant_counts, key=quadrant_counts.get) if quadrant_counts else "N/A" # type: ignore[arg-type]
        chart2 = {
            "type": "scatter",
            "status": "calibrated",
            "items": chart2_items,
            "quadrant_labels": {
                "top_right": "Build Now — High Priority + High Revenue Impact",
                "top_left": "Fix Fast — High Priority, Lower Revenue",
                "bottom_right": "Investigate — Low Priority Signal, High Revenue Impact",
                "bottom_left": "Deprioritize or Drop",
            },
            "insight": (
                f"Most items in '{most_common_q}' quadrant ({quadrant_counts.get(most_common_q, 0)} items)."
            ),
        }

        # Chart 3 — Cost of Inaction, top 3
        top3_risks = sorted(
            [fi for fi in financial_impact if fi.get("cost_of_inaction")],
            key=lambda x: x.get("revenue_at_risk") or 0,
            reverse=True,
        )[:3]

        chart3_series = []
        for fi in top3_risks:
            vel_score = fi.get("velocity_score_used")
            points = {}
            for mo in range(1, 13):
                risk = fi.get("revenue_at_risk", 0)
                monthly_rate = (vel_score / 10) * 0.005 if vel_score is not None else 0.0025
                points[mo] = round(risk * ((1 + monthly_rate) ** mo), 2)
            chart3_series.append({
                "theme": fi["theme"],
                "points": points,
                "velocity_score": vel_score,
            })

        coi_insight = ""
        if len(chart3_series) >= 2:
            s1, s2 = chart3_series[0], chart3_series[-1]
            diff = round((s1["points"].get(12, 0) - s2["points"].get(12, 0)), 2)
            coi_insight = (
                f"At 12 months, {s1['theme']} inaction costs ${diff:,.2f} more than "
                f"{s2['theme']} due to higher urgency velocity "
                f"({s1.get('velocity_score', 'N/A')} vs {s2.get('velocity_score', 'N/A')}) [F: Cost of Inaction formula]."
            )

        chart3 = {
            "type": "line_coi",
            "status": "calibrated",
            "items": chart3_series,
            "insight": coi_insight,
        }

    return {
        "section": 10,
        "title": "SENTIMENT ANALYSIS CHARTS",
        "chart_1_waterfall": chart1,
        "chart_2_scatter": chart2,
        "chart_3_coi_line": chart3,
        "chart_4_donut": chart4,
        "chart_5_trend": chart5,
        "chart_6_volume_bar": chart6,
        "chart_7_bubble": chart7,
    }


def _classify_quadrant_label(priority_score: float, financial_impact: float) -> str:
    high_p = priority_score >= 5.0
    high_f = financial_impact > 0
    if high_p and high_f:
        return "Build Now — High Priority + High Revenue Impact"
    elif high_p:
        return "Fix Fast — High Priority, Lower Revenue"
    elif high_f:
        return "Investigate — Low Priority Signal, High Revenue Impact"
    else:
        return "Deprioritize or Drop"


# ── Section 11: Representative Quotes ─────────────────────────────────────────

def build_representative_quotes(report: dict) -> dict:
    """
    Dispatch Section 11 — Representative Quotes (deduplicated, 3 per category max).
    Quotes already deduped in analyzer — we just format them here.
    """
    raw_quotes = report.get("representative_quotes", [])
    categories = []
    for q_item in raw_quotes:
        cat = q_item.get("category", "Unknown")
        quotes = q_item.get("quotes", [])
        formatted = []
        for q in quotes[:3]:
            formatted.append({
                "text": q.get("text", ""),
                "rating": _r(q.get("rating_display", q.get("rating", "N/A"))),
                "date": q.get("date", "N/A"),
                "signal": q.get("signal_type", "neutral"),
                "hash": q.get("hash", ""),
            })
        categories.append({
            "category": cat,
            "count": len(quotes),
            "insufficient": q_item.get("insufficient", False),
            "quotes": formatted,
        })

    return {
        "section": 11,
        "title": "REPRESENTATIVE QUOTES",
        "categories": categories,
        "total_categories": len(categories),
    }


# ── Section 12: Risks & Blind Spots ──────────────────────────────────────────

def build_risks_and_blind_spots(
    report: dict,
    priority_scores: list[dict],
    financial_impact: list[dict],
) -> dict:
    """
    Dispatch Section 12 — Risks & Blind Spots (5 deterministic checks, A-E).
    All checks are data-driven with named conditions.
    """
    meta = report.get("meta", {})
    roadmap = report.get("roadmap_items", [])
    preflight = report.get("preflight", {})
    pf_checks = preflight.get("checks", {}) if isinstance(preflight, dict) else {}

    checks = []

    # A: High Other% — taxonomy coverage risk
    unclassified_pct = meta.get("unclassified_pct", 0.0)
    checks.append({
        "id": "A",
        "name": "Taxonomy Coverage Risk",
        "status": "RISK" if unclassified_pct > 15 else "CLEAR",
        "message": (
            f"⚠ {unclassified_pct}% of reviews unclassified — scores may undercount true pain. "
            f"Consider expanding taxonomy or triggering Taxonomy Adaptation Gate."
            if unclassified_pct > 15 else
            f"Classification coverage acceptable ({100 - unclassified_pct:.1f}% classified)."
        ),
        "value": _r(unclassified_pct),
    })

    # B: Single category dominance
    volumes = sorted([item["volume"] for item in roadmap], reverse=True)
    dominance_ratio = (volumes[0] / max(1, sum(volumes))) if volumes else 0
    checks.append({
        "id": "B",
        "name": "Category Dominance",
        "status": "RISK" if dominance_ratio > 0.60 else "CLEAR",
        "message": (
            f"⚠ Top category accounts for {round(dominance_ratio * 100)}% of classified reviews — "
            f"may crowd out other important signals."
            if dominance_ratio > 0.60 else
            f"Category distribution healthy (top category: {round(dominance_ratio * 100)}%)."
        ),
        "value": _f(round(dominance_ratio, 3), "Top category volume / total classified"),
    })

    # C: Low review count warning
    total = meta.get("total_reviews", 0)
    checks.append({
        "id": "C",
        "name": "Sample Size",
        "status": "RISK" if total < 50 else "CLEAR",
        "message": (
            f"⚠ Only {total} reviews — statistical confidence is low. "
            f"Scores and financial projections should be treated as directional only."
            if total < 50 else
            f"Sample size adequate ({total} reviews)."
        ),
        "value": _r(total),
    })

    # D: Financial model locked
    fin_locked = not financial_impact or financial_impact[0].get("status") != "calibrated"
    checks.append({
        "id": "D",
        "name": "Financial Model Status",
        "status": "RISK" if fin_locked else "CLEAR",
        "message": (
            "⚠ Financial inputs not provided — Revenue at Risk and Cost of Inaction are LOCKED. "
            "Provide total_users and monthly_arpu to unlock."
            if fin_locked else
            "Financial model calibrated — all revenue projections are active."
        ),
        "value": "LOCKED [U]" if fin_locked else "CALIBRATED [U]",
    })

    # E: No date data (velocity axis excluded)
    has_dates = meta.get("has_date_col", False)
    checks.append({
        "id": "E",
        "name": "Urgency Velocity Axis",
        "status": "RISK" if not has_dates else "CLEAR",
        "message": (
            "⚠ No date column detected — Urgency Velocity axis excluded and weights rebalanced. "
            "Trending themes may be under-prioritized."
            if not has_dates else
            "Date column detected — Urgency Velocity axis active."
        ),
        "value": "Excluded [D: no date column]" if not has_dates else "Active [R]",
    })

    risk_count = sum(1 for c in checks if c["status"] == "RISK")
    return {
        "section": 12,
        "title": "RISKS & BLIND SPOTS",
        "checks": checks,
        "summary": f"{risk_count} risk(s) identified across {len(checks)} checks.",
    }


# ── Section 13: Watch List (Zero-Review & Low Confidence Items) ──────────────

def build_watch_list(report: dict) -> dict:
    """
    Dispatch Spec: Any item with 0 reviews or < 10 reviews is excluded from scoring
    and moved to the Watch List with a specific note.
    """
    watch_list = report.get("watch_list", [])
    
    rows = []
    for item in watch_list:
        rows.append({
            "theme": item.get("category", "Unknown"),
            "volume": item.get("volume", 0),
            "confidence": item.get("confidence", "None"),
            "message": item.get("message", "Low volume — scores volatile."),
        })
        
    return {
        "section": 13,
        "title": "WATCH LIST",
        "note": "Items not prioritized due to insufficient data volume.",
        "items": rows,
        "count": len(rows),
    }


# ── Taxonomy Gate Echo (Section 0 addon) ──────────────────────────────────────

def build_taxonomy_gate_echo(gate_result: dict | None) -> dict:
    """
    Echoes the taxonomy gate outcome into the report header area.
    Only populated when the gate was run (i.e., file was uploaded fresh).
    """
    if gate_result is None:
        return {"taxonomy_gate": "NOT RUN"}
    return {
        "taxonomy_gate": "PASSED" if gate_result.get("passes") else "CUSTOM TAXONOMY APPLIED",
        "coverage_pct": gate_result.get("coverage_pct", "N/A"),
        "matched": gate_result.get("matched", "N/A"),
        "sampled": gate_result.get("sampled", "N/A"),
    }


# ── Master Orchestrator ────────────────────────────────────────────────────────

def assemble_dispatch_report(
    run_id: str,
    filename: str,
    report: dict,
    narratives: dict,
    priority_scores: list[dict],
    financial_impact: list[dict],
    financial_inputs_echo: dict,
    effort_method: str,
    velocity_available: bool = True,
    taxonomy_gate_result: dict | None = None,
) -> dict:
    """
    Master orchestrator — assembles all 12 Dispatch v3.0 document sections
    in strict order. Returns the complete dispatch_report dict.
    """
    from datetime import datetime, timezone
    generated_at = datetime.now(tz=timezone.utc)

    meta = report.get("meta", {})
    preflight = report.get("preflight", {})
    representative_quotes = report.get("representative_quotes", [])

    # Build action cards first (needed for count in synthesis status)
    s8 = build_action_cards(priority_scores, report, financial_impact, representative_quotes)
    action_cards_count = len(s8["cards"])

    sections = {
        "s0_run_identity": build_run_identity_header(
            run_id=run_id,
            filename=filename,
            total_reviews=meta.get("total_reviews", 0),
            generated_at=generated_at,
        ),
        "s1_effort_scoring": build_effort_scoring_input(effort_method),
        "s2_synthesis_status": build_synthesis_status_panel(
            report, priority_scores, financial_impact, preflight, action_cards_count
        ),
        "s3_preflight_validation": build_preflight_validation(preflight),
        "s4_sentiment_alert": build_sentiment_acceleration_alert(preflight),
        "s5_data_quality_alert": build_data_quality_alert(preflight),
        "s6_financial_inputs": build_financial_input_panel(
            total_users=financial_inputs_echo.get("total_users"),
            monthly_arpu=financial_inputs_echo.get("monthly_arpu"),
            segment_weights=financial_inputs_echo.get("segment_weights"),
            sprint_cost=financial_inputs_echo.get("sprint_cost"),
        ),
        "s7_priority_matrix": build_priority_matrix(
            priority_scores, report, velocity_available, effort_method
        ),
        "s8_action_cards": s8,
        "s9_financial_model": build_financial_impact_model(financial_impact),
        "s10_charts": build_sentiment_charts_data(report, priority_scores, financial_impact),
        "s11_quotes": build_representative_quotes(report),
        "s12_risks": build_risks_and_blind_spots(report, priority_scores, financial_impact),
        "s13_watch_list": build_watch_list(report),
    }

    # Taxonomy gate echo (if gate was run)
    if taxonomy_gate_result:
        sections["s0_run_identity"]["taxonomy_gate"] = build_taxonomy_gate_echo(taxonomy_gate_result)

    return {
        "run_id": run_id,
        "generated_at": generated_at.isoformat(),
        "sections": sections,
    }
