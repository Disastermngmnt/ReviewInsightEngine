# Quick Start Guide

## Prerequisites
- Python 3.9 or higher
- Google AI API key (Gemini)

## Installation

### 1. Clone or Download the Repository
```bash
cd ReviewInsightEngine
```

### 2. Create Virtual Environment
```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux/Mac
source .venv/bin/activate
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Configure Environment
```bash
# Copy example environment file
cp .env.example .env

# Edit .env and add your Google API key
# Required: GOOGLE_API_KEY=your_actual_api_key_here
```

### 5. Initialize Database
```bash
python init_db.py
```

## Running the Application

### 1. Start the FastAPI Backend
```bash
python main.py
```
Wait for the logger to indicate the server is running.

### 2. Open the Application
Navigate to http://localhost:8000 in your web browser. The system serves the Dispatch UI from the `static/` directory.

## Running Tests

### Install Development Dependencies
```bash
pip install -r requirements-dev.txt
```

### Run All Tests
```bash
pytest
```

### Run with Coverage Report
```bash
pytest --cov=core --cov=utils --cov-report=html
```

### Run Specific Test File
```bash
pytest tests/test_analyzer.py -v
```

## Configuration

### Environment Variables
Edit `.env` file to customize:

```bash
# Application
ENVIRONMENT=development  # or staging, production
DEBUG=true
LOG_LEVEL=INFO

# Server
HOST=0.0.0.0
PORT=8000

# AI Configuration
GOOGLE_API_KEY=your_key_here
AI_MODEL_NAME=gemini-2.5-flash
AI_TEMPERATURE=0.7

# Security
MAX_FILE_SIZE_MB=50
RATE_LIMIT_PER_MINUTE=60

# Analysis
MIN_REVIEWS_THRESHOLD=10
```

## Usage

### 1. Authentication
- Enter a valid Order ID in the main interface.
- Default test IDs: `ORD-123`, `ORD-456`, `INSIGHTS2026`, `TEST123`

### 2. Upload Data
- Supported formats: CSV, XLSX, XLS
- Must contain review text column
- Optional: rating and date columns

### 3. View Results
- Executive summary
- Priority roadmap
- Sentiment analysis
- Validation report

## Troubleshooting

### "GOOGLE_API_KEY not configured"
- Make sure you've created `.env` file from `.env.example`
- Add your actual Google AI API key
- Restart the application

### "Rate limit exceeded"
- Wait 60 seconds and try again
- Or increase `RATE_LIMIT_PER_MINUTE` in `.env`

### "File too large"
- Increase `MAX_FILE_SIZE_MB` in `.env`
- Or split your data into smaller files

### Tests Failing
- Make sure you've installed dev dependencies: `pip install -r requirements-dev.txt`
- Check that `GOOGLE_API_KEY` is set in environment (tests use a mock key)

## Project Structure

```
ReviewInsightEngine/
├── core/               # Business logic
│   ├── analyzer.py     # Deterministic analysis
│   ├── ai_engine.py    # AI narrative generation
│   ├── auth.py         # Authentication
│   ├── database.py     # Database connection
│   ├── file_handler.py # File processing
│   ├── models.py       # Database models
│   └── synthesis_engine.py  # Validation
├── config/             # Configuration
│   ├── environments.py # Environment-based config
│   └── settings.py     # Static settings
├── utils/              # Utilities
│   ├── exceptions.py   # Custom exceptions
│   ├── logger.py       # Logging setup
│   ├── rate_limiter.py # Rate limiting
│   └── validators.py   # Input validation
├── tests/              # Test suite
├── static/             # Frontend assets (served by FastAPI)
├── main.py             # FastAPI entry point
└── requirements.txt    # Dependencies
```

## Next Steps

1. Review `README_IMPROVEMENTS.md` for detailed improvements
2. Check logs in `logs/app.log` for debugging
3. Run tests to ensure everything works
4. Customize configuration in `.env`
5. Add your own order IDs to the database

## Support

For issues or questions:
1. Check logs: `logs/app.log`
2. Review error messages in the UI
3. Run tests to identify issues
4. Check configuration in `.env`
