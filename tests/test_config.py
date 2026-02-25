"""
Tests for configuration management.
"""
import pytest
import os
from config.environments import (
    AppConfig,
    SecurityConfig,
    DatabaseConfig,
    AIConfig,
    AnalysisConfig,
    load_config
)
from pydantic import ValidationError


class TestSecurityConfig:
    def test_default_values(self):
        config = SecurityConfig()
        assert config.max_file_size_mb == 50
        assert config.rate_limit_per_minute == 60
        assert ".csv" in config.allowed_file_extensions
    
    def test_custom_values(self):
        config = SecurityConfig(
            max_file_size_mb=100,
            rate_limit_per_minute=120
        )
        assert config.max_file_size_mb == 100
        assert config.rate_limit_per_minute == 120
    
    def test_extension_normalization(self):
        config = SecurityConfig(allowed_file_extensions=["csv", ".xlsx", "XLS"])
        assert ".csv" in config.allowed_file_extensions
        assert ".xlsx" in config.allowed_file_extensions
        assert ".xls" in config.allowed_file_extensions


class TestDatabaseConfig:
    def test_default_values(self):
        config = DatabaseConfig()
        assert config.url == "sqlite:///./data/app.db"
        assert config.pool_size == 5
    
    def test_empty_url_validation(self):
        with pytest.raises(ValidationError):
            DatabaseConfig(url="")


class TestAIConfig:
    def test_valid_config(self):
        config = AIConfig(api_key="test_key_1234567890123456789012345")
        assert config.model_name == "gemini-2.5-flash"
        assert config.temperature == 0.7
    
    def test_empty_api_key_validation(self):
        with pytest.raises(ValidationError) as exc:
            AIConfig(api_key="")
        assert "required" in str(exc.value).lower()
    
    def test_short_api_key_validation(self):
        with pytest.raises(ValidationError) as exc:
            AIConfig(api_key="short")
        assert "too short" in str(exc.value).lower()
    
    def test_temperature_range(self):
        config = AIConfig(api_key="test_key_1234567890123456789012345", temperature=1.5)
        assert config.temperature == 1.5
        
        with pytest.raises(ValidationError):
            AIConfig(api_key="test_key_1234567890123456789012345", temperature=3.0)


class TestAnalysisConfig:
    def test_default_values(self):
        config = AnalysisConfig()
        assert config.min_reviews_warning_threshold == 10
        assert config.priority_weight_volume == 0.4
        assert config.priority_weight_sentiment == 0.35
        assert config.priority_weight_recency == 0.25
    
    def test_weights_sum_validation(self):
        # Valid: sums to 1.0
        config = AnalysisConfig(
            priority_weight_volume=0.5,
            priority_weight_sentiment=0.3,
            priority_weight_recency=0.2
        )
        assert config.priority_weight_volume == 0.5
        
        # Invalid: doesn't sum to 1.0
        with pytest.raises(ValidationError) as exc:
            AnalysisConfig(
                priority_weight_volume=0.5,
                priority_weight_sentiment=0.5,
                priority_weight_recency=0.5
            )
        assert "sum to 1.0" in str(exc.value)


class TestAppConfig:
    def test_default_config(self, test_env):
        config = AppConfig(
            ai=AIConfig(api_key="test_key_1234567890123456789012345")
        )
        assert config.environment == "development"
        assert config.port == 8000
    
    def test_load_config_from_env(self, test_env):
        os.environ["PORT"] = "9000"
        os.environ["LOG_LEVEL"] = "DEBUG"
        
        config = load_config()
        
        assert config.port == 9000
        assert config.log_level == "DEBUG"
