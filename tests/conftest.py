"""
Pytest configuration and shared fixtures.
"""
import pytest
import os
import tempfile
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from core.database import Base
from core.models import Order, UsageStats


@pytest.fixture(scope="session")
def test_env():
    """Set test environment variables."""
    os.environ["ENVIRONMENT"] = "development"
    os.environ["GOOGLE_API_KEY"] = "test_key_1234567890123456789012345"
    os.environ["DEBUG"] = "true"
    yield
    

@pytest.fixture
def temp_db():
    """Create temporary test database."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    
    yield SessionLocal
    
    # Cleanup
    Base.metadata.drop_all(bind=engine)
    engine.dispose()
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def sample_reviews():
    """Sample review data for testing."""
    return [
        {"text": "This product is amazing! Love it.", "rating": 5, "date": "2024-01-15"},
        {"text": "Terrible experience. Very slow and buggy.", "rating": 1, "date": "2024-01-20"},
        {"text": "It's okay, nothing special.", "rating": 3, "date": "2024-01-25"},
        {"text": "Great performance and fast loading times!", "rating": 5, "date": "2024-02-01"},
        {"text": "The UI is confusing and hard to navigate.", "rating": 2, "date": "2024-02-05"},
        {"text": "Customer support was very helpful.", "rating": 5, "date": "2024-02-10"},
        {"text": "Too expensive for what it offers.", "rating": 2, "date": "2024-02-12"},
        {"text": "Missing key features I need.", "rating": 2, "date": "2024-02-15"},
        {"text": "Crashes frequently, very unreliable.", "rating": 1, "date": "2024-02-18"},
        {"text": "Easy to use and intuitive interface.", "rating": 4, "date": "2024-02-20"},
    ]


@pytest.fixture
def sample_csv_content():
    """Sample CSV content as bytes."""
    csv_data = """review_text,rating,date
"Great product, highly recommend!",5,2024-01-15
"Slow and buggy",1,2024-01-20
"Average experience",3,2024-01-25
"Fast performance",5,2024-02-01
"Confusing UI",2,2024-02-05
"""
    return csv_data.encode('utf-8')


@pytest.fixture
def mock_taxonomy():
    """Simplified taxonomy for testing."""
    return {
        "Performance": ["slow", "fast", "speed", "lag"],
        "UX/UI": ["ui", "ux", "interface", "confusing"],
        "Pricing": ["price", "expensive", "cheap", "cost"],
        "Other": []
    }
