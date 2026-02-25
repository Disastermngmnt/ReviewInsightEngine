"""
Dispatch V9 Pipeline Runner — ReviewInsightEngine
===================================================
Executes the 8-node analysis pipeline where each node has exactly one
job, receives selective context from prior nodes, and deposits structured
JSON into a context store. Subsequent nodes pull from that store.

Node sequence:
  0 — Validation & Pre-flight stats
  1 — Taxonomy Adaptation
  2 — Classification
  3 — Feature Extraction (tiered — never produces zero items)
  4 — 5-Axis Scoring (Pain/Breadth/Velocity/Strategic/Effort)
  5 — Financial Model (Revenue at Risk, Cost of Inaction, ROI)
  6 — Action Cards (top 5 items → 5 structured cards)
  7 — Strategic Plan (5 steps + 7-horizon time-phased plan)

Context compression fires before Node 3 and Node 7 to stay under
token budgets when the upstream context grows large.
"""

import json
import logging
from typing import Any, AsyncGenerator

from core.llm_orchestrator import LLMOrchestrator

logger = logging.getLogger(__name__)

# ─── CUSTOMER SEGMENT CONTEXT ────────────────────────────────────────────────
# Injected into every system prompt so all node outputs are segment-aware.
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

When scoring items and writing action cards, always frame the impact in
terms of these segments. Revenue at Risk should reference marketplace
seller accounts or app store rankings, not generic users. Action card
deliverables should reference specific segment workflows. Strategic
milestones should reflect segment-specific business cycles.
""".strip()


class DispatchPipeline:
    """
    Runs the full 8-node V9 analysis pipeline against a CSV text string.

    Args:
        csv_text:        Raw CSV content as a string (headers + data rows).
        business_inputs: Optional dict with keys:
                           total_users   (int)
                           monthly_arpu  (float, in USD)
                           sprint_cost   (float, optional)
    """

    def __init__(self, csv_text: str, business_inputs: dict | None = None):
        self.orchestrator = LLMOrchestrator()
        self.csv_text = csv_text
        self.business_inputs = business_inputs or {}

        # ── Context Store ──────────────────────────────────────────────────
        # Each node writes its structured output here; later nodes read it.
        self.context: dict[str, Any] = {
            "raw":       None,   # Node 0 — validation stats
            "taxonomy":  None,   # Node 1 — final taxonomy dict
            "classified": None,  # Node 2 — per-category counts
            "features":  None,   # Node 3 — feature items list
            "scored":    None,   # Node 4 — scored items with 5 axes
            "financial": None,   # Node 5 — financial model per item
            "cards":     None,   # Node 6 — 5 action cards
            "strategy":  None,   # Node 7 — strategic steps + action plan
            "model_used": "v9-pipeline",
        }

    # ─── HELPERS ──────────────────────────────────────────────────────────────

    def _csv_preview(self, max_chars: int = 12_000) -> str:
        """Truncated CSV for validation/taxonomy nodes."""
        return self.csv_text[:max_chars]

    def _csv_sample_rows(self, start: int = 1, end: int = 51) -> str:
        """Return lines start..end (0-indexed with header at 0)."""
        lines = self.csv_text.split("\n")
        return "\n".join(lines[start:end])

    def _safe_parse(self, raw: str, node_name: str) -> dict | list:
        """
        Parse JSON from model output. Strips markdown code fences if present.
        Returns a best-effort empty structure on failure so the pipeline continues.
        """
        text = raw.strip()
        # Strip ```json ... ``` or ``` ... ```
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first and last fence lines
            lines = [l for l in lines if not l.strip().startswith("```")]
            text = "\n".join(lines).strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            logger.error(f"[Pipeline:{node_name}] JSON parse failed: {exc} | raw[:200]={raw[:200]}")
            # Return a graceful degraded structure
            return {"_parse_error": str(exc), "_raw": raw[:500]}

    async def _compress_context(self, node_outputs: dict) -> str:
        """
        Compress context dict to stay under token budget.
        Uses the cheapest available model (classification task type).
        Falls back to truncated JSON if compression fails.
        """
        context_str = json.dumps(node_outputs, ensure_ascii=False, default=str)
        if len(context_str) < 8_000:
            return context_str  # Small enough — use as-is

        try:
            resp = await self.orchestrator.query(
                task_type="compression",
                system_prompt=(
                    "You are a data compressor. Reduce the following JSON to its most "
                    "essential facts, preserving all numbers, named items, and scores. "
                    "Return valid JSON only, no commentary."
                ),
                user_message=(
                    f"Compress this context to under 3000 characters:\n{context_str[:15000]}"
                ),
                options={"max_tokens": 1_200, "json_mode": True},
            )
            return resp["result"]
        except Exception as exc:
            logger.warning(f"[Pipeline:compress] Compression failed ({exc}), using truncation")
            return context_str[:7_000]

    # ─── NODE 0: Pre-processing & Validation ─────────────────────────────────

    async def run_node0_validation(self) -> dict:
        """Count reviews, detect date range, extract global signal counts."""
        resp = await self.orchestrator.query(
            task_type="classification",
            system_prompt=(
                "You are a data validation engine. Analyse the CSV data and return "
                "ONLY a strictly valid JSON object — no commentary, no markdown.\n"
                + CUSTOMER_SEGMENT_CONTEXT
            ),
            user_message=f"""
Analyse this review CSV and return a JSON object with exactly these fields:
{{
  "totalReviews": number,
  "duplicatesFound": number,
  "duplicatesRemoved": number,
  "cleanedReviewCount": number,
  "dateRange": {{"min": "ISO date or null", "max": "ISO date or null"}},
  "ratingDistribution": {{"1": 0, "2": 0, "3": 0, "4": 0, "5": 0}},
  "avgRating": number,
  "positiveCount": number,
  "neutralCount": number,
  "negativeCount": number,
  "churnSignalCount": number,
  "urgencySignalCount": number,
  "expansionSignalCount": number,
  "runId": "timestamp"
}}

Rating rules: 1-2 = negative, 3 = neutral, 4-5 = positive.
Churn signals: cancel, switch, uninstall, leaving, refund, deleted.
Urgency signals: cannot, broken, unusable, crash, freeze, stuck.
Expansion signals: wish, would pay, missing, need it to, upgrade if.
If no rating column exists, infer sentiment from text keywords.

CSV DATA (first 12000 chars):
{self._csv_preview()}
""",
            options={"max_tokens": 600, "json_mode": True},
        )
        self.context["raw"] = self._safe_parse(resp["result"], "node0")
        self.context["model_used"] = resp.get("model_used", "v9-pipeline")
        logger.info(f"[Pipeline:Node0] Validation complete. model={resp['model_used']}")
        return self.context["raw"]

    # ─── NODE 1: Taxonomy Adaptation ─────────────────────────────────────────

    async def run_node1_taxonomy(self) -> dict:
        """Decide whether to use the default taxonomy or propose a custom one."""
        sample_rows = self._csv_sample_rows(1, 51)
        resp = await self.orchestrator.query(
            task_type="classification",
            system_prompt=(
                "You are a taxonomy designer. Analyse review content and design "
                "the optimal classification system. Return ONLY valid JSON.\n"
                + CUSTOMER_SEGMENT_CONTEXT
            ),
            user_message=f"""
Read these 50 reviews and design a taxonomy.

Step 1: List the 15 most frequent themes you observe.
Step 2: Calculate what % of these 50 reviews the DEFAULT taxonomy covers.
  Default taxonomy categories: Performance, UX/UI, Onboarding, Pricing,
  Reliability, Customer Support, Feature Gaps
Step 3: If coverage < 70%, propose a CUSTOM taxonomy of 5-8 categories.
Step 4: Return the taxonomy to use (default or custom).

Return JSON:
{{
  "observedThemes": ["theme1", "theme2"],
  "defaultCoveragePercent": number,
  "taxonomyType": "default",
  "finalTaxonomy": {{
    "CategoryName": ["keyword1", "keyword2"]
  }},
  "rationale": "one sentence"
}}

FIRST 50 REVIEWS:
{sample_rows}
""",
            options={"max_tokens": 1_800, "json_mode": True},
        )
        self.context["taxonomy"] = self._safe_parse(resp["result"], "node1")
        logger.info(
            f"[Pipeline:Node1] Taxonomy set: "
            f"{self.context['taxonomy'].get('taxonomyType', 'unknown')} | model={resp['model_used']}"
        )
        return self.context["taxonomy"]

    # ─── NODE 2: Classification ───────────────────────────────────────────────

    async def run_node2_classification(self) -> dict:
        """Classify every review using the Node 1 taxonomy."""
        taxonomy_ctx = json.dumps(
            self.context["taxonomy"].get("finalTaxonomy", {}), ensure_ascii=False
        )
        resp = await self.orchestrator.query(
            task_type="classification",
            system_prompt=(
                "You are a review classifier. Classify each review using the provided "
                "taxonomy and return ONLY valid JSON."
            ),
            user_message=f"""
Classify every review using this taxonomy:
{taxonomy_ctx}

Rules:
- Assign each review to exactly one category (highest keyword match count wins).
- Ties broken by: category whose reviews have lower average rating.
- Reviews matching no category go to "Other".
- Return counts and representative review indices per category.

Return JSON:
{{
  "categories": {{
    "CategoryName": {{
      "count": number,
      "avgRating": number,
      "reviewIds": [0, 1, 2],
      "churnSignals": number,
      "urgencySignals": number
    }}
  }},
  "otherCount": number,
  "otherPercent": number,
  "totalClassified": number
}}

FULL CSV (up to 20000 chars):
{self.csv_text[:20_000]}
""",
            options={"max_tokens": 2_500, "json_mode": True},
        )
        self.context["classified"] = self._safe_parse(resp["result"], "node2")
        total = self.context["classified"].get("totalClassified", "?")
        logger.info(
            f"[Pipeline:Node2] Classification complete: {total} reviews | model={resp['model_used']}"
        )
        return self.context["classified"]

    # ─── NODE 3: Feature Extraction ───────────────────────────────────────────

    async def run_node3_feature_extraction(self) -> dict:
        """
        Extract specific, named feature items from review clusters.
        TIERED OUTPUT guarantee — never returns zero items:
          Tier 1: 3+ reviews, named element, full confidence
          Tier 2: Theme clear, specific element needs UX research
          Tier 3: Category has reviews but fragmented — show top quote
        """
        compressed_ctx = await self._compress_context({
            "validation":     self.context["raw"],
            "taxonomy":       self.context["taxonomy"],
            "classification": self.context["classified"],
        })
        resp = await self.orchestrator.query(
            task_type="scoring",
            system_prompt=(
                "You are a feature analyst. Extract specific, named product issues "
                "from review clusters. Return ONLY valid JSON.\n"
                + CUSTOMER_SEGMENT_CONTEXT
            ),
            user_message=f"""
CONTEXT FROM PREVIOUS ANALYSIS:
{compressed_ctx}

For each category with > 0 reviews, extract specific named feature items.

A feature item qualifies if:
- 3+ reviews mention the same specific product element, OR
- 2+ reviews contain urgency language about the same element.

Name each item as: [Verb] + [Specific Object] + [Context]
Examples:
  "Fix keyboard not appearing on password field at login"
  "Add extended time mode for users with processing difficulties"
  "Reduce API rate limit error rate during peak order sync windows"

TIERED OUTPUT (never return zero items across all tiers):
Tier 1 (Specific): 3+ reviews, named element, full confidence
Tier 2 (Directional): Theme clear, specific element needs more data
Tier 3 (Signal): Category has reviews but fragmented — show top quote

Return JSON:
{{
  "items": [
    {{
      "id": "item_001",
      "name": "specific item name",
      "category": "category name",
      "tier": 1,
      "mentionCount": number,
      "supportingReviewIds": [0, 1, 2],
      "topQuote": "best quote text under 200 chars",
      "topQuoteRating": number,
      "signalType": "urgency",
      "itemType": "bug_fix"
    }}
  ]
}}

itemType values: bug_fix | ui_change | new_feature | architecture
signalType values: urgency | churn | low-rating | expansion
""",
            options={"max_tokens": 3_500, "json_mode": True},
        )
        self.context["features"] = self._safe_parse(resp["result"], "node3")
        items = self.context["features"].get("items", [])
        logger.info(
            f"[Pipeline:Node3] Extracted {len(items)} feature items | model={resp['model_used']}"
        )
        return self.context["features"]

    # ─── NODE 4: 5-Axis Scoring ───────────────────────────────────────────────

    async def run_node4_scoring(self) -> dict:
        """Score every feature item on 5 Dispatch axes with justifications."""
        items_json = json.dumps(
            self.context["features"].get("items", []), ensure_ascii=False
        )
        classified_json = json.dumps(self.context["classified"], ensure_ascii=False)
        date_range = json.dumps(
            (self.context["raw"] or {}).get("dateRange", {}), ensure_ascii=False
        )

        resp = await self.orchestrator.query(
            task_type="scoring",
            system_prompt=(
                "You are a product prioritization engine. Score each feature item "
                "on 5 Dispatch axes. Return ONLY valid JSON.\n"
                + CUSTOMER_SEGMENT_CONTEXT
            ),
            user_message=f"""
FEATURE ITEMS TO SCORE:
{items_json[:8_000]}

CLASSIFICATION DATA:
{classified_json[:3_000]}

DATE RANGE: {date_range}

Score each item on 5 axes (0–10 each):

AXIS 1 — Pain Intensity
  Formula: (((5 - avgRating) / 4) * 10 * 0.5) + (urgencyRate * 10 * 0.3) + (churnRate * 10 * 0.2)
  Provide one-line justification citing specific numbers.

AXIS 2 — Impact Breadth
  Formula: (mentionCount / totalClassifiedReviews) * 10
  Provide one-line justification.

AXIS 3 — Urgency Velocity
  Compare mentions in first half vs second half of date range.
  Score 8-10 if increasing >20%, 4-7 if stable, 0-3 if decreasing.
  Score 5.0 [Default] if no date data available.

AXIS 4 — Strategic Leverage
  8-10: competitor names in reviews citing this item
  5-7: touches onboarding, pricing, or core workflow
  0-4: cosmetic or peripheral
  Default 5.0 [Default] if insufficient signal

AXIS 5 — Effort Inverse
  bug_fix → 8 | ui_change → 6 | new_feature → 3 | architecture → 1

FINAL SCORE = (Pain*0.30) + (Breadth*0.25) + (Velocity*0.20) + (Strategic*0.15) + (Effort*0.10)
NORMALIZED = FinalScore / 10

TIMELINE:
  Normalized >= 0.80 → Q1 – Ship Now
  0.60–0.79 → Q2 – Next Quarter
  0.40–0.59 → Q3 – Mid-term
  < 0.40 → Q4 / Backlog

Return JSON:
{{
  "scoredItems": [
    {{
      "id": "item_001",
      "name": "item name",
      "category": "category",
      "scores": {{
        "pain":      {{"value": 0.0, "justification": "..."}},
        "breadth":   {{"value": 0.0, "justification": "..."}},
        "velocity":  {{"value": 0.0, "justification": "..."}},
        "strategic": {{"value": 0.0, "justification": "...", "isDefault": false}},
        "effort":    {{"value": 0.0, "itemType": "bug_fix"}}
      }},
      "finalScore": 0.0,
      "normalizedScore": 0.0,
      "timeline": "Q1 – Ship Now",
      "confidence": "High",
      "tier": 1
    }}
  ]
}}
""",
            options={"max_tokens": 5_000, "json_mode": True},
        )
        self.context["scored"] = self._safe_parse(resp["result"], "node4")
        scored = self.context["scored"].get("scoredItems", [])
        logger.info(
            f"[Pipeline:Node4] Scored {len(scored)} items | model={resp['model_used']}"
        )
        return self.context["scored"]

    # ─── NODE 5: Financial Model ───────────────────────────────────────────────

    async def run_node5_financial(self) -> dict:
        """Compute Revenue at Risk, Cost of Inaction, and ROI per item."""
        total_users  = self.business_inputs.get("total_users")
        monthly_arpu = self.business_inputs.get("monthly_arpu")
        sprint_cost  = self.business_inputs.get("sprint_cost")

        if not total_users or not monthly_arpu:
            self.context["financial"] = {
                "status": "LOCKED",
                "reason": "Business inputs (total_users, monthly_arpu) required for financial model.",
                "items": [],
            }
            logger.info("[Pipeline:Node5] Financial model skipped — missing business inputs")
            return self.context["financial"]

        top_items_json = json.dumps(
            self.context["scored"].get("scoredItems", [])[:10], ensure_ascii=False
        )
        raw = self.context["raw"] or {}

        resp = await self.orchestrator.query(
            task_type="financial_model",
            system_prompt=(
                "You are a financial analyst. Compute revenue impact for each "
                "roadmap item. Return ONLY valid JSON.\n"
                + CUSTOMER_SEGMENT_CONTEXT
            ),
            user_message=f"""
TOP SCORED ITEMS:
{top_items_json[:6_000]}

BUSINESS INPUTS:
  Total Active Users: {total_users}
  Monthly ARPU: ${monthly_arpu}
  Sprint Cost: {f'${sprint_cost}' if sprint_cost else 'Not provided'}

VALIDATION DATA:
  Total Reviews: {raw.get('totalReviews', 0)}
  Churn Signal Reviews: {raw.get('churnSignalCount', 0)}

For each item compute:

A. Revenue at Risk:
   churnRateProxy = item.churnSignalCount / totalReviews
   revenueAtRisk  = churnRateProxy * totalUsers * monthlyARPU * 12
   Show formula with substituted values.

B. Cost of Inaction (3/6/12 months):
   monthlyRate = (item.velocityScore / 10) * 0.005
   costN       = revenueAtRisk * (1 + monthlyRate)^N

C. Revenue Opportunity:
   opportunityRate  = item.expansionSignalCount / totalReviews
   opportunity      = opportunityRate * totalUsers * monthlyARPU * 12

D. ROI (only if sprint cost provided):
   sprints = pain >= 8 ? 1 : pain >= 5 ? 3 : 6
   roi     = (revenueAtRisk + opportunity) / (sprintCost * sprints)

Return JSON:
{{
  "status": "computed",
  "items": [
    {{
      "id": "item_001",
      "revenueAtRisk": 0.0,
      "costOfInaction3mo": 0.0,
      "costOfInaction6mo": 0.0,
      "costOfInaction12mo": 0.0,
      "revenueOpportunity": 0.0,
      "roi": null,
      "formulasUsed": {{
        "revenueAtRisk": "churnRateProxy * totalUsers * monthlyARPU * 12 = ..."
      }}
    }}
  ]
}}
""",
            options={"max_tokens": 2_500, "json_mode": True},
        )
        self.context["financial"] = self._safe_parse(resp["result"], "node5")
        logger.info(
            f"[Pipeline:Node5] Financial model: "
            f"{self.context['financial'].get('status')} | model={resp['model_used']}"
        )
        return self.context["financial"]

    # ─── NODE 6: Action Cards ─────────────────────────────────────────────────

    async def run_node6_action_cards(self) -> dict:
        """Generate 5 structured action cards for the top-ranked items."""
        top5 = self.context["scored"].get("scoredItems", [])[:5]
        financial = self.context["financial"] or {}

        compressed_ctx = await self._compress_context({
            "topItems":  top5,
            "financial": financial,
        })

        resp = await self.orchestrator.query(
            task_type="action_cards",
            system_prompt=(
                "You are a product manager writing action cards for engineering teams. "
                "Be specific, measurable, and evidence-backed. Return ONLY valid JSON.\n"
                + CUSTOMER_SEGMENT_CONTEXT
            ),
            user_message=f"""
CONTEXT:
{compressed_ctx}

Write action cards for the top 5 scored items.

BANNED TEXT — never use these phrases:
- "Investigate and resolve the top issues in [Category]"
- "Done when [Category]-related negative reviews fall below 5%"
- Any generic category-level description without naming a specific element

Each card must include:
- problemStatement: one line, specific, with evidence numbers
- whoIsAffected: segment-specific (reference marketplace sellers or app developers)
- whatDataSays: exactly 3 bullet points with specific metric + [source tag]
- whatToBuild: specific deliverable with acceptance criteria
- successMetric: measurable threshold with timeframe
- riskIfIgnored: revenue at risk at 6mo + churn signal count
- suggestedOwner: Engineering | Design | Product | CS + one-phrase reason

Return JSON:
{{
  "cards": [
    {{
      "rank": 1,
      "itemId": "item_001",
      "itemName": "...",
      "timeline": "Q1 – Ship Now",
      "priorityScore": 0.0,
      "problemStatement": "...",
      "whoIsAffected": "...",
      "whatDataSays": ["bullet 1 [R]", "bullet 2 [F]", "bullet 3 [R]"],
      "whatToBuild": "...",
      "successMetric": "...",
      "riskIfIgnored": "...",
      "suggestedOwner": "Engineering — reason"
    }}
  ]
}}
""",
            options={"max_tokens": 4_000, "json_mode": True},
        )
        self.context["cards"] = self._safe_parse(resp["result"], "node6")
        cards = self.context["cards"].get("cards", [])
        logger.info(
            f"[Pipeline:Node6] Generated {len(cards)} action cards | model={resp['model_used']}"
        )
        return self.context["cards"]

    # ─── NODE 7: Strategic Plan ───────────────────────────────────────────────

    async def run_node7_strategic_plan(self) -> dict:
        """Generate 5 strategic steps and a 7-horizon time-phased action plan."""
        raw = self.context["raw"] or {}
        scored_items = self.context["scored"].get("scoredItems", [])
        financial_items = (self.context["financial"] or {}).get("items", [])

        strategic_summary = {
            "topItems": [
                {
                    "name":     i.get("name"),
                    "score":    i.get("finalScore"),
                    "timeline": i.get("timeline"),
                    "pain":     i.get("scores", {}).get("pain", {}).get("value"),
                }
                for i in scored_items[:5]
            ],
            "sentimentSplit": {
                "positive": raw.get("positiveCount", 0),
                "negative": raw.get("negativeCount", 0),
                "neutral":  raw.get("neutralCount",  0),
            },
            "topFinancialRisk": financial_items[0] if financial_items else None,
            "customerSegments": [
                "Amazon/Flipkart/Myntra marketplace sellers",
                "Google Play / App Store developers",
            ],
        }

        resp = await self.orchestrator.query(
            task_type="strategic_plan",
            system_prompt=(
                "You are a Chief Product Officer writing a strategic plan for a "
                "product intelligence platform. Be direct, specific, and segment-aware. "
                "Return ONLY valid JSON.\n"
                + CUSTOMER_SEGMENT_CONTEXT
            ),
            user_message=f"""
PRODUCT ANALYSIS SUMMARY:
{json.dumps(strategic_summary, ensure_ascii=False)}

Generate two outputs:

OUTPUT 1 — STRATEGIC STEPS (5 recommended actions)
Each step must be:
- Specific to the data findings above
- Framed for the customer segments (marketplace sellers + app developers)
- Sequenced logically (foundational steps before advanced ones)
- Include the "why" tied to a specific finding

OUTPUT 2 — TIME-PHASED ACTION PLAN
Generate milestones for: day7, day15, day30, day60, day90, day120, day365.

Each milestone:
- Is ONE specific, completable action (not "work on X" or "monitor")
- References which roadmap item it serves
- Includes a success indicator
- Is realistic for a small-to-mid product team

HORIZON GUIDANCE:
  day7   — Emergency triage — only items actively causing churn or blocking core flows
  day15  — Foundation fixes — unblock other work or reduce support tickets
  day30  — First user-visible improvement shipped (tied to a specific roadmap item)
  day60  — Velocity items — features that add competitive capability
  day90  — Measurable outcome checkpoint — state specific metric + threshold
  day120 — Strategic positioning — items differentiating in the market
  day365 — Platform vision — one sentence: what can sellers/developers do that they cannot today?

Return JSON:
{{
  "strategicSteps": [
    {{
      "stepNumber": 1,
      "title": "short title",
      "description": "2-3 sentence specific recommendation",
      "rationale": "tied to specific data finding",
      "segment": "both",
      "priority": "critical"
    }}
  ],
  "actionPlan": {{
    "day7":   {{"milestone": "specific action", "servesItem": "item name", "successIndicator": "measurable check", "owner": "Engineering"}},
    "day15":  {{"milestone": "...", "servesItem": "...", "successIndicator": "...", "owner": "..."}},
    "day30":  {{"milestone": "...", "servesItem": "...", "successIndicator": "...", "owner": "..."}},
    "day60":  {{"milestone": "...", "servesItem": "...", "successIndicator": "...", "owner": "..."}},
    "day90":  {{"milestone": "...", "servesItem": "...", "successIndicator": "...", "owner": "..."}},
    "day120": {{"milestone": "...", "servesItem": "...", "successIndicator": "...", "owner": "..."}},
    "day365": {{"milestone": "...", "servesItem": "...", "successIndicator": "...", "owner": "..."}}
  }}
}}
""",
            options={"max_tokens": 3_500, "json_mode": True},
        )
        self.context["strategy"] = self._safe_parse(resp["result"], "node7")
        steps = self.context["strategy"].get("strategicSteps", [])
        logger.info(
            f"[Pipeline:Node7] Strategic plan: {len(steps)} steps | model={resp['model_used']}"
        )
        return self.context["strategy"]

    # ─── MASTER RUNNER ────────────────────────────────────────────────────────

    async def run(self) -> dict:
        """
        Execute all 8 nodes sequentially and return the complete context store.
        Each node output is available in self.context after this call.
        """
        logger.info("[Pipeline] Starting V9 pipeline run")
        nodes = [
            ("Node 0: Validation",         self.run_node0_validation),
            ("Node 1: Taxonomy",           self.run_node1_taxonomy),
            ("Node 2: Classification",     self.run_node2_classification),
            ("Node 3: Feature Extraction", self.run_node3_feature_extraction),
            ("Node 4: 5-Axis Scoring",     self.run_node4_scoring),
            ("Node 5: Financial Model",    self.run_node5_financial),
            ("Node 6: Action Cards",       self.run_node6_action_cards),
            ("Node 7: Strategic Plan",     self.run_node7_strategic_plan),
        ]
        for name, fn in nodes:
            logger.info(f"[Pipeline] Running {name}")
            await fn()
            logger.info(f"[Pipeline] {name} complete")

        logger.info(
            f"[Pipeline] Complete. Model selection log: "
            f"{self.orchestrator.selector.selection_log}"
        )
        return self.context

    async def run_streaming(self) -> AsyncGenerator[dict, None]:
        """
        Execute all 8 nodes and yield a progress event after each completes.
        Each yielded dict has:
          {"node": int, "label": str, "status": "complete"|"error", "data": dict}
        On completion, yields a final event with status "done" and full context.
        """
        nodes = [
            ("Node 0: Validation",         self.run_node0_validation),
            ("Node 1: Taxonomy",           self.run_node1_taxonomy),
            ("Node 2: Classification",     self.run_node2_classification),
            ("Node 3: Feature Extraction", self.run_node3_feature_extraction),
            ("Node 4: 5-Axis Scoring",     self.run_node4_scoring),
            ("Node 5: Financial Model",    self.run_node5_financial),
            ("Node 6: Action Cards",       self.run_node6_action_cards),
            ("Node 7: Strategic Plan",     self.run_node7_strategic_plan),
        ]
        for idx, (label, fn) in enumerate(nodes):
            try:
                result = await fn()
                yield {"node": idx, "label": label, "status": "complete", "data": result}
            except Exception as exc:
                logger.error(f"[Pipeline] {label} failed: {exc}", exc_info=True)
                yield {
                    "node": idx,
                    "label": label,
                    "status": "error",
                    "error": str(exc),
                    "data": {},
                }
                # Continue pipeline — degraded output is better than total failure

        yield {"node": 8, "label": "Pipeline Complete", "status": "done", "context": self.context}
