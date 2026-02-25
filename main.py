# Standard and third-party imports for the FastAPI framework, database ORM, and utility functions.
# Integrates with: core/ modules for logic, utils/ for helpers, and config/ for settings.
from fastapi import FastAPI, File, UploadFile, Form, HTTPException, Depends, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from sqlalchemy.orm import Session
import uvicorn
import math
import json
import os
import asyncio

from core.auth import AuthManager
from core.file_handler import FileHandler
from core.play_store_api import PlayStoreConnector
from core.app_store_api import AppStoreConnector
from core.analyzer import Analyzer
from core.ai_engine import AIEngine, generate_run_id
from core.synthesis_engine import SynthesisEngine
from core.signal_extractor import extract_signals, aggregate_theme_signals
from core.prioritization_engine import compute_priority_scores, classify_quadrant
from core.financial_engine import compute_financial_impact, FinancialInputs
from core.dispatch_formatter import assemble_dispatch_report
from core.pipeline_runner import DispatchPipeline
from core.database import Base, engine, SessionLocal, get_db
from core.models import UsageStats
from core.taxonomy_gate import check_coverage, build_taxonomy_from_proposal, format_gate_result_for_frontend
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

@app.get("/marketing", response_class=HTMLResponse)
async def read_marketing():
    """Serve the marketing landing page."""
    try:
        with open("static/landing.html", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        logger.error("landing.html not found")
        raise HTTPException(status_code=404, detail="Marketing page not found")


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

# ── GOOGLE PLAY API ENDPOINT ─────────────────────────────────────────────────
# Fetches data via the official Google Play Developer API.
# Integrates with: core/play_store_api.py
@app.post("/api/fetch_play_store")
async def fetch_play_store(
    request: Request,
    package_name: str = Form(...),
    service_account_json: UploadFile = File(...)
):
    client_id = get_client_id(request)
    
    try:
        rate_limiter.check_rate_limit(f"fetch_play:{client_id}")
    except RateLimitError as e:
        raise HTTPException(
            status_code=429,
            detail=e.message,
            headers={"Retry-After": str(e.details.get("retry_after", 60))}
        )
    
    logger.info(f"Play Store fetch from {client_id} for {package_name}")
    
    try:
        # Extract json key
        json_contents = await service_account_json.read()
        
        connector = PlayStoreConnector(
            package_name=package_name,
            service_account_json_content=json_contents
        )
        
        # Max results 500 mapping to the same scale as MVP CSV uploads
        result = connector.fetch_reviews(max_results=500)
        
        if "error" in result:
            logger.warning(f"Play Store API error: {result['error']}")
            raise HTTPException(status_code=400, detail=result["error"])
            
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in play store fetch: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# ── APPLE APP STORE API ENDPOINT ─────────────────────────────────────────────
# Fetches data via the public iTunes RSS Customer Reviews feed.
# Integrates with: core/app_store_api.py
@app.post("/api/fetch_app_store")
async def fetch_app_store(
    request: Request,
    app_id: str = Form(...)
):
    client_id = get_client_id(request)
    
    try:
        rate_limiter.check_rate_limit(f"fetch_appstore:{client_id}")
    except RateLimitError as e:
        raise HTTPException(
            status_code=429,
            detail=e.message,
            headers={"Retry-After": str(e.details.get("retry_after", 60))}
        )
    
    logger.info(f"App Store fetch from {client_id} for {app_id}")
    
    try:
        # Max results 500 mapping to the same scale as MVP CSV uploads
        result = AppStoreConnector.fetch_reviews(app_id=app_id, max_pages=10)
        return result
        
    except ValueError as e:
        logger.warning(f"App Store API error: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Unexpected error in app store fetch: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))



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


# ── TAXONOMY GATE ENDPOINT ───────────────────────────────────────────────────
@app.post("/api/taxonomy_check")
async def check_taxonomy(
    request: Request,
    columns: str = Form(...),
    data: str = Form(...)
):
    """
    Evaluates whether the default taxonomy is appropriate for the uploaded reviews.
    Returns PASS or FAIL (with AI-proposed custom taxonomy).
    """
    client_id = get_client_id(request)
    try:
        rate_limiter.check_rate_limit(f"taxonomy_check:{client_id}")
    except RateLimitError as e:
        raise HTTPException(status_code=429, detail=e.message)

    try:
        columns_list = json.loads(columns)
        data_list = json.loads(data)

        # Basic parser just to get the review text out
        review_col = None
        for col in columns_list:
            if col.lower() in ["review", "content", "text", "body", "comment", "feedback"]:
                review_col = col
                break
        if not review_col and columns_list:
            review_col = columns_list[0]
            
        review_idx = columns_list.index(review_col) if review_col in columns_list else 0
        review_texts = [str(r[review_idx]) for r in data_list if len(r) > review_idx and str(r[review_idx]).strip()]

        # 1. Run the coverage check against default taxonomy
        gate_result = check_coverage(review_texts)

        # 2. If it fails, generate a custom taxonomy
        proposal = None
        if not gate_result["passes"]:
            ai = AIEngine()
            proposal = ai.propose_custom_taxonomy(gate_result["sample_texts"])

        # 3. Format and return
        return format_gate_result_for_frontend(gate_result, proposal)

    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON data")
    except Exception as e:
        logger.error(f"Taxonomy check failed: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ── CORE ANALYSIS ENDPOINT ───────────────────────────────────────────────────
# Executes the full Review Insight Engine pipeline.
# Pipeline: Usage Track -> Deterministic Analysis -> AI Narrative -> Synthesis Validation.
@app.post("/api/analyze")
async def analyze_reviews(
    request: Request,
    columns: str = Form(...),
    data: str = Form(...),
    total_users: str = Form(None),
    monthly_arpu: str = Form(None),
    segment_weights: str = Form(None),
    sprint_cost: str = Form(None),
    priority_weights: str = Form(None),
    effort_scoring_method: str = Form("B"),        # Dispatch v3.0: A / B / C
    filename: str = Form("unknown_file"),           # Dispatch Run Identity Header
    custom_taxonomy: str = Form(None),              # From taxonomy gate
    db: Session = Depends(get_db)
):
    """
    Analyze reviews and generate insights.
    
    Accepts the full structured data from the frontend (columns + data rows as JSON),
    plus optional business inputs for financial impact modelling.
    
    Args:
        columns: JSON string of column names
        data: JSON string of data rows
        total_users: Optional total active users (for financial model)
        monthly_arpu: Optional monthly ARPU in dollars (for financial model)
        segment_weights: Optional JSON string of segment weights
        sprint_cost: Optional avg engineering sprint cost in dollars
        priority_weights: Optional JSON string of custom priority axis weights
        db: Database session
        
    Returns:
        Complete analysis report with narratives, validation, priority matrix,
        and financial impact
        
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
        
        # Parse optional business inputs for the financial model.
        fin_inputs = FinancialInputs(
            total_users=int(total_users) if total_users else None,
            monthly_arpu=float(monthly_arpu) if monthly_arpu else None,
            segment_weights=json.loads(segment_weights) if segment_weights else None,
            sprint_cost=float(sprint_cost) if sprint_cost else None,
        )
        custom_weights = json.loads(priority_weights) if priority_weights else None
        
        logger.info(f"Analyzing {len(data_list)} reviews with {len(columns_list)} columns")
        logger.info(f"Financial inputs calibrated: {fin_inputs.is_calibrated}")

        # Generate Dispatch Run ID from data content (traceable per run)
        data_bytes = data.encode("utf-8")
        run_id = generate_run_id(data_bytes)

        # Parse custom taxonomy if the frontend confirmed a proposed one
        parsed_custom_taxonomy = None
        if custom_taxonomy:
            raw_proposal = json.loads(custom_taxonomy)
            parsed_custom_taxonomy = build_taxonomy_from_proposal(raw_proposal)

        # 3. Pipeline Step A: Deterministic Analysis.
        # Integrates with: core/analyzer.py for scoring, themes, and stats.
        analyzer = Analyzer()
        result = analyzer.run(columns_list, data_list, custom_taxonomy=parsed_custom_taxonomy)

        if "error" in result:
            logger.error(f"Analyzer error: {result['error']}")
            raise HTTPException(status_code=400, detail=result["error"])

        # 4. Pipeline Step B: Signal Extraction.
        # Enriches each parsed review with polarity, urgency, churn, expansion signals.
        parsed_reviews = result.get("_parsed_reviews", [])
        rating_scale = result["meta"].get("rating_scale", 5) or 5
        enriched_reviews = extract_signals(
            parsed_reviews,
            segment_weights=fin_inputs.segment_weights,
            rating_scale=rating_scale,
        )
        total_reviews = result["meta"]["total_reviews"]
        theme_signals = aggregate_theme_signals(enriched_reviews, total_reviews)
        
        logger.info(f"Signal extraction complete: {len(theme_signals)} themes")

        # 5. Pipeline Step C: Generative Narrative (existing — unchanged).
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

        # 6. Pipeline Step D: AI Theme Scoring (Dispatch v3.0 — 5-axis decision engine).
        # ENFORCEMENT: Never score items that belong in the Watch List (low volume).
        valid_roadmap_cats = {item["category"] for item in result.get("roadmap_items", [])}
        filtered_theme_signals = {
            k: v for k, v in theme_signals.items() if k in valid_roadmap_cats
        }

        velocity_available = result["meta"].get("has_date_col", False)
        try:
            ai_scores = ai.score_themes(filtered_theme_signals, total_reviews, velocity_available=velocity_available)
        except Exception as e:
            logger.error(f"AI theme scoring failed: {str(e)}", exc_info=True)
            # Non-fatal: degrade gracefully, priority matrix will be empty.
            ai_scores = {"theme_scores": []}

        # 7. Pipeline Step E: Priority Scoring (Dispatch v3.0 formula).
        priority_matrix = compute_priority_scores(
            ai_scores.get("theme_scores", []),
            weights=custom_weights,
            effort_method=effort_scoring_method,
            velocity_available=velocity_available,
        )
        
        logger.info(f"Priority matrix: {len(priority_matrix)} themes ranked")

        # 8. Pipeline Step F: Financial Impact Modelling (Dispatch v3.0 formulas).
        financial_impact = compute_financial_impact(
            theme_signals, fin_inputs, total_reviews, priority_scores=priority_matrix
        )

        # 9. Pipeline Step G: Quadrant Classification.
        # Build a financial lookup for quadrant classification.
        fin_lookup = {}
        for fi in financial_impact:
            total_fin = 0
            if fi.get("revenue_at_risk") is not None:
                total_fin = (fi.get("revenue_at_risk", 0) or 0) + (fi.get("revenue_opportunity", 0) or 0)
            else:
                total_fin = None
            fin_lookup[fi["theme"]] = total_fin

        decision_quadrant = []
        for item in priority_matrix:
            theme = item["theme"]
            fin_val = fin_lookup.get(theme)
            quadrant = classify_quadrant(item["priority_score"], fin_val)
            decision_quadrant.append({
                "theme": theme,
                "priority_score": item["priority_score"],
                "financial_impact": fin_val,
                "quadrant": quadrant,
            })

        # 10. Pipeline Step H: Cross-Validation (Synthesis — existing, unchanged).
        synthesis = SynthesisEngine()
        validation = synthesis.validate(result, narratives)
        
        logger.info(f"Validation score: {validation['validation_score']}, grade: {validation['grade']}")

        # 11. Pipeline Step I: Dispatch v3.0 Report Assembly.
        financial_inputs_echo = {
            "total_users": int(total_users) if total_users else None,
            "monthly_arpu": float(monthly_arpu) if monthly_arpu else None,
            "segment_weights": json.loads(segment_weights) if segment_weights else None,
            "sprint_cost": float(sprint_cost) if sprint_cost else None,
        }
        dispatch_report = assemble_dispatch_report(
            run_id=run_id,
            filename=filename,
            report=result,
            narratives=narratives,
            priority_scores=priority_matrix,
            financial_impact=financial_impact,
            financial_inputs_echo=financial_inputs_echo,
            effort_method=effort_scoring_method,
        )

        # 12. Assembly: Merge all results into a single payload.
        result["narratives"] = narratives
        result["validation"] = validation
        result["priority_matrix"] = priority_matrix
        result["financial_impact"] = financial_impact
        result["decision_quadrant"] = decision_quadrant
        result["financial_calibrated"] = fin_inputs.is_calibrated
        result["run_id"] = run_id
        del result["_for_ai"]
        result.pop("_parsed_reviews", None)
        
        logger.info(f"Analysis completed successfully for {client_id}")

        return {"report": result, "dispatch_report": dispatch_report}

    except HTTPException:
        raise
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {str(e)}")
        raise HTTPException(status_code=400, detail="Invalid JSON data")
    except Exception as e:
        logger.error(f"Unexpected error in analysis: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")



# ── V9 PIPELINE ENDPOINT ─────────────────────────────────────────────────────
# Runs the 8-node Dispatch V9 pipeline with LLM auto-switching.
# Streams SSE progress events so the UI can show per-node status in real time.
@app.post("/api/analyze_v9")
async def analyze_reviews_v9(
    request: Request,
    csv_text: str = Form(...),            # Raw CSV as plain text string
    total_users: str = Form(None),
    monthly_arpu: str = Form(None),
    sprint_cost: str = Form(None),
    db: Session = Depends(get_db),
):
    """
    V9 multi-node pipeline analysis with SSE streaming.
    Accepts raw CSV text plus optional business inputs.
    Returns a Server-Sent Events stream — one event per completed node.

    SSE event format:
        data: {"node": N, "label": "...", "status": "complete"|"error"|"done", "data": {...}}

    Final event (node=8, status="done") contains the full context store.
    """
    client_id = get_client_id(request)
    try:
        rate_limiter.check_rate_limit(f"analyze_v9:{client_id}")
    except RateLimitError as e:
        raise HTTPException(
            status_code=429,
            detail=e.message,
            headers={"Retry-After": str(e.details.get("retry_after", 60))}
        )

    logger.info(f"[V9] Pipeline request from {client_id}")

    # Increment usage counter (non-fatal if DB unavailable)
    try:
        stats = db.query(UsageStats).first()
        if not stats:
            stats = UsageStats(id=1, count=1000)
            db.add(stats)
        stats.count += 1
        db.commit()
    except Exception as db_err:
        logger.warning(f"[V9] Usage counter failed: {db_err}")

    # Parse optional business inputs
    business_inputs: dict = {}
    if total_users:
        try:
            business_inputs["total_users"] = int(total_users)
        except ValueError:
            pass
    if monthly_arpu:
        try:
            business_inputs["monthly_arpu"] = float(monthly_arpu)
        except ValueError:
            pass
    if sprint_cost:
        try:
            business_inputs["sprint_cost"] = float(sprint_cost)
        except ValueError:
            pass

    pipeline = DispatchPipeline(csv_text=csv_text, business_inputs=business_inputs)

    async def event_generator():
        """Yield SSE-formatted strings for each pipeline node event."""
        try:
            async for event in pipeline.run_streaming():
                payload = json.dumps(event, ensure_ascii=False, default=str)
                yield f"data: {payload}\n\n"
                await asyncio.sleep(0)  # Yield control to allow response flushing
        except Exception as exc:
            logger.error(f"[V9] Streaming pipeline fatal: {exc}", exc_info=True)
            error_payload = json.dumps({"status": "fatal", "error": str(exc)})
            yield f"data: {error_payload}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


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
