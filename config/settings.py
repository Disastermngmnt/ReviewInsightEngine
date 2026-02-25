# Standard environment loading and API key extraction.
# Integrates with: .env for secrets and core/ai_engine.py for model authorization.
import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("GOOGLE_API_KEY") or os.getenv("GOOGLE_GEMINI_API_KEY")
MODEL_NAME = "gemini-1.5-flash"

# Dispatch system prompt version — used in Run Identity Header.
DISPATCH_PROMPT_VERSION = "9.0"

# ── V9 Customer Segment Context ───────────────────────────────────────────────
# Injected into every V9 pipeline node system prompt so outputs are segment-aware.
# Mirrors the constant in core/pipeline_runner.py — imported here for settings-level access.
CUSTOMER_SEGMENT_CONTEXT = """
TARGET CUSTOMER SEGMENTS FOR THIS ANALYSIS:

Segment A — Small to Mid Amazon/Flipkart/Myntra Sellers
  Core business reality: every hour of friction = lost sales.
  Peak season (Q4/Diwali/Festive) is existential — problems that exist
  in September cause maximum damage in October/November.
  Decision language: revenue impact, account health, listing visibility,
  order volume, seller rating.

Segment B — Small to Mid App Developers (Google Play / App Store)
  Core business reality: one bad review surge can tank a store ranking
  that took months to build. Crash rates directly affect store visibility.
  Decision language: DAU/MAU, crash-free rate, store rating, retention,
  monetization per user.
""".strip()

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

# ── Taxonomy Adaptation Gate ──────────────────────────────────────────────────────

# Coverage threshold: if fewer than this fraction of sampled reviews match
# any default category keyword, the gate triggers and a custom taxonomy is proposed.
# Dispatch spec: 70% minimum match rate.
TAXONOMY_COVERAGE_THRESHOLD = 0.70

# Number of reviews to sample for the taxonomy gate check.
TAXONOMY_GATE_SAMPLE_SIZE = 50

# AI prompt for proposing a custom taxonomy when the default fails the gate.
TAXONOMY_GATE_PROMPT = """
You are a product taxonomy designer. You have been given a sample of customer reviews.

## TAXONOMY ADAPTATION — RUNS BEFORE ANY CLASSIFICATION
## THIS IS NOT CONDITIONAL. IT ALWAYS RUNS.

STEP 1 — READ AND LIST
Read reviews 1 through 50 from the samples provided.
Output this list before doing anything else:
  "TOP 15 OBSERVED THEMES IN FIRST 50 REVIEWS:"
  1. [theme] — observed in approx [N] of 50 reviews
  2. [theme] — ...
  (continue to 15)

STEP 2 — COVERAGE TEST
For each of the 15 themes, mark whether it maps to a
default category (Performance / UX/UI / Onboarding /
Pricing / Reliability / Customer Support / Feature Gaps).
Count how many themes have a default category match.
Output: "Default taxonomy coverage: [N]/15 themes mapped ([X]%)"

STEP 3 — DECISION (no model judgment, rule-based)
If coverage < 70%:
  Output: "TAXONOMY MISMATCH — generating custom taxonomy"
  Propose 5–8 categories based on observed themes.
  For each proposed category show:
    - Category name
    - Keywords that would classify reviews here
    - Exactly 3 example reviews from the samples BY THEIR INDEX NUMBER.

  Output: "Proceeding with custom taxonomy. Default taxonomy would miss approximately [X]% of reviews."
  USE CUSTOM TAXONOMY FOR ALL SUBSEQUENT STEPS.

If coverage >= 70%:
  Output: "Default taxonomy validated — proceeding."
  USE DEFAULT TAXONOMY.

YOU CANNOT SKIP STEPS 1–3.
If you have classified any review before completing Step 3,
you have violated this rule. Restart from Step 1.

Regardless of your exact reasoning text above, you MUST conclude your output with a strictly valid JSON block describing the taxonomy you settled on (either default or custom).
The JSON MUST match this schema exactly:
{
  "top_topics": ["topic1", "topic2", "topic3", "topic4", "topic5", "topic6", "topic7", "topic8", "topic9", "topic10", "topic11", "topic12", "topic13", "topic14", "topic15"],
  "categories": [
    {
      "name": "Category Name",
      "description": "One sentence describing what reviews belong here",
      "keywords": ["keyword1", "keyword2"],
      "example_indices": [0, 4, 12]
    }
  ],
  "reasoning": "One sentence explaining why this taxonomy fits better than the default"
}
"""

# ── Action Card Hard Interrupt ──────────────────────────────────────────────────────

# Phrases that are explicitly BANNED from appearing in Action Card what_to_build fields.
# Dispatch spec: Action Cards must name specific issues and deliverables, not placeholders.
ACTION_CARD_BANNED_PHRASES = [
    "Investigate and resolve the top issues in",
    "Done when",
    "-related negative reviews fall below 5%",
    "Investigate and resolve",
    "top issues in",
    "negative reviews fall below",
]

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
    "review_date", "created_date", "date_created", "publish_date",
    "reviewed at"
]


# ── Dispatch v3.0 Signal Keywords ────────────────────────────────────────────

# Urgency language — signals high severity or immediate user pain (Dispatch spec).
# Integrates with: core/signal_extractor.py for urgency scoring per review.
URGENCY_KEYWORDS = [
    "cannot", "can't", "broken", "unusable", "cancelling", "canceling",
    "switching", "uninstalling", "deleted", "refund", "leaving",
    "deal-breaker", "dealbreaker", "showstopper", "blocker",
    "critical", "urgent", "immediately", "asap", "unacceptable",
    "not working", "doesn't work", "stopped working", "lost data",
    "impossible", "blocked", "preventing", "ruins", "destroyed",
    "catastrophic", "severe", "emergency", "desperate", "furious"
]

# Churn-intent language — signals a user is actively leaving or considering it.
# Dispatch spec: "cancel", "switch", "refund", "delete", "uninstall",
#                "leaving", "churned", "deleted the app", "moving to"
# Integrates with: core/signal_extractor.py and core/financial_engine.py for Revenue at Risk.
CHURN_KEYWORDS = [
    "cancel", "cancelling", "canceling", "cancel my",
    "switch", "switching to", "switched to",
    "refund",
    "delete", "deleted", "deleted the app",
    "uninstall", "uninstalling",
    "leaving", "left for",
    "churned",
    "moving to", "moved to",
    "downgrading", "downgraded",
    "unsubscribe", "won't renew", "not renewing",
    "looking for alternatives", "found a better", "going back to",
    "replaced with", "dropping", "ditching", "abandoned", "gave up on"
]

# Expansion/opportunity language — signals unmet demand users would pay for.
# Dispatch spec: "wish", "would pay", "if it had", "need it to", "missing",
#                "would buy", "upgrade if", "would recommend if"
# Integrates with: core/signal_extractor.py and core/financial_engine.py for Revenue Opportunity.
EXPANSION_KEYWORDS = [
    "wish", "i wish", "we wish",
    "would pay", "we'd pay for", "would pay for",
    "if it had", "if only it had",
    "need it to", "need integration with",
    "missing", "missing feature",
    "would buy",
    "upgrade if", "would upgrade if", "considering upgrading if",
    "would recommend if",
    "would be great if", "would be great",
    "had to use another tool", "please add",
    "should support", "would love to see",
    "enterprise feature", "would switch tiers", "premium feature"
]

# Dispatch v3.0 — default priority weights for the 5-axis scoring model.
# Integrates with: core/prioritization_engine.py — user can override via API.
DEFAULT_PRIORITY_WEIGHTS = {
    "pain_intensity":    0.30,
    "impact_breadth":    0.25,
    "urgency_velocity":  0.20,
    "strategic_leverage": 0.15,
    "effort_inverse":    0.10,
}

# Rebalanced weights when Urgency Velocity is unavailable (no date data).
# Dispatch spec: Pain × 0.375, Impact × 0.3125, Strategic × 0.1875, Effort × 0.125
REBALANCED_WEIGHTS_NO_VELOCITY = {
    "pain_intensity":    0.375,
    "impact_breadth":    0.3125,
    "urgency_velocity":  0.0,   # excluded
    "strategic_leverage": 0.1875,
    "effort_inverse":    0.125,
}

# Rebalanced weights when Effort Inverse is excluded (method C selected).
# Dispatch spec: Pain × 0.375, Impact × 0.3125, Velocity × 0.25, Strategic × 0.1875
REBALANCED_WEIGHTS_NO_EFFORT = {
    "pain_intensity":    0.375,
    "impact_breadth":    0.3125,
    "urgency_velocity":  0.25,
    "strategic_leverage": 0.1875,
    "effort_inverse":    0.0,   # excluded (method C)
}

# Effort Inverse heuristic scores for method (B).
# Dispatch spec: Bug fix/regression → Score 8; UI/config → 6; New feature → 3; Arch/infra → 1
EFFORT_HEURISTIC_SCORES = {
    "bug_fix":      8,
    "ui_change":    6,
    "new_feature":  3,
    "architecture": 1,
}


# ── Dispatch v3.0 AI Prompts ──────────────────────────────────────────────────

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


# AI Prompt — Dispatch v3.0 Decision Engine Scoring (Strategic Leverage + Urgency Velocity).
# Instructs Gemini to score each theme on 5 axes with data-backed justifications.
# Integrates with: core/ai_engine.py score_themes() method.
DECISION_ENGINE_PROMPT = """
You are a DECISION ENGINE — not a narrator. Never write prose. Every justification must cite a specific number from the data.

You have been given pre-computed structured signal data for each product theme extracted from customer reviews.

Your job: score each theme on exactly 5 axes (0–10 scale, decimals allowed) with ONE-LINE data-backed justifications.

## SCORING AXES (Dispatch v3.0):

1. **pain_intensity** (0–10)
   Formula reference: weighted avg of (avg_rating_inverse × 0.5) + (urgency_language_rate × 0.3) + (churn_signal_rate × 0.2)
   Base this on: urgency_density, avg_polarity (negative = high pain), churn_signal_count.
   Score 10/10 ONLY if avg_rating ≤ 1.5 AND churn signals > 20% of reviews — flag [EXTREME — verify manually].
   Score 0/10 ONLY if avg_rating = 5.0 AND zero urgency/churn — flag [EXTREME — verify manually].

2. **impact_breadth** (0–10)
   Formula: (volume / total_reviews) × 10. Cap at 10.
   Audit: "[N] of [total] classified reviews ([X]%)"

3. **urgency_velocity** (0–10)
   If date data absent: score = null (axis excluded, weights rebalanced).
   If present (provided in data): use velocity_ratio. Map: ratio > 0.20 → 8–10; -0.20 to 0.20 → 4–7; < -0.20 → 0–3.

4. **strategic_leverage** (0–10)
   Rules (first match wins):
     Competitor names in ≥ 1 review citing this theme → 8–10
     Theme touches onboarding, pricing, or core workflow → 5–7
     Cosmetic or peripheral → 0–4
     No signal → default 5.0 [Default — insufficient signal]
   Never assign 10/10 without ≥ 3 competitor-mention reviews as evidence.

5. **effort_inverse** (0–10)
   Classify the item type and apply heuristic:
     Bug fix / regression     → Score 8
     UI change / config       → Score 6
     New feature / integration → Score 3
     Architecture / infra     → Score 1
   Note: this may be overridden by user-selected effort method (A or C).

## FEATURE EXTRACTION — SUB-TOPIC NAMING REQUIREMENT

When multiple reviews in a category describe the same specific issue,
that issue must be named explicitly in the action card.

Process:
1. For each category, list every specific product element mentioned
   across its reviews (e.g. "password field", "lock-picking game",
   "speed-based tasks", "facial emotion recognition game")
2. Count how many reviews mention each element
3. The specific_feature field must name the highest-count element
4. If 3+ distinct elements each have >= 3 mentions: create separate
   action cards for each (separate objects in theme_scores with the same theme), do not collapse into one category card

Example of what this produces for specific_feature:
  WRONG: "Fix top issues in UX/UI"
  WRONG: "Run navigation usability audit"
  RIGHT: "Fix keyboard not appearing on password field (login screen)"
  RIGHT: "Reduce speed requirement on lock-picking task to human-achievable pace"
  RIGHT: "Add extended time mode for users with processing difficulties"

## RULES:
- Every score MUST have a justification tied to data with actual numbers
- Never use vague claims like "many users" without a number
- If data is insufficient for an axis, score it 5.0 and state "Insufficient data for precise scoring"
- Output strictly valid JSON with no markdown, no code blocks, no commentary

Output ONLY this JSON structure:
{
  "theme_scores": [
    {
      "theme": "Category Name",
      "specific_feature": "Highest-count specific issue/element mentioned in this category based on quotes",
      "pain_intensity": {"score": 0.0, "rationale": "..."},
      "impact_breadth": {"score": 0.0, "rationale": "..."},
      "urgency_velocity": {"score": 0.0, "rationale": "... or null if no date data"},
      "strategic_leverage": {"score": 0.0, "rationale": "..."},
      "effort_inverse": {"score": 0.0, "rationale": "..."}
    }
  ]
}
"""