# Standard library and third-party imports for AI interaction, JSON handling, and internal project utilities.
# Integrates with: Google Gemini API for narrative generation and centralized logging/exception systems.
import google.generativeai as genai
import json
from config.settings import API_KEY, MODEL_NAME, NARRATIVE_PROMPT
from utils.logger import setup_logger
from utils.exceptions import AIEngineError, ConfigurationError

# Initialize the module-level logger.
# Integrates with: utils/logger.py for recording AI-related events and errors.
logger = setup_logger(__name__)


# Wrapper class for interactions with Google's Generative AI (Gemini).
# Integrates with: Analyzer.run output data to transform structured stats into human-readable narratives.
class AIEngine:
    def __init__(self):
        """
        Initialize AI engine with API configuration.
        
        Raises:
            ConfigurationError: If API key is missing or invalid
        """
        # 1. Validate the presence and format of the Google API Key.
        # Integrates with: .env configuration and config/environments.py for secure access.
        if not API_KEY:
            raise ConfigurationError("GOOGLE_API_KEY not configured")
        
        if len(API_KEY) < 20:
            raise ConfigurationError("GOOGLE_API_KEY appears invalid (too short)")
        
        # 2. Configure the generative AI client and specify the model to use.
        # Integrates with: config/settings.py for model selection (e.g., gemini-1.5-flash).
        try:
            genai.configure(api_key=API_KEY)
            self.model = genai.GenerativeModel(MODEL_NAME)
            logger.info(f"AI Engine initialized with model: {MODEL_NAME}")
        except Exception as e:
            logger.error(f"Failed to initialize AI engine: {e}", exc_info=True)
            raise ConfigurationError(f"AI engine initialization failed: {str(e)}")

    # Generates narrative reports (Executive Summary, RCA, etc.) based on deterministic analysis results.
    # Uses: genai.GenerativeModel and NARRATIVE_PROMPT from settings.
    # Integrates with: Frontend result cards (ReportTab) to display AI-enhanced product insights.
    def generate_narratives(self, stats: dict) -> dict:
        """
        Given pre-computed structured statistics, ask Gemini to write narrative
        prose only (executive summary, hypothesis, RCA, mermaid flowchart).
        Classification is NOT done here.
        
        Args:
            stats: Pre-computed statistics dictionary
            
        Returns:
            Dictionary with narrative fields
            
        Raises:
            AIEngineError: If generation fails
        """
        logger.info("Generating AI narratives")
        
        try:
            # Prepare the prompt by combining the narrative guidelines with the actual statistics.
            context = json.dumps(stats, ensure_ascii=False, indent=2)
            prompt = f"{NARRATIVE_PROMPT}\n\nPre-computed statistics:\n{context}"
            
            logger.debug(f"Prompt length: {len(prompt)} characters")

            # Call Gemini with a JSON constraint to ensure the response is machine-readable.
            # Integrates with: json.loads to parse the final narrative report.
            response = self.model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    response_mime_type="application/json",
                ),
            )
            
            result = json.loads(response.text)
            logger.info("Successfully generated AI narratives")
            return result
            
        # Robust error handling for malformed JSON or API failures.
        # Integrates with: utils/exceptions.py to raise specific AIEngineError types.
        except json.JSONDecodeError as e:
            raw = getattr(response, "text", "No text generated.")
            logger.error(f"AI JSON parse error: {e}\nRaw response: {raw}")
            raise AIEngineError(
                "AI returned invalid JSON",
                details={"error": str(e), "raw_response": raw[:500]}
            )
        except Exception as e:
            logger.error(f"AI narrative generation failed: {e}", exc_info=True)
            raise AIEngineError(f"AI narrative generation failed: {str(e)}")

    # Performs a competitive head-to-head analysis between two products based on provided reviews.
    # Integrates with: main.py API endpoint (/api/compare) to power the Compare mode in the UI.
    def compare(self, reviews_a: str, reviews_b: str, label_a: str, label_b: str) -> dict:
        """Head-to-head product comparison (unchanged)."""
        try:
            # Construct a structured comparison prompt requiring JSON output.
            comparison_prompt = f"""
You are comparing two products based on their customer reviews.

{label_a} reviews: {reviews_a}
{label_b} reviews: {reviews_b}

Output a strictly valid JSON with no markdown wrapping or code blocks:
{{
  "head_to_head": [
    {{"dimension": "Ease of Use", "score_a": 8, "score_b": 6}},
    {{"dimension": "Value", "score_a": 7, "score_b": 8}},
    {{"dimension": "Support", "score_a": 9, "score_b": 5}},
    {{"dimension": "Reliability", "score_a": 8, "score_b": 7}},
    {{"dimension": "Features", "score_a": 6, "score_b": 9}}
  ],
  "where_a_wins": [
    {{"point": "Better customer service", "evidence": "Multiple users mentioned fast replies"}}
  ],
  "where_b_wins": [
    {{"point": "More robust features", "evidence": "Users loved the advanced options"}}
  ],
  "opportunity": "What {label_a} could steal from {label_b}'s weaknesses...",
  "positioning": "One paragraph on how {label_a} should position against {label_b}..."
}}
"""
            # Request and parse the comparison result from Gemini.
            response = self.model.generate_content(
                comparison_prompt,
                generation_config=genai.types.GenerationConfig(
                    response_mime_type="application/json",
                ),
            )
            return json.loads(response.text)
        except Exception as e:
            # Catch-all for AI generation or parsing failures within comparison.
            raise Exception(f"AI Comparison failed: {str(e)}")
