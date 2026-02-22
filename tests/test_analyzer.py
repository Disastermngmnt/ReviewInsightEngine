"""
Tests for the deterministic analyzer engine.
"""
import pytest
from datetime import datetime, timezone
from core.analyzer import (
    Analyzer,
    _normalise,
    _classify_review,
    _derive_sentiment_from_text,
    _derive_sentiment_from_rating,
    _recency_weight,
    _sentiment_impact,
    _confidence_label,
    _timeline_bucket
)


class TestHelperFunctions:
    def test_normalise(self):
        assert _normalise("  Hello World  ") == "hello world"
        assert _normalise("UPPERCASE") == "uppercase"
    
    def test_classify_review_performance(self):
        text = "The app is very slow and laggy"
        result = _classify_review(text)
        assert result == "Performance"
    
    def test_classify_review_ux(self):
        text = "The UI is confusing and hard to navigate"
        result = _classify_review(text)
        assert result == "UX/UI"
    
    def test_classify_review_other(self):
        text = "Random text with no keywords"
        result = _classify_review(text)
        assert result == "Other"
    
    def test_sentiment_from_text_positive(self):
        assert _derive_sentiment_from_text("I love this product!") == "Positive"
        assert _derive_sentiment_from_text("Great experience") == "Positive"
    
    def test_sentiment_from_text_negative(self):
        assert _derive_sentiment_from_text("Terrible and awful") == "Negative"
        assert _derive_sentiment_from_text("Worst product ever") == "Negative"
    
    def test_sentiment_from_text_neutral(self):
        assert _derive_sentiment_from_text("It exists") == "Neutral"
    
    def test_sentiment_from_rating_5_scale(self):
        assert _derive_sentiment_from_rating(5, 5) == "Positive"
        assert _derive_sentiment_from_rating(4, 5) == "Positive"
        assert _derive_sentiment_from_rating(3, 5) == "Neutral"
        assert _derive_sentiment_from_rating(2, 5) == "Negative"
        assert _derive_sentiment_from_rating(1, 5) == "Negative"
    
    def test_sentiment_from_rating_10_scale(self):
        assert _derive_sentiment_from_rating(10, 10) == "Positive"
        assert _derive_sentiment_from_rating(7, 10) == "Positive"
        assert _derive_sentiment_from_rating(6, 10) == "Neutral"
        assert _derive_sentiment_from_rating(5, 10) == "Neutral"
        assert _derive_sentiment_from_rating(4, 10) == "Negative"
    
    def test_recency_weight(self):
        now = datetime.now(tz=timezone.utc)
        
        # Last 30 days
        from datetime import timedelta
        recent = now - timedelta(days=15)
        assert _recency_weight(recent, now) == 1.0
        
        # Last 90 days
        mid = now - timedelta(days=60)
        assert _recency_weight(mid, now) == 0.75
        
        # Older
        old = now - timedelta(days=120)
        assert _recency_weight(old, now) == 0.5
        
        # No date
        assert _recency_weight(None, now) == 0.5
    
    def test_sentiment_impact(self):
        assert _sentiment_impact("Positive") == 1.0
        assert _sentiment_impact("Neutral") == 0.5
        assert _sentiment_impact("Negative") == 0.0
    
    def test_confidence_label(self):
        assert _confidence_label(25) == "High"
        assert _confidence_label(15) == "Medium"
        assert _confidence_label(5) == "Low"
    
    def test_timeline_bucket(self):
        assert _timeline_bucket(0.80) == "Q1 – Immediate"
        assert _timeline_bucket(0.60) == "Q2 – Near-term"
        assert _timeline_bucket(0.40) == "Q3 – Mid-term"
        assert _timeline_bucket(0.20) == "Q4 / Backlog"


class TestAnalyzer:
    def test_basic_analysis(self, sample_reviews):
        analyzer = Analyzer()
        
        columns = ["review_text", "rating", "date"]
        data = [[r["text"], r["rating"], r["date"]] for r in sample_reviews]
        
        result = analyzer.run(columns, data)
        
        assert "meta" in result
        assert "roadmap_items" in result
        assert result["meta"]["total_reviews"] == len(sample_reviews)
        assert len(result["roadmap_items"]) > 0
    
    def test_empty_data_error(self):
        analyzer = Analyzer()
        result = analyzer.run(["col1"], [])
        assert "error" in result
    
    def test_priority_score_range(self, sample_reviews):
        analyzer = Analyzer()
        
        columns = ["review_text", "rating", "date"]
        data = [[r["text"], r["rating"], r["date"]] for r in sample_reviews]
        
        result = analyzer.run(columns, data)
        
        for item in result["roadmap_items"]:
            assert 0.0 <= item["priority_score"] <= 1.0
    
    def test_roadmap_items_sorted(self, sample_reviews):
        analyzer = Analyzer()
        
        columns = ["review_text", "rating", "date"]
        data = [[r["text"], r["rating"], r["date"]] for r in sample_reviews]
        
        result = analyzer.run(columns, data)
        
        scores = [item["priority_score"] for item in result["roadmap_items"]]
        assert scores == sorted(scores, reverse=True)
    
    def test_sentiment_distribution_sums_to_100(self, sample_reviews):
        analyzer = Analyzer()
        
        columns = ["review_text", "rating", "date"]
        data = [[r["text"], r["rating"], r["date"]] for r in sample_reviews]
        
        result = analyzer.run(columns, data)
        
        dist = result["meta"]["sentiment_distribution"]
        total = dist["Positive"] + dist["Neutral"] + dist["Negative"]
        assert 99.9 <= total <= 100.1  # Allow floating point error
    
    def test_no_rating_column_fallback(self):
        analyzer = Analyzer()
        
        columns = ["review_text"]
        data = [
            ["I love this product!"],
            ["Terrible experience"],
            ["It's okay"]
        ]
        
        result = analyzer.run(columns, data)
        
        assert result["meta"]["has_rating_col"] is False
        assert result["meta"]["sentiment_source"] == "keyword"
    
    def test_verbatim_quotes_included(self, sample_reviews):
        analyzer = Analyzer()
        
        columns = ["review_text", "rating", "date"]
        data = [[r["text"], r["rating"], r["date"]] for r in sample_reviews]
        
        result = analyzer.run(columns, data)
        
        assert "verbatim_quotes" in result
        assert len(result["verbatim_quotes"]) <= 3
        
        for category_quotes in result["verbatim_quotes"]:
            assert "category" in category_quotes
            assert "quotes" in category_quotes
            assert len(category_quotes["quotes"]) <= 3
