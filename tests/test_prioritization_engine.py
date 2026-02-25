"""
Tests for the prioritization engine.
"""
import pytest
from core.prioritization_engine import compute_priority_scores, classify_quadrant


class TestComputePriorityScores:
    @pytest.fixture
    def sample_theme_scores(self):
        """Sample AI-generated theme scores."""
        return [
            {
                "theme": "Performance",
                "impact_breadth": {"score": 8.0, "rationale": "High volume"},
                "pain_intensity": {"score": 9.0, "rationale": "Many urgency signals"},
                "strategic_alignment": {"score": 7.0, "rationale": "Core feature"},
                "competitive_exposure": {"score": 6.0, "rationale": "Competitors are faster"},
                "effort_inverse": {"score": 5.0, "rationale": "Systemic issue"},
            },
            {
                "theme": "UX/UI",
                "impact_breadth": {"score": 5.0, "rationale": "Moderate volume"},
                "pain_intensity": {"score": 4.0, "rationale": "Low urgency"},
                "strategic_alignment": {"score": 6.0, "rationale": "Visual refresh"},
                "competitive_exposure": {"score": 3.0, "rationale": "Not a differentiator"},
                "effort_inverse": {"score": 8.0, "rationale": "Quick CSS changes"},
            },
        ]

    def test_ranking_order(self, sample_theme_scores):
        result = compute_priority_scores(sample_theme_scores)
        assert len(result) == 2
        assert result[0]["theme"] == "Performance"  # Higher scores first
        assert result[1]["theme"] == "UX/UI"
    
    def test_rank_assignment(self, sample_theme_scores):
        result = compute_priority_scores(sample_theme_scores)
        assert result[0]["rank"] == 1
        assert result[1]["rank"] == 2
    
    def test_score_range(self, sample_theme_scores):
        result = compute_priority_scores(sample_theme_scores)
        for item in result:
            assert 0.0 <= item["priority_score"] <= 10.0
    
    def test_default_weights_applied(self, sample_theme_scores):
        result = compute_priority_scores(sample_theme_scores)
        # Performance: (8*0.25)+(9*0.30)+(7*0.20)+(6*0.15)+(5*0.10) = 2+2.7+1.4+0.9+0.5 = 7.5
        assert abs(result[0]["priority_score"] - 7.50) < 0.1

    def test_custom_weights(self, sample_theme_scores):
        custom = {
            "impact_breadth": 1.0,
            "pain_intensity": 0.0,
            "strategic_alignment": 0.0,
            "competitive_exposure": 0.0,
            "effort_inverse": 0.0,
        }
        result = compute_priority_scores(sample_theme_scores, weights=custom)
        # Only impact_breadth matters: Performance=8.0, UX/UI=5.0
        assert result[0]["theme"] == "Performance"
        assert abs(result[0]["priority_score"] - 8.0) < 0.1
    
    def test_axis_data_preserved(self, sample_theme_scores):
        result = compute_priority_scores(sample_theme_scores)
        assert "impact_breadth" in result[0]
        assert "rationale" in result[0]["impact_breadth"]
    
    def test_empty_input(self):
        result = compute_priority_scores([])
        assert result == []
    
    def test_all_zeros(self):
        scores = [{
            "theme": "Test",
            "impact_breadth": {"score": 0, "rationale": "None"},
            "pain_intensity": {"score": 0, "rationale": "None"},
            "strategic_alignment": {"score": 0, "rationale": "None"},
            "competitive_exposure": {"score": 0, "rationale": "None"},
            "effort_inverse": {"score": 0, "rationale": "None"},
        }]
        result = compute_priority_scores(scores)
        assert result[0]["priority_score"] == 0.0


class TestClassifyQuadrant:
    def test_build_immediately(self):
        assert classify_quadrant(7.0, 50000) == "Build Immediately"
    
    def test_fix_loud(self):
        assert classify_quadrant(7.0, 0) == "Fix (Loud but Low Impact)"
    
    def test_investigate(self):
        assert classify_quadrant(3.0, 50000) == "Investigate (Underreported)"
    
    def test_backlog(self):
        assert classify_quadrant(3.0, 0) == "Backlog/Drop"
    
    def test_no_financial_data(self):
        result = classify_quadrant(7.0, None)
        assert "pending" in result.lower()
