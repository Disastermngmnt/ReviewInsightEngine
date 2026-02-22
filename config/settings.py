# Standard environment loading and API key extraction.
# Integrates with: .env for secrets and core/ai_engine.py for model authorization.
import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("GOOGLE_API_KEY")
MODEL_NAME = "gemini-2.5-flash"

# Hardcoded list of allowed Order IDs for offline or early-access validation.
# Integrates with: core/auth.py as a primary fallback before checking the database.
VALID_ORDER_IDS = ["ORD-123", "ORD-456", "INSIGHTS2026", "TEST123"]

# The Master Categorization Schema (Taxonomy).
# Defines the keywords used to map raw review text to logical product categories.
# Integrates with: core/analyzer.py (_classify_review) to perform deterministic tagging.
TAXONOMY = {
    "Performance": [
        "slow", "speed", "lag", "fast", "loading", "crash", "freeze", "hang",
        "responsive", "latency", "timeout", "delay", "performance", "quick"
    ],
    "UX/UI": [
        "ui", "ux", "design", "interface", "layout", "navigation", "button",
        "screen", "menu", "dashboard", "confusing", "intuitive", "ugly",
        "beautiful", "dark mode", "theme", "font", "color", "visual"
    ],
    "Onboarding": [
        "onboard", "sign up", "signup", "setup", "install", "tutorial",
        "guide", "documentation", "getting started", "first time", "learn",
        "confusing start", "registration"
    ],
    "Pricing": [
        "price", "cost", "expensive", "cheap", "value", "money", "subscription",
        "plan", "billing", "payment", "afford", "free", "paid", "tier",
        "refund", "worth", "overpriced"
    ],
    "Reliability": [
        "reliable", "unreliable", "downtime", "outage", "error", "bug",
        "glitch", "stable", "unstable", "broken", "failed", "fail",
        "always crashes", "doesn't work", "not working"
    ],
    "Customer Support": [
        "support", "customer service", "help", "response", "ticket", "agent",
        "wait", "reply", "resolve", "chat", "email support", "rude", "helpful",
        "ignored", "escalate", "refund request"
    ],
    "Feature Gaps": [
        "missing", "feature", "wish", "want", "need", "request", "add",
        "would be great", "should have", "integration", "export", "import",
        "api", "lacks", "no option", "cannot"
    ],
    "Other": []  # Catch-all — assigned when no other category matches
}

# Keyword-based sentiment detector.
# Used when numeric ratings (1-5) are unavailable in the source file.
# Integrates with: core/analyzer.py (_derive_sentiment_from_text).
SENTIMENT_KEYWORDS = {
    "Positive": [
        "love", "great", "excellent", "amazing", "fantastic", "awesome",
        "perfect", "best", "wonderful", "happy", "impressed", "brilliant",
        "easy", "smooth", "reliable", "fast", "helpful", "recommend",
        "good", "nice", "superb", "outstanding", "satisfied"
    ],
    "Negative": [
        "hate", "terrible", "awful", "horrible", "worst", "bad", "poor",
        "disappointing", "frustrating", "annoying", "useless", "broken",
        "slow", "crash", "failed", "expensive", "rude", "ignored",
        "waste", "refund", "never again", "unacceptable", "buggy", "glitch"
    ],
    # Neutral is the automatic fallback if no keywords from the above lists are found.
}

# Heuristic lists for automated column detection.
# These map common CSV/Excel headers to the application's internal data requirements.
# Integrates with: core/file_handler.py and core/analyzer.py for structural mapping.
COMMON_REVIEW_COLUMNS = [
    "review text", "body", "body html", "note", "description", "comment",
    "conversation body", "reviews", "text", "feedback", "content",
    "review content", "review body", "message", "remarks", "opinion",
    "review", "user review", "customer review", "customer feedback"
]

RATING_COLUMNS = [
    "rating", "score", "stars", "star rating", "review score",
    "overall rating", "satisfaction", "rate", "grade", "points"
]

DATE_COLUMNS = [
    "date", "created", "created_at", "timestamp", "review date",
    "submitted at", "posted", "time", "datetime", "date posted",
    "review_date", "created_date", "date_created", "publish_date"
]


# AI prompt — Gemini only writes narrative prose; classification is done in Python.
NARRATIVE_PROMPT = """
You are an expert Senior Product Manager writing a product analysis report.
You have been given pre-computed structured statistics about customer reviews.
Your job is to write ONLY the narrative prose sections — do NOT re-classify or re-score anything.

Output ONLY a strictly valid JSON object with no markdown, no code blocks, no commentary:

{
  "executive_summary": "One paragraph (4–6 sentences) narrating the overall health of the product based on the statistics provided. Write for a C-suite audience.",
  "hypothesis": "One paragraph (3–5 sentences) explaining what is likely causing the top issues and what will happen if left unfixed.",
  "rca_body": "One paragraph (3–5 sentences) summarizing the root cause analysis across the top problem categories.",
  "mermaid_flowchart": "A valid Mermaid graph TD flowchart string showing the causal chain of the top 2–3 problems. Use \\n for newlines. Example: graph TD\\n A[Root Cause] --> B(Effect)"
}
"""