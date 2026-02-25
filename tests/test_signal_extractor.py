"""
Tests for the signal extraction engine.
"""
import pytest
from core.signal_extractor import (
    extract_signals,
    aggregate_theme_signals,
    _polarity_from_rating,
    _polarity_from_sentiment,
    _has_concrete_feature,
    _match_keyword_count,
)


class TestPolarityFromRating:
    def test_5_scale_extremes(self):
        assert _polarity_from_rating(1, 5) == -1.0
        assert _polarity_from_rating(5, 5) == 1.0
    
    def test_5_scale_mid(self):
        assert _polarity_from_rating(3, 5) == 0.0
    
    def test_10_scale_extremes(self):
        assert _polarity_from_rating(1, 10) == -1.0
        assert _polarity_from_rating(10, 10) == 1.0
    
    def test_10_scale_mid(self):
        result = _polarity_from_rating(5.5, 10)
        assert abs(result) < 0.01  # near zero

    def test_none_rating(self):
        assert _polarity_from_rating(None, 5) == 0.0


class TestPolarityFromSentiment:
    def test_positive(self):
        assert _polarity_from_sentiment("Positive") == 0.7
    
    def test_negative(self):
        assert _polarity_from_sentiment("Negative") == -0.7
    
    def test_neutral(self):
        assert _polarity_from_sentiment("Neutral") == 0.0


class TestFeatureDetection:
    def test_concrete_feature(self):
        assert _has_concrete_feature("we need api integration") is True
        assert _has_concrete_feature("please add slack integration") is True
    
    def test_vague_complaint(self):
        assert _has_concrete_feature("this is terrible") is False
        assert _has_concrete_feature("i hate this product") is False


class TestKeywordMatching:
    def test_urgency_detection(self):
        from config.settings import URGENCY_KEYWORDS
        count, matched = _match_keyword_count("this is broken and unusable", URGENCY_KEYWORDS)
        assert count >= 2
        assert "broken" in matched
        assert "unusable" in matched
    
    def test_churn_detection(self):
        from config.settings import CHURN_KEYWORDS
        count, matched = _match_keyword_count("i'm cancelling my subscription", CHURN_KEYWORDS)
        assert count >= 1
        assert "cancelling" in matched
    
    def test_expansion_detection(self):
        from config.settings import EXPANSION_KEYWORDS
        count, matched = _match_keyword_count("i wish it could export to pdf", EXPANSION_KEYWORDS)
        assert count >= 1
    
    def test_no_matches(self):
        count, matched = _match_keyword_count("everything is fine", [])
        assert count == 0
        assert matched == []


class TestExtractSignals:
    @pytest.fixture
    def sample_parsed(self):
        return [
            {"text": "App is broken and unusable, cancelling subscription", "rating": 1, "sentiment": "Negative", "category": "Reliability", "date": None, "recency_weight": 0.5},
            {"text": "I wish it could export to PDF", "rating": 3, "sentiment": "Neutral", "category": "Feature Gaps", "date": None, "recency_weight": 0.5},
            {"text": "Great product, love the dashboard", "rating": 5, "sentiment": "Positive", "category": "UX/UI", "date": None, "recency_weight": 0.5},
            {"text": "Switching to competitor, too slow", "rating": 1, "sentiment": "Negative", "category": "Performance", "date": None, "recency_weight": 0.5},
        ]
    
    def test_enrichment_adds_fields(self, sample_parsed):
        result = extract_signals(sample_parsed)
        for r in result:
            assert "polarity_score" in r
            assert "urgency_flags" in r
            assert "urgency_score" in r
            assert "churn_signal" in r
            assert "expansion_signal" in r
            assert "feature_specificity" in r
            assert "segment_weight" in r
    
    def test_churn_signal_detected(self, sample_parsed):
        result = extract_signals(sample_parsed)
        # First review has "cancelling" — should be churn
        assert result[0]["churn_signal"] is True
        # Fourth review has "switching to" — should be churn
        assert result[3]["churn_signal"] is True
        # Third review (positive) — should not be churn
        assert result[2]["churn_signal"] is False
    
    def test_expansion_signal_detected(self, sample_parsed):
        result = extract_signals(sample_parsed)
        # Second review has "wish it could" — should be expansion
        assert result[1]["expansion_signal"] is True
    
    def test_polarity_from_rating(self, sample_parsed):
        result = extract_signals(sample_parsed, rating_scale=5)
        assert result[0]["polarity_score"] == -1.0   # rating 1
        assert result[2]["polarity_score"] == 1.0     # rating 5
    
    def test_feature_specificity(self, sample_parsed):
        result = extract_signals(sample_parsed)
        # "dashboard" is a concrete feature
        assert result[2]["feature_specificity"] == "concrete"
        # "broken and unusable" is vague
        assert result[0]["feature_specificity"] == "vague"


class TestAggregateThemeSignals:
    def test_aggregation(self):
        reviews = [
            {"text": "broken", "category": "Reliability", "polarity_score": -1.0,
             "urgency_score": 0.5, "churn_signal": True, "expansion_signal": False,
             "feature_specificity": "vague", "segment_weight": 1.0, "sentiment": "Negative"},
            {"text": "great dashboard", "category": "UX/UI", "polarity_score": 1.0,
             "urgency_score": 0.0, "churn_signal": False, "expansion_signal": False,
             "feature_specificity": "concrete", "segment_weight": 1.0, "sentiment": "Positive"},
            {"text": "also broken", "category": "Reliability", "polarity_score": -0.7,
             "urgency_score": 0.3, "churn_signal": False, "expansion_signal": False,
             "feature_specificity": "vague", "segment_weight": 1.0, "sentiment": "Negative"},
        ]
        result = aggregate_theme_signals(reviews, total_reviews=3)

        assert "Reliability" in result
        assert "UX/UI" in result
        assert result["Reliability"]["volume"] == 2
        assert result["Reliability"]["churn_signal_count"] == 1
        assert result["UX/UI"]["volume"] == 1
        assert result["UX/UI"]["positive_count"] == 1
