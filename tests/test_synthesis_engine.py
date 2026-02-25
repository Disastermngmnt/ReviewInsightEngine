"""
Tests for synthesis and validation engine.
"""
import pytest
from core.synthesis_engine import (
    SynthesisEngine,
    check_sentiment_alignment,
    check_top_theme_consistency,
    check_score_plausibility,
    _grade
)


class TestGradeHelper:
    def test_grade_a(self):
        assert _grade(95) == "A"
        assert _grade(90) == "A"
    
    def test_grade_b(self):
        assert _grade(85) == "B"
        assert _grade(80) == "B"
    
    def test_grade_c(self):
        assert _grade(70) == "C"
        assert _grade(65) == "C"
    
    def test_grade_d(self):
        assert _grade(55) == "D"
        assert _grade(50) == "D"
    
    def test_grade_f(self):
        assert _grade(45) == "F"
        assert _grade(0) == "F"


class TestSentimentAlignment:
    def test_aligned_negative_sentiment(self):
        report = {
            "meta": {
                "sentiment_distribution": {
                    "Positive": 20,
                    "Neutral": 20,
                    "Negative": 60
                }
            }
        }
        narratives = {
            "executive_summary": "The product faces critical issues with poor performance and negative feedback, despite some strong areas."
        }
        
        result = check_sentiment_alignment(report, narratives)
        assert result["pass"] is True
    
    def test_misaligned_sentiment(self):
        report = {
            "meta": {
                "sentiment_distribution": {
                    "Positive": 80,
                    "Neutral": 10,
                    "Negative": 10
                }
            }
        }
        narratives = {
            "executive_summary": "The product has terrible problems and critical failures everywhere."
        }
        
        result = check_sentiment_alignment(report, narratives)
        assert result["pass"] is False


class TestTopThemeConsistency:
    def test_themes_mentioned(self):
        report = {
            "meta": {
                "top_themes": ["Performance", "UX/UI", "Pricing"]
            }
        }
        narratives = {
            "executive_summary": "Users report performance issues and confusing ux/ui design.",
            "hypothesis": "The pricing model may need adjustment."
        }
        
        result = check_top_theme_consistency(report, narratives)
        assert result["pass"] is True
    
    def test_themes_not_mentioned(self):
        report = {
            "meta": {
                "top_themes": ["Performance", "UX/UI", "Pricing"]
            }
        }
        narratives = {
            "executive_summary": "The product is doing well overall.",
            "hypothesis": "No major issues detected."
        }
        
        result = check_top_theme_consistency(report, narratives)
        assert result["pass"] is False


class TestScorePlausibility:
    def test_valid_scores(self):
        report = {
            "roadmap_items": [
                {"priority_score": 0.85, "category": "Performance"},
                {"priority_score": 0.72, "category": "UX/UI"},
                {"priority_score": 0.45, "category": "Pricing"}
            ]
        }
        
        result = check_score_plausibility(report, {})
        assert result["pass"] is True
    
    def test_out_of_range_scores(self):
        report = {
            "roadmap_items": [
                {"priority_score": 1.5, "category": "Performance"},
                {"priority_score": 0.72, "category": "UX/UI"}
            ]
        }
        
        result = check_score_plausibility(report, {})
        assert result["pass"] is False
    
    def test_unsorted_scores(self):
        report = {
            "roadmap_items": [
                {"priority_score": 0.45, "category": "Pricing"},
                {"priority_score": 0.85, "category": "Performance"},
                {"priority_score": 0.72, "category": "UX/UI"}
            ]
        }
        
        result = check_score_plausibility(report, {})
        assert result["pass"] is False


class TestSynthesisEngine:
    def test_full_validation(self):
        engine = SynthesisEngine()
        
        report = {
            "meta": {
                "sentiment_distribution": {"Positive": 60, "Neutral": 20, "Negative": 20},
                "top_themes": ["Performance", "UX/UI"]
            },
            "roadmap_items": [
                {"priority_score": 0.85, "category": "Performance", "confidence": "High", "volume": 25},
                {"priority_score": 0.72, "category": "UX/UI", "confidence": "Medium", "volume": 15}
            ],
            "risks": []
        }
        
        narratives = {
            "executive_summary": "The product shows strong positive feedback with good performance.",
            "hypothesis": "UI improvements could enhance user experience.",
            "rca_body": "Performance metrics are solid but UI needs attention."
        }
        
        result = engine.validate(report, narratives)
        
        assert "validation_score" in result
        assert "grade" in result
        assert "checks" in result
        assert 0 <= result["validation_score"] <= 100
        assert result["grade"] in ["A", "B", "C", "D", "F"]
