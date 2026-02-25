# ReviewInsightEngine 🚀

Transform customer reviews into actionable product roadmaps using AI-powered analysis.

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests](https://img.shields.io/badge/tests-70%2B%20passing-brightgreen.svg)](tests/)

## Overview

ReviewInsightEngine is an intelligent review analysis platform that combines deterministic data science with AI narrative generation to help product teams understand customer feedback and prioritize their roadmap.

### Key Features

- **📊 Deterministic Analysis** - Reproducible, transparent classification and scoring
- **🤖 AI Narratives** - Executive summaries and insights powered by Google Gemini
- **✅ Validation Engine** - Cross-checks AI outputs against computed statistics
- **📈 Priority Scoring** - Data-driven roadmap prioritization
- **🎯 Sentiment Analysis** - Multi-source sentiment detection (ratings + keywords)
- **📅 Temporal Analysis** - Recency-weighted insights
- **🔒 Enterprise Security** - Rate limiting, input validation, audit logging

## Quick Start

### Prerequisites

- Python 3.9 or higher
- Google AI API key ([Get one here](https://makersuite.google.com/app/apikey))

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/ReviewInsightEngine.git
cd ReviewInsightEngine

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and add your GOOGLE_API_KEY
```

### Configuration

Create a `.env` file with your settings:

```bash
# Required
GOOGLE_API_KEY=your_api_key_here

# Optional (defaults shown)
ENVIRONMENT=development
LOG_LEVEL=INFO
MAX_FILE_SIZE_MB=50
RATE_LIMIT_PER_MINUTE=60
```

### Initialize Database

```bash
python scripts/init_db.py
```

### Run the Application

**Option 1: Streamlit UI (Recommended)**
```bash
streamlit run app.py
```
Open http://localhost:8501 in your browser.

**Option 2: FastAPI Backend**
```bash
python main.py
```
Open http://localhost:8000 in your browser.

## Usage

### 1. Authentication
Enter a valid Order ID to access the platform. For testing, use:
- `TEST123`
- `INSIGHTS2026`

### 2. Upload Data
Upload customer review data in CSV or Excel format. The system automatically detects:
- Review text columns
- Rating columns (1-5 or 1-10 scale)
- Date/timestamp columns

### 3. View Results
Get comprehensive insights including:
- **Executive Summary** - High-level overview for stakeholders
- **Priority Roadmap** - Ranked categories with confidence scores
- **Sentiment Analysis** - Distribution and trends over time
- **Verbatim Quotes** - Representative customer feedback
- **Validation Report** - AI output quality assessment

## Architecture

### Hybrid Analysis Approach

```
┌─────────────────┐
│  Upload Data    │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Deterministic   │  ← Python-based classification
│   Analyzer      │    Reproducible, transparent
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  AI Narrative   │  ← Google Gemini
│   Generator     │    Executive summaries only
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Synthesis &    │  ← Cross-validation
│  Validation     │    Detects hallucinations
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  Final Report   │
└─────────────────┘
```

### Project Structure

```
ReviewInsightEngine/
├── core/                   # Business logic
│   ├── analyzer.py         # Deterministic analysis engine
│   ├── ai_engine.py        # AI narrative generation
│   ├── synthesis_engine.py # Validation & cross-checking
│   ├── file_handler.py     # File processing
│   ├── auth.py             # Authentication
│   ├── database.py         # Database connection
│   └── models.py           # Data models
├── config/                 # Configuration
│   ├── settings.py         # Static settings (taxonomy, prompts)
│   └── environments.py     # Environment-based config
├── ui/                     # Streamlit UI components
│   ├── sidebar.py
│   ├── uploader.py
│   └── results.py
├── utils/                  # Utilities
│   ├── logger.py           # Centralized logging
│   ├── exceptions.py       # Custom exceptions
│   ├── validators.py       # Input validation
│   └── rate_limiter.py     # Rate limiting
├── tests/                  # Test suite (70+ tests)
├── app.py                  # Streamlit entry point
├── main.py                 # FastAPI entry point
└── requirements.txt        # Dependencies
```

## Features in Detail

### Deterministic Analysis

All classification and scoring is done in Python with fixed rules:

**Priority Formula:**
```
Priority Score = (Volume × 0.4) + (Sentiment Impact × 0.35) + (Recency × 0.25)
```

**Taxonomy Categories:**
- Performance
- UX/UI
- Onboarding
- Pricing
- Reliability
- Customer Support
- Feature Gaps
- Other

**Confidence Levels:**
- High: 20+ mentions
- Medium: 10-19 mentions
- Low: <10 mentions

### AI Integration

Google Gemini generates narrative prose only:
- Executive summaries
- Hypothesis statements
- Root cause analysis
- Mermaid flowcharts

Classification and scoring remain deterministic for reproducibility.

### Validation Engine

Cross-checks AI outputs against computed statistics:
- Sentiment alignment
- Theme consistency
- Score plausibility
- Risk acknowledgement
- Confidence calibration

Outputs validation score (0-100) and letter grade (A-F).

## Development

### Running Tests

```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Run all tests
pytest

# Run with coverage
pytest --cov=core --cov=utils --cov-report=html

# Run specific test file
pytest tests/test_analyzer.py -v
```

### Code Quality

```bash
# Format code
black core utils config tests

# Sort imports
isort core utils config tests

# Lint
flake8 core utils config tests --max-line-length=120

# Type check
mypy core utils config --ignore-missing-imports
```

### Validation

```bash
# Validate all improvements
python scripts/validate_improvements.py
```

## Security

### Built-in Security Features

- **Rate Limiting** - 60 requests/minute per client (configurable)
- **Input Validation** - File size limits, extension whitelist, format validation
- **Authentication** - Order ID validation with database backing
- **Audit Logging** - All actions logged with rotation
- **Error Handling** - No sensitive data in error messages

### Security Best Practices

- Store API keys in `.env` (never commit)
- Use HTTPS in production
- Configure security headers
- Regular dependency updates
- Review `SECURITY.md` for detailed guidelines

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `GOOGLE_API_KEY` | Google AI API key | Required |
| `ENVIRONMENT` | Environment (development/staging/production) | development |
| `LOG_LEVEL` | Logging level (DEBUG/INFO/WARNING/ERROR) | INFO |
| `HOST` | Server host | 0.0.0.0 |
| `PORT` | Server port | 8000 |
| `MAX_FILE_SIZE_MB` | Maximum upload size | 50 |
| `RATE_LIMIT_PER_MINUTE` | API rate limit | 60 |
| `DATABASE_URL` | Database connection string | sqlite:///./app.db |

See `.env.example` for complete list.

### Customization

**Taxonomy** - Edit `config/settings.py` to customize categories and keywords

**Priority Weights** - Adjust in `.env`:
```bash
PRIORITY_WEIGHT_VOLUME=0.4
PRIORITY_WEIGHT_SENTIMENT=0.35
PRIORITY_WEIGHT_RECENCY=0.25
```

**AI Model** - Change model in `.env`:
```bash
AI_MODEL_NAME=gemini-2.5-flash
AI_TEMPERATURE=0.7
```

## API Documentation

### FastAPI Endpoints

**Authentication**
```
POST /api/auth
Body: order_id (form data)
Returns: {"status": "success"}
```

**Upload File**
```
POST /api/upload
Body: file (multipart/form-data)
Returns: {columns, data, auto_detected_column, ...}
```

**Analyze Reviews**
```
POST /api/analyze
Body: columns (JSON string), data (JSON string)
Returns: {report: {...}}
```

**Get Pricing**
```
GET /api/pricing
Returns: {usages, price}
```

## Troubleshooting

### Common Issues

**"GOOGLE_API_KEY not configured"**
- Ensure `.env` file exists with valid API key
- Restart the application after adding key

**"Rate limit exceeded"**
- Wait 60 seconds or increase `RATE_LIMIT_PER_MINUTE` in `.env`

**"File too large"**
- Increase `MAX_FILE_SIZE_MB` in `.env`
- Or split data into smaller files

**Tests failing**
- Install dev dependencies: `pip install -r requirements-dev.txt`
- Check that environment variables are set

### Logs

Application logs are written to `logs/app.log`:
```bash
# View logs
tail -f logs/app.log

# Search for errors
grep "ERROR" logs/app.log
```

## Performance

### Benchmarks

- **Small datasets** (<100 reviews): ~2-3 seconds
- **Medium datasets** (100-1000 reviews): ~5-10 seconds
- **Large datasets** (1000+ reviews): ~10-15 seconds

### Optimization Tips

- Use CSV instead of Excel for faster parsing
- Limit review text to essential columns
- Enable database connection pooling for high traffic
- Consider caching for repeated analyses

## Contributing

Contributions are welcome! Please follow these guidelines:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Write tests for new functionality
4. Ensure all tests pass (`pytest`)
5. Format code (`black`, `isort`)
6. Commit changes (`git commit -m 'Add amazing feature'`)
7. Push to branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request

### Development Setup

```bash
# Install dev dependencies
pip install -r requirements-dev.txt

# Run tests before committing
pytest

# Format code
make format

# Run linters
make lint
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- **Google Gemini** - AI narrative generation
- **Streamlit** - Interactive UI framework
- **FastAPI** - High-performance API framework
- **SQLAlchemy** - Database ORM
- **Pandas** - Data processing

## Support

- **Documentation**: See `docs/` directory
- **Issues**: [GitHub Issues](https://github.com/yourusername/ReviewInsightEngine/issues)
- **Security**: See `SECURITY.md` for reporting vulnerabilities

## Roadmap

### Current Version (1.0)
- ✅ Deterministic analysis engine
- ✅ AI narrative generation
- ✅ Validation engine
- ✅ Streamlit UI
- ✅ FastAPI backend
- ✅ Comprehensive testing
- ✅ Security features

### Planned Features
- [ ] Multi-language support
- [ ] Custom taxonomy builder
- [ ] Competitor comparison
- [ ] Historical trend analysis
- [ ] Export to Jira/Linear
- [ ] Slack/Teams integration
- [ ] Real-time collaboration
- [ ] Advanced visualizations

## Citation

If you use ReviewInsightEngine in your research or product, please cite:

```bibtex
@software{reviewinsightengine2024,
  title = {ReviewInsightEngine: AI-Powered Review Analysis},
  author = {Your Name},
  year = {2024},
  url = {https://github.com/yourusername/ReviewInsightEngine}
}
```

---

**Made with ❤️ for product teams who want to understand their customers better.**

For detailed documentation, see:
- [Quick Start Guide](docs/QUICKSTART.md)
- [Security Guidelines](docs/SECURITY.md)
- [Deployment Checklist](docs/DEPLOYMENT_CHECKLIST.md)
- [Improvements Summary](docs/IMPROVEMENTS_SUMMARY.md)
