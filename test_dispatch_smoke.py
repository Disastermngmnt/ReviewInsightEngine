"""Dispatch v3.0 Smoke Test — verifies all new modules work end-to-end."""

import sys
sys.path.insert(0, '.')

from core.analyzer import Analyzer
from core.prioritization_engine import compute_priority_scores, _timeline_bucket
from core.financial_engine import compute_financial_impact, FinancialInputs
from core.ai_engine import generate_run_id
from core.dispatch_formatter import assemble_dispatch_report, build_run_identity_header, build_preflight_validation


def test_analyzer():
    a = Analyzer()
    cols = ['review', 'rating', 'date']
    # Create ≥10 unique reviews per category so items appear in roadmap_items
    perf_reviews = [
        ("App crashes constantly after the update. This is a nightmare!", 1, "2024-01-15"),
        ("Performance is so slow it's unusable. I might cancel.", 1, "2024-01-16"),
        ("The app freezes every time I open the dashboard.", 2, "2024-01-17"),
        ("Crashes again on startup. Terrible performance.", 1, "2024-01-18"),
        ("Loading time is ridiculous - takes 2 minutes to start.", 2, "2024-01-20"),
        ("App is crashing during checkout, lost a sale!", 1, "2024-02-01"),
        ("Very sluggish response, crashes frequently.", 2, "2024-02-02"),
        ("App keeps freezing on mobile. Completely unusable product.", 1, "2024-02-03"),
        ("Performance degraded after last patch. Please fix urgently.", 2, "2024-02-10"),
        ("Crash on save every single time. I will leave if not fixed.", 1, "2024-02-15"),
        ("The app is slower than ever after the update.", 2, "2024-02-20"),
        ("Frequent crashes are killing my productivity, need fix fast.", 1, "2024-03-01"),
    ]
    ui_reviews = [
        ("The UI is confusing and navigation is impossible", 2, "2024-01-15"),
        ("Interface design is terrible, hard to find anything.", 2, "2024-01-16"),
        ("Navigation is a mess. I can't find the settings at all.", 2, "2024-01-17"),
        ("Too many clicks to do simple tasks. Bad UX design overall.", 2, "2024-01-18"),
        ("The menu is hidden and the layout is counterintuitive.", 2, "2024-01-20"),
        ("Color scheme makes it very hard to read. Poor design choices.", 3, "2024-02-01"),
        ("The new UI broke my workflow. Reverted to old version.", 2, "2024-02-05"),
        ("Icons have no labels, very confusing to use daily.", 2, "2024-02-10"),
        ("Dashboard is overwhelming. Too much information shown.", 3, "2024-02-15"),
        ("UI feels outdated compared to all main competitors.", 2, "2024-02-20"),
        ("Too many pop-ups interrupting my daily work.", 2, "2024-03-01"),
        ("The font is too small, hard to read on mobile devices.", 2, "2024-03-05"),
    ]
    data = [list(r) for r in perf_reviews + ui_reviews]

    result = a.run(cols, data)
    assert 'meta' in result, "Missing meta key"
    assert 'preflight' in result, "Missing preflight key"
    assert 'roadmap_items' in result, "Missing roadmap_items key"

    meta = result['meta']
    total = meta['total_reviews']
    assert total == len(data), f"Expected {len(data)} reviews, got {total}"
    assert meta['has_date_col'] == True, "Date column not detected"
    assert meta['has_rating_col'] == True, "Rating column not detected"

    # Preflight checks
    pf = result['preflight']
    assert 'checks' in pf, "Preflight missing checks"
    assert len(pf['checks']) == 6, f"Expected 6 checks, got {len(pf['checks'])}"
    assert 'summary' in pf, "Preflight missing summary"

    # Roadmap items (with ≥10 reviews per category, should appear here)
    items = result['roadmap_items']
    assert len(items) > 0, f"No roadmap items! watch_list={len(result.get('watch_list',[]))}, classified={meta.get('total_classified')}"
    for item in items:
        assert 'pain_intensity_precomputed' in item, f"Missing pain_intensity for {item['category']}"
        assert 'impact_breadth_precomputed' in item, f"Missing impact_breadth for {item['category']}"
        pain = item['pain_intensity_precomputed']
        impact = item['impact_breadth_precomputed']
        assert 0 <= pain <= 10, f"Pain out of range: {pain}"
        assert 0 <= impact <= 10, f"Impact out of range: {impact}"

    print(f"  ✓ Analyzer: {meta['total_reviews']} reviews, {len(items)} roadmap items, {len(pf['checks'])} preflight checks")
    return result


def test_prioritization_engine():
    # Simulate AI-scored themes
    fake_ai_scores = [
        {
            "theme": "Performance",
            "pain_intensity": {"score": 8.5, "rationale": "High pain"},
            "impact_breadth": {"score": 7.0, "rationale": "Wide impact"},
            "urgency_velocity": {"score": 9.0, "rationale": "Accelerating"},
            "strategic_leverage": {"score": 6.5, "rationale": "Moderate leverage"},
            "effort_inverse": {"score": 3.0, "rationale": "Complex fix"},
        },
        {
            "theme": "UI Design",
            "pain_intensity": {"score": 5.0, "rationale": "Moderate pain"},
            "impact_breadth": {"score": 4.0, "rationale": "Moderate breadth"},
            "urgency_velocity": {"score": 3.0, "rationale": "Stable"},
            "strategic_leverage": {"score": 7.0, "rationale": "High strategic value"},
            "effort_inverse": {"score": 6.0, "rationale": "Quick win"},
        },
    ]

    scored = compute_priority_scores(fake_ai_scores, effort_method="B", velocity_available=True)
    assert len(scored) == 2, f"Expected 2 scored items, got {len(scored)}"
    assert scored[0]['rank'] == 1, "First item should be rank 1"
    assert scored[0]['theme'] == 'Performance', f"Expected Performance first, got {scored[0]['theme']}"
    assert 'normalized_score' in scored[0], "Missing normalized_score"
    assert 'timeline' in scored[0], "Missing timeline"
    assert 0 <= scored[0]['priority_score'] <= 10, "Priority score out of range"

    # Test timeline buckets
    assert _timeline_bucket(0.85) == "Q1 – Ship Now"
    assert _timeline_bucket(0.65) == "Q2 – Next Quarter"
    assert _timeline_bucket(0.45) == "Q3 – Mid-term"
    assert _timeline_bucket(0.30) == "Q4 / Backlog"

    print(f"  ✓ Prioritization: {scored[0]['theme']} priority={scored[0]['priority_score']}, timeline={scored[0]['timeline']}")


def test_financial_engine():
    from core.signal_extractor import extract_signals, aggregate_theme_signals

    # Create simple theme signals
    theme_signals = {
        "Performance": {
            "volume": 20,
            "churn_signal_count": 5,
            "expansion_signal_count": 2,
        },
        "UI Design": {
            "volume": 10,
            "churn_signal_count": 1,
            "expansion_signal_count": 3,
        },
    }

    # Uncalibrated
    fin_uncal = FinancialInputs()
    result_uncal = compute_financial_impact(theme_signals, fin_uncal, 30)
    assert all(r['status'] == 'pending_calibration' for r in result_uncal), "Should all be pending"

    # Calibrated
    fin_cal = FinancialInputs(total_users=10000, monthly_arpu=50.0, sprint_cost=15000.0)
    result_cal = compute_financial_impact(theme_signals, fin_cal, 30)
    assert all(r['status'] == 'calibrated' for r in result_cal), "Should all be calibrated"
    risk = result_cal[0]['revenue_at_risk']
    assert risk is not None and risk > 0, "Revenue at risk should be positive"
    assert 'cost_of_inaction' in result_cal[0], "Missing cost_of_inaction"

    print(f"  ✓ Financial Engine: revenue_at_risk={result_cal[0]['revenue_at_risk']:.2f}, formula={result_cal[0]['revenue_at_risk_formula'][:50]}")


def test_run_id():
    rid = generate_run_id(b"test data")
    assert len(rid) > 10, "Run ID too short"
    assert "-" in rid, "Run ID missing separator"
    rid2 = generate_run_id(b"different data")
    assert rid != rid2, "Different data should produce different run IDs"
    print(f"  ✓ Run ID: {rid}")


def test_dispatch_formatter():
    # Build a minimal report structure
    minimal_report = {
        "meta": {
            "total_reviews": 30,
            "pre_dedup_count": 32,
            "duplicates_removed": 2,
            "total_classified": 28,
            "unclassified_count": 2,
            "unclassified_pct": 6.7,
            "has_date_col": True,
            "has_rating_col": True,
            "rating_scale": 5,
            "sentiment_source": "rating",
            "top_themes": ["Performance", "UI Design"],
            "sentiment_distribution": {"Positive": 30.0, "Neutral": 30.0, "Negative": 40.0},
            "date_range": {"from": "2024-01-01", "to": "2024-03-31"},
            "low_review_warning": False,
        },
        "preflight": {
            "checks": {
                "check_1_classification_coverage": {"status": "PASS", "other_pct": 6.7, "other_count": 2, "message": "OK"},
                "check_2_duplicate_detection": {"status": "WARN", "duplicates_found": 2, "duplicates_pct": 6.3, "message": "2 dupes removed"},
                "check_3_quote_integrity": {"status": "PASS", "conflict_count": 0, "message": "Clean"},
                "check_4_sentiment_acceleration": {"status": "PASS", "alert_data": None, "message": "No alert"},
                "check_5_score_auditability": {"status": "PASS", "has_date_data": True, "message": "Date detected"},
                "check_6_minimum_data": {"status": "PASS", "classified_count": 28, "message": "Sufficient"},
            },
            "summary": {"passed": 5, "warned": 1, "failed": 0, "alerted": 0, "halt": False, "display": "5 passed / 1 warned / 0 failed / 0 alerted"},
        },
        "roadmap_items": [
            {
                "category": "Performance",
                "volume": 20,
                "confidence": "High",
                "sentiment_breakdown": {"Positive": 3, "Neutral": 5, "Negative": 12},
                "avg_rating": 2.1,
                "pain_intensity_precomputed": 7.8,
                "impact_breadth_precomputed": 7.1,
                "churn_signal_count": 5,
                "expansion_signal_count": 1,
                "urgency_density": 0.4,
                "_legacy_priority": 0.72,
                "rank": 1,
            }
        ],
        "watch_list": [],
        "representative_quotes": [
            {
                "category": "Performance",
                "quotes": [{"text": "App crashes all the time", "sentiment": "Negative", "rating": 1.0, "date": "2024-02-01", "signal_type": "churn", "hash": "abc123", "rating_display": "1.0★"}],
                "insufficient": True,
                "available_count": 1,
            }
        ],
    }

    priority_scores = [
        {
            "rank": 1,
            "theme": "Performance",
            "priority_score": 7.85,
            "normalized_score": 0.785,
            "timeline": "Q2 – Next Quarter",
            "weight_label": "",
            "pain_intensity": {"score": 8.0, "rationale": "High pain"},
            "impact_breadth": {"score": 7.0, "rationale": "Wide impact"},
            "urgency_velocity": {"score": 9.0, "rationale": "Accelerating"},
            "strategic_leverage": {"score": 6.0, "rationale": "Moderate"},
            "effort_inverse": {"score": 3.0, "rationale": "Complex"},
        }
    ]

    fin_cal = FinancialInputs(total_users=10000, monthly_arpu=50.0, sprint_cost=15000.0)
    financial_impact = compute_financial_impact({"Performance": {"volume": 20, "churn_signal_count": 5, "expansion_signal_count": 1}}, fin_cal, 30, priority_scores=priority_scores)

    run_id = generate_run_id(b"test")

    dispatch = assemble_dispatch_report(
        run_id=run_id,
        filename="test_reviews.csv",
        report=minimal_report,
        narratives={"executive_summary": "Test narrative"},
        priority_scores=priority_scores,
        financial_impact=financial_impact,
        financial_inputs_echo={"total_users": 10000, "monthly_arpu": 50.0},
        effort_method="B",
    )

    assert 'sections' in dispatch, "Missing sections"
    assert 'run_id' in dispatch, "Missing run_id"
    assert dispatch['run_id'] == run_id, "Run ID mismatch"

    sections = dispatch['sections']
    assert 's0_run_identity' in sections, "Missing section 0"
    assert 's3_preflight_validation' in sections, "Missing section 3"
    assert 's7_priority_matrix' in sections, "Missing section 7"
    assert 's8_action_cards' in sections, "Missing section 8"
    assert 's12_risks' in sections, "Missing section 12"

    # Section 0 checks
    s0 = sections['s0_run_identity']
    assert s0['run_id'] == run_id
    assert s0['file'] == 'test_reviews.csv'

    # Section 3 checks
    s3 = sections['s3_preflight_validation']
    assert len(s3['checks']) == 6, f"Expected 6 checks in section 3, got {len(s3['checks'])}"

    print(f"  ✓ Dispatch Formatter: {len(sections)} sections, run_id={run_id[:20]}...")


if __name__ == '__main__':
    print("Running Dispatch v3.0 Smoke Tests...")
    tests = [
        ("Analyzer", test_analyzer),
        ("Prioritization Engine", test_prioritization_engine),
        ("Financial Engine", test_financial_engine),
        ("Run ID Generation", test_run_id),
        ("Dispatch Formatter", test_dispatch_formatter),
    ]
    passed = 0
    for name, fn in tests:
        print(f"\n[{name}]")
        try:
            fn()
            passed += 1
        except Exception as e:
            print(f"  ✗ FAILED: {e}")
            import traceback
            traceback.print_exc()

    print(f"\n{'='*50}")
    print(f"Results: {passed}/{len(tests)} tests passed")
    if passed == len(tests):
        print("✓ ALL DISPATCH v3.0 SMOKE TESTS PASSED")
    else:
        print("✗ SOME TESTS FAILED — check output above")
        sys.exit(1)
