# Standard and third-party imports for the FastAPI framework, database ORM, and utility functions.
# Integrates with: core/ modules for logic, utils/ for helpers, and config/ for settings.
from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Depends, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
import uvicorn
import math
import json
import os

from core.auth import AuthManager
from core.file_handler import FileHandler
from core.analyzer import Analyzer
from core.ai_engine import AIEngine
from core.synthesis_engine import SynthesisEngine
from core.database import Base, engine, SessionLocal, get_db
from core.models import UsageStats
from utils.logger import setup_logger
from utils.exceptions import (
    ReviewInsightError,
    ValidationError,
    AuthenticationError,
    RateLimitError
)
from utils.rate_limiter import RateLimiter
from config.environments import config

# ── APP INITIALIZATION ────────────────────────────────────────────────────────
# Integrates with: config/environments.py for log levels and security parameters.
logger = setup_logger(__name__, level=config.log_level, log_file="logs/app.log")

app = FastAPI(title="ReviewInsightEngine", version="1.0.0")

# 1. Database Setup: Ensure tables exist upon server start.
Base.metadata.create_all(bind=engine)

# 2. Static Asset Hosting: Serve CSS, JS, and Images from the local directory.
app.mount("/static", StaticFiles(directory="static"), name="static")

# 3. Global Rate Limiting: Prevent API flooding using the sliding window utility.
rate_limiter = RateLimiter(
    max_requests=config.security.rate_limit_per_minute,
    window_seconds=60
)


# ── EXCEPTION HANDLERS ───────────────────────────────────────────────────────
# Custom middleware for converting internal application errors into structured HTTP responses.

@app.exception_handler(ReviewInsightError)
async def review_insight_error_handler(request: Request, exc: ReviewInsightError):
    """Handle custom application errors."""
    logger.error(f"Application error: {exc.message}", extra={"details": exc.details})
    return JSONResponse(
        status_code=400,
        content={"error": exc.message, "details": exc.details}
    )


@app.exception_handler(RateLimitError)
async def rate_limit_error_handler(request: Request, exc: RateLimitError):
    """Handle rate limit errors."""
    logger.warning(f"Rate limit exceeded: {request.client.host}")
    return JSONResponse(
        status_code=429,
        content={
            "error": exc.message,
            "retry_after": exc.details.get("retry_after", 60)
        },
        headers={"Retry-After": str(exc.details.get("retry_after", 60))}
    )


def get_client_id(request: Request) -> str:
    """Extract client identifier (IP) for rate limiting checks."""
    return request.client.host if request.client else "unknown"


# ── FRONTEND ROUTE ───────────────────────────────────────────────────────────
# Serves the Single Page Application (SPA).
@app.get("/", response_class=HTMLResponse)
async def read_root():
    """Serve the main HTML page."""
    try:
        with open("static/index.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        logger.error("index.html not found")
        raise HTTPException(status_code=404, detail="Page not found")


# ── AUTHENTICATION ENDPOINT ──────────────────────────────────────────────────
# Processes Order ID login requests.
# Integrates with: core/auth.py for verification and utils/rate_limiter.py for security.
@app.post("/api/auth")
async def verify_auth(request: Request, order_id: str = Form(...)):
    """
    Verify order ID authentication.
    
    Args:
        order_id: Order ID to validate
        
    Returns:
        Success status
        
    Raises:
        HTTPException: If authentication fails
    """
    client_id = get_client_id(request)
    
    # 1. Protection: Apply per-client rate limit for auth attempts.
    try:
        rate_limiter.check_rate_limit(f"auth:{client_id}")
    except RateLimitError as e:
        raise HTTPException(
            status_code=429,
            detail=e.message,
            headers={"Retry-After": str(e.details.get("retry_after", 60))}
        )
    
    logger.info(f"Auth attempt from {client_id}")
    
    # 2. Logic: Delegate validation to the AuthManager.
    if AuthManager.is_valid_order(order_id):
        logger.info(f"Auth successful for {client_id}")
        return {"status": "success"}
    
    logger.warning(f"Auth failed for {client_id}")
    raise HTTPException(status_code=401, detail="Invalid Order ID")


# ── FILE UPLOAD ENDPOINT ─────────────────────────────────────────────────────
# Ingests raw binary files and returns a structured preview.
# Integrates with: core/file_handler.py for binary parsing and column detection.
@app.post("/api/upload")
async def upload_file(request: Request, file: UploadFile = File(...)):
    """
    Upload and process a review file.
    
    Args:
        file: Uploaded file (CSV or Excel)
        
    Returns:
        Processed file data with columns and rows
        
    Raises:
        HTTPException: If processing fails
    """
    client_id = get_client_id(request)
    
    # Rate limiting to prevent server overload from large/repeated uploads.
    try:
        rate_limiter.check_rate_limit(f"upload:{client_id}")
    except RateLimitError as e:
        raise HTTPException(
            status_code=429,
            detail=e.message,
            headers={"Retry-After": str(e.details.get("retry_after", 60))}
        )
    
    logger.info(f"File upload from {client_id}: {file.filename}")
    
    try:
        # 1. Extraction: Read the raw upload stream.
        contents = await file.read()
        # 2. Parsing: Hand off to FileHandler which uses pandas.
        handler = FileHandler()
        result = handler.process_file(contents, file.filename)
        
        # Check for handler-level errors (e.g., unsupported format).
        if "error" in result:
            logger.warning(f"File processing error: {result['error']}")
            raise HTTPException(status_code=400, detail=result["error"])
        
        logger.info(f"File processed successfully: {file.filename}")
        return result
        
    except HTTPException:
        # Rethrow known HTTP exceptions.
        raise
    except Exception as e:
        # Shield internal logic from exposing too much detail in production.
        logger.error(f"Unexpected error in upload: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


# ── PRICING & USAGE ENDPOINT ─────────────────────────────────────────────────
# Returns global usage statistics and the current calculated price.
# Integrates with: core/database.py for persistent stats and core/models.py for schema.
@app.get("/api/pricing")
async def get_pricing(db: Session = Depends(get_db)):
    """
    Get current usage and pricing information.
    Read-only endpoint.
    """
    # 1. Registry: Fetch the singleton usage record from the database.
    stats = db.query(UsageStats).first()
    if not stats:
        # Bootstrapping: initialize the first record if the DB is fresh.
        stats = UsageStats(id=1, count=1000)
        db.add(stats)
        db.commit()
        db.refresh(stats)

    # 2. Calculation: Derive the price based on 1000-usage brackets.
    current_usage = stats.count
    tiers = math.floor((current_usage - 1000) / 1000)
    current_tier = max(0, tiers)
    current_price = 341 + (current_tier * 50)
    
    return {"usages": current_usage, "price": current_price}


# ── CORE ANALYSIS ENDPOINT ───────────────────────────────────────────────────
# Executes the full Review Insight Engine pipeline.
# Pipeline: Usage Track -> Deterministic Analysis -> AI Narrative -> Synthesis Validation.
@app.post("/api/analyze")
async def analyze_reviews(
    request: Request,
    columns: str = Form(...),
    data: str = Form(...),
    db: Session = Depends(get_db)
):
    """
    Analyze reviews and generate insights.
    
    Accepts the full structured data from the frontend (columns + data rows as JSON).
    Runs deterministic analyzer first, then AI for narrative prose only.
    
    Args:
        columns: JSON string of column names
        data: JSON string of data rows
        db: Database session
        
    Returns:
        Complete analysis report with narratives and validation
        
    Raises:
        HTTPException: If analysis fails
    """
    client_id = get_client_id(request)
    
    try:
        rate_limiter.check_rate_limit(f"analyze:{client_id}")
    except RateLimitError as e:
        raise HTTPException(
            status_code=429,
            detail=e.message,
            headers={"Retry-After": str(e.details.get("retry_after", 60))}
        )
    
    logger.info(f"Analysis request from {client_id}")
    
    try:
        # 1. Metric Logging: Increment the global usage count upon every successful trigger.
        stats = db.query(UsageStats).first()
        if not stats:
            stats = UsageStats(id=1, count=1000)
            db.add(stats)
        stats.count += 1
        db.commit()
        
        logger.debug(f"Usage count: {stats.count}")

        # 2. Deserialization: Convert JSON strings back into Python primitives.
        columns_list = json.loads(columns)
        data_list = json.loads(data)
        
        logger.info(f"Analyzing {len(data_list)} reviews with {len(columns_list)} columns")

        # 3. Pipeline Step A: Deterministic Analysis.
        # Integrates with: core/analyzer.py for scoring, themes, and stats.
        analyzer = Analyzer()
        result = analyzer.run(columns_list, data_list)

        if "error" in result:
            logger.error(f"Analyzer error: {result['error']}")
            raise HTTPException(status_code=400, detail=result["error"])

        # 4. Pipeline Step B: Generative Narrative.
        # Integrates with: core/ai_engine.py to request PM-style prose from Gemini.
        try:
            ai = AIEngine()
            narratives = ai.generate_narratives(result["_for_ai"])
        except Exception as e:
            logger.error(f"AI generation failed: {str(e)}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"AI narrative generation failed: {str(e)}"
            )

        # 5. Pipeline Step C: Cross-Validation (Synthesis).
        # Integrates with: core/synthesis_engine.py to ensure the AI isn't hallucinating.
        synthesis = SynthesisEngine()
        validation = synthesis.validate(result, narratives)
        
        logger.info(f"Validation score: {validation['validation_score']}, grade: {validation['grade']}")

        # 6. Assembly: Merge all results into a single payload and prune the internal '_for_ai' breadcrumbs.
        result["narratives"] = narratives
        result["validation"] = validation
        del result["_for_ai"]
        
        logger.info(f"Analysis completed successfully for {client_id}")

        return {"report": result}

    except HTTPException:
        raise
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {str(e)}")
        raise HTTPException(status_code=400, detail="Invalid JSON data")
    except Exception as e:
        logger.error(f"Unexpected error in analysis: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


# ── COMPETITOR COMPARISON ENDPOINT ──────────────────────────────────────────
# Performs a head-to-head AI analysis between two review datasets.
# Integrates with: AIEngine.compare for direct LLM synthesis.
@app.post("/api/compare")
async def compare_products(
    file_a: UploadFile = File(...),
    file_b: UploadFile = File(...),
    label_a: str = Form("My Product"),
    label_b: str = Form("Competitor"),
    db: Session = Depends(get_db)
):
    try:
        # 1. Registry: Increment usage for comparison tasks.
        stats = db.query(UsageStats).first()
        if not stats:
            stats = UsageStats(id=1, count=1000)
            db.add(stats)
        stats.count += 1
        db.commit()

        # 2. Payload Extraction: Read both files.
        contents_a = await file_a.read()
        contents_b = await file_b.read()

        # 3. Parsing: Direct extraction using the FileHandler.
        handler = FileHandler()
        result_a = handler.process_file(contents_a, file_a.filename)
        result_b = handler.process_file(contents_b, file_b.filename)

        if "error" in result_a or "error" in result_b:
            raise HTTPException(status_code=400, detail="Error parsing comparison files.")

        # 4. Text Truncation: Extract raw review strings for the AI prompt.
        col_a_idx = result_a["columns"].index(result_a["auto_detected_column"]) if result_a.get("auto_detected_column") in result_a["columns"] else 0
        col_b_idx = result_b["columns"].index(result_b["auto_detected_column"]) if result_b.get("auto_detected_column") in result_b["columns"] else 0

        reviews_text_a = " | ".join([str(r[col_a_idx]) for r in result_a["data"] if r[col_a_idx]])[:25000]
        reviews_text_b = " | ".join([str(r[col_b_idx]) for r in result_b["data"] if r[col_b_idx]])[:25000]

        # 5. Generative Step: Ask the AI to write the comparison matrix.
        ai = AIEngine()
        comparison = ai.compare(reviews_text_a, reviews_text_b, label_a, label_b)
        
        return comparison

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in comparison: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ── SERVER ENTRY POINT ───────────────────────────────────────────────────────
# Launches the FastAPI application using the Uvicorn ASGI server.
if __name__ == "__main__":
    logger.info(f"Starting server on {config.host}:{config.port}")
    logger.info(f"Environment: {config.environment}")
    logger.info(f"Debug mode: {config.debug}")
    
    # Run the app with configured host, port, and log settings.
    uvicorn.run(
        app,
        host=config.host,
        port=config.port,
        log_level=config.log_level.lower()
    )
