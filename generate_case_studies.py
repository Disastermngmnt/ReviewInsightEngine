import asyncio
import os
import json
import logging
from core.app_store_api import AppStoreConnector
from core.analyzer import Analyzer
from core.ai_engine import AIEngine, generate_run_id
from core.synthesis_engine import SynthesisEngine
from core.signal_extractor import extract_signals, aggregate_theme_signals
from core.prioritization_engine import compute_priority_scores, classify_quadrant
from core.dispatch_formatter import assemble_dispatch_report
from utils.logger import setup_logger
from config.environments import config

logger = setup_logger(__name__)

# Ensure output directory exists
os.makedirs("case_studies", exist_ok=True)

APPS_TO_TEST = {
    "Spotify": "324684580",
    "Instagram": "389801252",
    "Airbnb": "401626263",
    "Uber": "368677368"
}

from core.taxonomy_gate import check_coverage, build_taxonomy_from_proposal

async def generate_case_study(app_name: str, app_id: str):
    logger.info(f"Starting Case Study generation for {app_name} (ID: {app_id})")
    
    try:
        # 1. Fetch App Store Reviews
        fetch_result = AppStoreConnector.fetch_reviews(app_id, max_pages=10) # 500 reviews
        columns = fetch_result["columns"]
        data_rows = fetch_result["data"]
        logger.info(f"Fetched {len(data_rows)} reviews for {app_name}")
        
        # Determine review column
        review_col = "Review Text"
        if review_col not in columns:
            review_col = columns[1] if len(columns) > 1 else columns[0]
            
        # 2. Extract texts for taxonomy gate check
        idx = columns.index(review_col)
        review_texts = [str(r[idx]) for r in data_rows if len(r) > idx and str(r[idx]).strip()][:25]
        
        # 3. Custom Taxonomy check
        gate_res = check_coverage(review_texts)
        custom_taxonomy = None
        if not gate_res.get("passes"):
            logger.info(f"{app_name}: Using custom taxonomy.")
            ai_engine = AIEngine()
            proposal = ai_engine.propose_custom_taxonomy(review_texts)
            if "error" not in proposal:
                custom_taxonomy = build_taxonomy_from_proposal(proposal)
        
        # 4. Analyze Data
        analyzer = Analyzer()
        payload = analyzer.run(
            columns,
            data_rows,
            custom_taxonomy=custom_taxonomy
        )
        
        # 5. Extract Theme Signals
        reviews_metadata = payload.get("_parsed_reviews", [])
        theme_signals = extract_signals(reviews_metadata)
        
        # 6. AI Engine
        ai_engine = AIEngine()
        run_id = generate_run_id(b"case_study")
        data_for_ai = payload.get("_for_ai", {})
        
        # Exclude watch list items from AI if possible
        watch_list_cats = set([item["category"] for item in payload.get("roadmap_items", [])])
        ai_theme_signals = {k: v for k, v in theme_signals.items() if k in watch_list_cats}
        total_reviews = payload["meta"]["total_reviews"]
        velocity_available = payload["meta"].get("has_date_col", False)

        try:
             narratives = ai_engine.generate_narratives(data_for_ai)
             ai_scores = ai_engine.score_themes(ai_theme_signals, total_reviews, velocity_available=velocity_available)
        except Exception as e:
             logger.error(f"AI Engine failed for {app_name}: {str(e)}")
             return False

        # 7. Apply Score Formula
        priority_matrix = compute_priority_scores(
            ai_scores.get("theme_scores", []), 
            effort_method='B',
            velocity_available=velocity_available
        )
        
        from core.financial_engine import compute_financial_impact, FinancialInputs
        # Synthetic financial inputs for high-growth B2C cases
        fin_inputs = FinancialInputs(total_users=5000000, monthly_arpu=12.99, sprint_cost=25000)
        financial_impact = compute_financial_impact(
            theme_signals, fin_inputs, total_reviews, priority_scores=priority_matrix
        )
        
        # 8. Synthesis Validation
        synthesis_engine = SynthesisEngine()
        val_result = synthesis_engine.validate(payload, narratives)
        
        # 9. Format Dispatch
        run_metadata = {
            "run_id": run_id,
            "filename": f"{app_name}_AppStore_Scrape.json",
            "effort_scoring_method": "B", 
        }
        dispatch_report = assemble_dispatch_report(
            priority_ranking=priority_matrix,
            financial_impact=financial_impact,
            validation_data=val_result,
            narratives=narratives,
            run_metadata=run_metadata,
            effort_method="B",
            watch_list=payload.get("s13_watch_list", {}).get("items", [])
        )
        payload["dispatch_report"] = dispatch_report
        payload["report"] = payload.get("report", {})
        payload["report"]["narratives"] = narratives
        
        # 10. Save Results
        file_path = f"case_studies/{app_name}_Dispatch_Report.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
            
        logger.info(f"Successfully generated case study for {app_name} at {file_path}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to generate case study for {app_name}: {str(e)}", exc_info=True)
        return False

async def main():
    logger.info("Starting batch case study generation for marketing assets...")
    for app_name, app_id in APPS_TO_TEST.items():
        success = await generate_case_study(app_name, app_id)
        if success:
            logger.info(f"✅ Completed {app_name}")
        else:
            logger.error(f"❌ Failed {app_name}")

if __name__ == "__main__":
    asyncio.run(main())
