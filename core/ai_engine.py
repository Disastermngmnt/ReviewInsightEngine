# Standard library and third-party imports for AI interaction, JSON handling, and internal project utilities.
# Integrates with: Google Gemini API for narrative generation and centralized logging/exception systems.
import google.generativeai as genai
import hashlib
import json
from datetime import datetime, timezone
from config.settings import API_KEY, MODEL_NAME, NARRATIVE_PROMPT, DECISION_ENGINE_PROMPT, DISPATCH_PROMPT_VERSION, TAXONOMY_GATE_PROMPT
from utils.logger import setup_logger
from utils.exceptions import AIEngineError, ConfigurationError

# Initialize the module-level logger.
# Integrates with: utils/logger.py for recording AI-related events and errors.
logger = setup_logger(__name__)


def generate_run_id(file_bytes: bytes | None = None) -> str:
    """
    Generate a Dispatch Run Identity Header ID.
    Format: {timestamp}-{first-8-chars-of-input-file-sha256}
    If no file bytes provided, uses 'noinput' as hash prefix.
    """
    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    if file_bytes:
        file_hash = hashlib.sha256(file_bytes).hexdigest()[:8]
    else:
        file_hash = "noinput0"
    return f"{ts}-{file_hash}"


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
            raise ConfigurationError("AI API key not configured. Set GOOGLE_GEMINI_API_KEY in .env")
        
        if len(API_KEY) < 20:
            raise ConfigurationError("AI API key appears invalid (too short)")
        
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

    # Scores each product theme on 5 Dispatch v3.0 axes using structured signal data.
    # Uses: DECISION_ENGINE_PROMPT from settings and aggregated theme signals from signal_extractor.
    # Integrates with: core/prioritization_engine.py to compute final priority scores.
    def score_themes(self, theme_signals: dict, total_reviews: int, velocity_available: bool = True) -> dict:
        """
        Given aggregated theme-level signal data, ask Gemini to score each theme
        on 5 axes (0–10) with data-backed justifications.

        Args:
            theme_signals: dict keyed by category, from signal_extractor.aggregate_theme_signals()
            total_reviews: total number of reviews for context

        Returns:
            Dictionary with 'theme_scores' list

        Raises:
            AIEngineError: If generation or parsing fails
        """
        logger.info("Scoring themes via AI Decision Engine (Dispatch v3.0)")

        try:
            # Prepare structured signal data as context for the prompt.
            context = json.dumps(
                {
                    "total_reviews": total_reviews,
                    "velocity_data_available": velocity_available,
                    "dispatch_prompt_version": DISPATCH_PROMPT_VERSION,
                    "themes": theme_signals,
                },
                ensure_ascii=False,
                indent=2,
            )
            prompt = f"{DECISION_ENGINE_PROMPT}\n\nPre-computed theme signal data:\n{context}"

            logger.debug(f"Decision engine prompt length: {len(prompt)} characters")

            response = self.model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    response_mime_type="application/json",
                ),
            )

            result = json.loads(response.text)

            # Validate structure
            if "theme_scores" not in result:
                raise AIEngineError(
                    "AI response missing 'theme_scores' key",
                    details={"raw_response": response.text[:500]},
                )

            logger.info(f"Successfully scored {len(result['theme_scores'])} themes")
            return result

        except json.JSONDecodeError as e:
            raw = getattr(response, "text", "No text generated.")
            logger.error(f"AI scoring JSON parse error: {e}\nRaw response: {raw}")
            raise AIEngineError(
                "AI returned invalid JSON for theme scoring",
                details={"error": str(e), "raw_response": raw[:500]},
            )
        except AIEngineError:
            raise
        except Exception as e:
            logger.error(f"AI theme scoring failed: {e}", exc_info=True)
            raise AIEngineError(f"AI theme scoring failed: {str(e)}")

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

    # ── Taxonomy Adaptation Gate ─────────────────────────────────────────────
    # Integrates with: core/taxonomy_gate.py (called when gate check fails).
    def propose_custom_taxonomy(self, sample_texts: list[str]) -> dict:
        """
        When the default taxonomy fails the 70% coverage gate, ask Gemini
        to design a custom taxonomy that fits the product's vocabulary.

        Args:
            sample_texts: List of raw review strings (up to 50) to analyse.

        Returns:
            Proposal dict: {"categories": [...], "reasoning": "..."}.
            Falls back to empty on JSON error.
        """
        logger.info(f"Proposing custom taxonomy for {len(sample_texts)} sampled reviews")

        # Enumerate samples for AI to reference by index.
        numbered = "\n".join(
            f"[{i}] {text[:300]}" for i, text in enumerate(sample_texts)
        )
        prompt = (
            TAXONOMY_GATE_PROMPT.strip()
            + "\n\nSAMPLED REVIEWS:\n"
            + numbered
        )

        try:
            response = self.model.generate_content(prompt)
            text = response.text
            
            # Extract json block if wrapped in markdown or just find first { and last }
            import re
            json_str = text
            match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL | re.IGNORECASE)
            if match:
                json_str = match.group(1)
            else:
                start = text.find('{')
                end = text.rfind('}')
                if start != -1 and end != -1:
                    json_str = text[start:end+1]
                    
            result = json.loads(json_str)
            logger.info(
                f"Custom taxonomy proposed: {len(result.get('categories', []))} categories"
            )
            return result
        except Exception as e:
            logger.error(f"Custom taxonomy proposal failed: {e}", exc_info=True)
            # Return minimal fallback structure so caller can handle gracefully.
            return {"categories": [], "reasoning": f"AI error: {str(e)}"}
