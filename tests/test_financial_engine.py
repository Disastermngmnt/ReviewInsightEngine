"""
Tests for the financial impact engine.
"""
import pytest
from core.financial_engine import (
    compute_financial_impact,
    FinancialInputs,
    _compute_revenue_at_risk,
    _compute_revenue_opportunity,
    _compute_cost_of_inaction,
    _compute_roi,
    _confidence_level,
)


class TestFinancialFormulas:
    def test_revenue_at_risk(self):
        # 10 churn signals out of 100 reviews, 1000 users, $50/mo ARPU
        # = (10/100) * 1000 * 50 * 12 = $60,000
        result = _compute_revenue_at_risk(10, 100, 1000, 50.0)
        assert result == 60000.0
    
    def test_revenue_at_risk_zero_churn(self):
        result = _compute_revenue_at_risk(0, 100, 1000, 50.0)
        assert result == 0.0
    
    def test_revenue_at_risk_zero_reviews(self):
        result = _compute_revenue_at_risk(10, 0, 1000, 50.0)
        assert result == 0.0
    
    def test_revenue_opportunity(self):
        # 20 expansion signals out of 100 reviews, 1000 users, $50/mo ARPU
        # = (20/100) * 1000 * 50 * 12 * 0.20 = $24,000
        result = _compute_revenue_opportunity(20, 100, 1000, 50.0)
        assert result == 24000.0
    
    def test_cost_of_inaction_high_urgency(self):
        result = _compute_cost_of_inaction(10, 100, 1000, 50.0, urgency_density=0.6)
        base = 60000.0  # same as revenue_at_risk
        # High urgency → 1.5x compound
        assert result["3_months"] == round(base * 1.5, 2)
        assert result["6_months"] == round(base * 1.5 ** 2, 2)
        assert result["12_months"] == round(base * 1.5 ** 4, 2)
    
    def test_cost_of_inaction_low_urgency(self):
        result = _compute_cost_of_inaction(10, 100, 1000, 50.0, urgency_density=0.1)
        base = 60000.0
        # Low urgency → 1.1x compound
        assert result["3_months"] == round(base * 1.1, 2)
    
    def test_roi_with_sprint_cost(self):
        result = _compute_roi(60000.0, 24000.0, 15000.0)
        # (60000 + 24000) / 15000 = 5.6
        assert result == 5.6
    
    def test_roi_without_sprint_cost(self):
        assert _compute_roi(60000.0, 24000.0, None) is None
        assert _compute_roi(60000.0, 24000.0, 0) is None
    
    def test_confidence_levels(self):
        assert _confidence_level(25) == "High"
        assert _confidence_level(15) == "Medium"
        assert _confidence_level(5) == "Low"


class TestComputeFinancialImpact:
    @pytest.fixture
    def sample_signals(self):
        return {
            "Reliability": {
                "volume": 25,
                "churn_signal_count": 8,
                "expansion_signal_count": 2,
                "urgency_density": 0.4,
            },
            "Feature Gaps": {
                "volume": 15,
                "churn_signal_count": 1,
                "expansion_signal_count": 10,
                "urgency_density": 0.1,
            },
        }
    
    def test_calibrated_output(self, sample_signals):
        inputs = FinancialInputs(total_users=10000, monthly_arpu=50.0, sprint_cost=20000.0)
        result = compute_financial_impact(sample_signals, inputs, total_reviews=100)
        
        assert len(result) == 2
        for item in result:
            assert item["status"] == "calibrated"
            assert item["revenue_at_risk"] is not None
            assert item["revenue_opportunity"] is not None
            assert item["cost_of_inaction"] is not None
            assert item["roi_score"] is not None
    
    def test_pending_calibration(self, sample_signals):
        inputs = FinancialInputs()  # No business data
        result = compute_financial_impact(sample_signals, inputs, total_reviews=100)
        
        for item in result:
            assert item["status"] == "pending_calibration"
            assert item["revenue_at_risk"] is None
            assert item["roi_score"] is None
    
    def test_partial_calibration_no_sprint_cost(self, sample_signals):
        inputs = FinancialInputs(total_users=10000, monthly_arpu=50.0)
        result = compute_financial_impact(sample_signals, inputs, total_reviews=100)
        
        for item in result:
            assert item["status"] == "calibrated"
            assert item["revenue_at_risk"] is not None
            assert item["roi_score"] is None  # No sprint cost → no ROI

    def test_sorted_by_impact(self, sample_signals):
        inputs = FinancialInputs(total_users=10000, monthly_arpu=50.0)
        result = compute_financial_impact(sample_signals, inputs, total_reviews=100)
        
        # First item should have higher total financial impact
        if len(result) >= 2:
            impact_0 = (result[0]["revenue_at_risk"] or 0) + (result[0]["revenue_opportunity"] or 0)
            impact_1 = (result[1]["revenue_at_risk"] or 0) + (result[1]["revenue_opportunity"] or 0)
            assert impact_0 >= impact_1

    def test_confidence_from_volume(self, sample_signals):
        inputs = FinancialInputs(total_users=10000, monthly_arpu=50.0)
        result = compute_financial_impact(sample_signals, inputs, total_reviews=100)
        
        confidence_map = {item["theme"]: item["confidence"] for item in result}
        assert confidence_map["Reliability"] == "High"     # 25 mentions
        assert confidence_map["Feature Gaps"] == "Medium"   # 15 mentions
