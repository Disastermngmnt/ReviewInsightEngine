"""
Environment-specific configuration management.
Supports dev, staging, and production environments.
"""
# Standard library and third-party imports for environment management, typing, and validation.
# Integrates with: pydantic for type-safe configuration and python-dotenv for local variable loading.
import os
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field, validator
from dotenv import load_dotenv

# Load key-value pairs from the .env file into the shell environment.
load_dotenv()


# Enumeration of supported execution environments.
# Integrates with: AppConfig to drive specific behavior based on the current stage (e.g., debug level).
class Environment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


# Encapsulates all security-related settings, including limits and allowed types.
# Integrates with: core/file_handler.py to enforce upload restrictions and main.py for rate limiting.
class SecurityConfig(BaseModel):
    """Security-related configuration."""
    api_key_min_length: int = Field(default=20, ge=10)
    max_file_size_mb: int = Field(default=50, ge=1, le=500)
    rate_limit_per_minute: int = Field(default=60, ge=1)
    session_timeout_minutes: int = Field(default=30, ge=5)
    allowed_file_extensions: list[str] = Field(default=[".csv", ".xlsx", ".xls"])
    
    # Normalizes provided extensions to a standard '.ext' format.
    @validator("allowed_file_extensions")
    def validate_extensions(cls, v):
        return [ext.lower() if ext.startswith(".") else f".{ext.lower()}" for ext in v]


# Manages the database connection string and pooling parameters.
# Integrates with: core/database.py to initialize the SQLAlchemy engine.
class DatabaseConfig(BaseModel):
    """Database configuration."""
    url: str = Field(default="sqlite:///./app.db")
    echo: bool = Field(default=False)
    pool_size: int = Field(default=5, ge=1)
    max_overflow: int = Field(default=10, ge=0)
    pool_timeout: int = Field(default=30, ge=1)
    
    # Ensures a valid connection URL is always present.
    @validator("url")
    def validate_url(cls, v):
        if not v:
            raise ValueError("Database URL cannot be empty")
        return v


# Configuration for the Google Gemini AI Model and API interaction.
# Integrates with: core/ai_engine.py to authorize and parameters content generation.
class AIConfig(BaseModel):
    """AI/LLM configuration."""
    api_key: str = Field(default="")
    model_name: str = Field(default="gemini-2.5-flash")
    max_tokens: int = Field(default=8192, ge=100)
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    timeout_seconds: int = Field(default=30, ge=5)
    max_retries: int = Field(default=3, ge=0)
    
    # Critical validator: Stops the engine if no API key is set in the environment.
    @validator("api_key")
    def validate_api_key(cls, v):
        if not v:
            raise ValueError("AI API key is required. Set GOOGLE_API_KEY in .env")
        if len(v) < 20:
            raise ValueError("AI API key appears invalid (too short)")
        return v


# Configuration for the deterministic analysis engine, including weights and thresholds.
# Integrates with: core/analyzer.py for scoring, recency, and confidence calculations.
class AnalysisConfig(BaseModel):
    """Analysis engine configuration."""
    min_reviews_warning_threshold: int = Field(default=10, ge=1)
    max_review_text_length: int = Field(default=25000, ge=1000)
    priority_weight_volume: float = Field(default=0.4, ge=0.0, le=1.0)
    priority_weight_sentiment: float = Field(default=0.35, ge=0.0, le=1.0)
    priority_weight_recency: float = Field(default=0.25, ge=0.0, le=1.0)
    confidence_high_threshold: int = Field(default=20, ge=1)
    confidence_medium_threshold: int = Field(default=10, ge=1)
    
    # Ensures that the sum of the three engine weights is exactly 1.0.
    @validator("priority_weight_recency")
    def validate_weights_sum(cls, v, values):
        total = values.get("priority_weight_volume", 0) + values.get("priority_weight_sentiment", 0) + v
        if not (0.99 <= total <= 1.01):  # Allow small floating point error
            raise ValueError(f"Priority weights must sum to 1.0, got {total}")
        return v


# Root configuration object that bundles all sub-configs (Security, DB, AI, Analysis).
# Integrates with: Entire application through the globally shared 'config' instance.
class AppConfig(BaseModel):
    """Main application configuration."""
    environment: Environment = Field(default=Environment.DEVELOPMENT)
    debug: bool = Field(default=False)
    log_level: str = Field(default="INFO")
    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000, ge=1, le=65535)
    
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    ai: AIConfig = Field(default_factory=AIConfig)
    analysis: AnalysisConfig = Field(default_factory=AnalysisConfig)
    
    class Config:
        # Configures Pydantic to treat enums as their raw string values.
        use_enum_values = True


# Logic to construct the AppConfig model by pulling values from environment variables.
# Integrates with: os.getenv and the AppConfig model definition above.
def load_config() -> AppConfig:
    """Load configuration based on environment."""
    # Read the environment variable, defaulting to development if not set.
    env = os.getenv("ENVIRONMENT", "development").lower()
    
    # Map OS environment variables into the structured dictionary format Pydantic expects.
    config_dict = {
        "environment": env,
        "debug": os.getenv("DEBUG", "false").lower() == "true",
        "log_level": os.getenv("LOG_LEVEL", "INFO").upper(),
        "host": os.getenv("HOST", "0.0.0.0"),
        "port": int(os.getenv("PORT", "8000")),
        "security": {
            "max_file_size_mb": int(os.getenv("MAX_FILE_SIZE_MB", "50")),
            "rate_limit_per_minute": int(os.getenv("RATE_LIMIT_PER_MINUTE", "60")),
            "session_timeout_minutes": int(os.getenv("SESSION_TIMEOUT_MINUTES", "30")),
        },
        "database": {
            "url": os.getenv("DATABASE_URL", "sqlite:///./app.db"),
            "echo": os.getenv("DB_ECHO", "false").lower() == "true",
        },
        "ai": {
            "api_key": os.getenv("GOOGLE_API_KEY", ""),
            "model_name": os.getenv("AI_MODEL_NAME", "gemini-2.5-flash"),
            "max_tokens": int(os.getenv("AI_MAX_TOKENS", "8192")),
            "temperature": float(os.getenv("AI_TEMPERATURE", "0.7")),
            "timeout_seconds": int(os.getenv("AI_TIMEOUT_SECONDS", "30")),
        },
        "analysis": {
            "min_reviews_warning_threshold": int(os.getenv("MIN_REVIEWS_THRESHOLD", "10")),
            "max_review_text_length": int(os.getenv("MAX_REVIEW_TEXT_LENGTH", "25000")),
        }
    }
    
    return AppConfig(**config_dict)


# Singleton instance of the application configuration.
# Integrates with: All components using 'from config.environments import config'.
config = load_config()
