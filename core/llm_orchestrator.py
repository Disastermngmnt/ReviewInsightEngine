"""
LLM Orchestrator — ReviewInsightEngine Dispatch V9
====================================================
Provides ModelSelector (picks best available model per task type)
and LLMOrchestrator (executes query with automatic silent fallback).

Supported providers (used only if their API key is present in .env):
  - Google Gemini    (GOOGLE_GEMINI_API_KEY)
  - OpenAI           (OPENAI_API_KEY)
  - Groq             (GROQ_API_KEY)
  - Anthropic Claude (ANTHROPIC_API_KEY)

Usage:
    orchestrator = LLMOrchestrator()
    result = await orchestrator.query(
        task_type='classification',
        system_prompt='...',
        user_message='...',
        options={'maxTokens': 1000, 'json_mode': True}
    )
"""

import json
import os
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ─── STEP 1: CAPABILITY REGISTRY ────────────────────────────────────────────
# Each model is registered with: provider, env key, strengths, context window,
# cost tier, and a base priority score used when no task-specific adjustment applies.
MODEL_REGISTRY = {
    "gemini-1.5-pro": {
        "provider": "google",
        "env_key": "GOOGLE_GEMINI_API_KEY",
        "strengths": ["long_context", "structured_output", "reasoning"],
        "context_window": 1_000_000,
        "cost_tier": "high",
        "priority_score": 85,
    },
    "gemini-1.5-flash": {
        "provider": "google",
        "env_key": "GOOGLE_GEMINI_API_KEY",
        "strengths": ["speed", "classification", "structured_output"],
        "context_window": 100_000,
        "cost_tier": "low",
        "priority_score": 72,
    },
    "gemini-2.0-flash": {
        "provider": "google",
        "env_key": "GOOGLE_GEMINI_API_KEY",
        "strengths": ["speed", "classification", "structured_output"],
        "context_window": 500_000,
        "cost_tier": "low",
        "priority_score": 80,
    },
    "gpt-4o": {
        "provider": "openai",
        "env_key": "OPENAI_API_KEY",
        "strengths": ["reasoning", "structured_output", "instruction_following"],
        "context_window": 128_000,
        "cost_tier": "medium",
        "priority_score": 80,
    },
    "gpt-4o-mini": {
        "provider": "openai",
        "env_key": "OPENAI_API_KEY",
        "strengths": ["speed", "classification", "cost_efficiency"],
        "context_window": 128_000,
        "cost_tier": "very_low",
        "priority_score": 65,
    },
    "llama-3.3-70b-versatile": {
        "provider": "groq",
        "env_key": "GROQ_API_KEY",
        "strengths": ["speed", "classification", "cost_efficiency"],
        "context_window": 128_000,
        "cost_tier": "very_low",
        "priority_score": 60,
    },
    "claude-sonnet-4-5": {
        "provider": "anthropic",
        "env_key": "ANTHROPIC_API_KEY",
        "strengths": ["instruction_following", "reasoning", "structured_output"],
        "context_window": 200_000,
        "cost_tier": "medium",
        "priority_score": 88,
    },
}

# ─── STEP 2: TASK PROFILE DEFINITIONS ────────────────────────────────────────
# Each pipeline node maps to a task profile describing what strengths it needs,
# whether to prefer lower-cost models, and the minimum viable context window.
TASK_PROFILES = {
    "classification": {
        "required_strengths": ["classification", "structured_output"],
        "prefer_low_cost": True,   # High volume, simple → cheaper is fine
        "min_context_window": 50_000,
    },
    "scoring": {
        "required_strengths": ["reasoning", "structured_output"],
        "prefer_low_cost": False,  # Accuracy critical — use best available
        "min_context_window": 50_000,
    },
    "financial_model": {
        "required_strengths": ["reasoning", "instruction_following"],
        "prefer_low_cost": False,
        "min_context_window": 30_000,
    },
    "action_cards": {
        "required_strengths": ["instruction_following", "structured_output"],
        "prefer_low_cost": False,
        "min_context_window": 30_000,
    },
    "strategic_plan": {
        "required_strengths": ["reasoning", "instruction_following"],
        "prefer_low_cost": False,
        "min_context_window": 40_000,
    },
    # Used internally for context compression (cheap is fine)
    "compression": {
        "required_strengths": ["classification"],
        "prefer_low_cost": True,
        "min_context_window": 10_000,
    },
}

# Cost tier bonuses/penalties applied when scoring a candidate for a task
_COST_BONUS_LOW_COST  = {"very_low": 20, "low": 15, "medium": 5, "high": 0}
_COST_BONUS_HIGH_QUAL = {"very_low": 0,  "low": 5,  "medium": 10, "high": 5}


class ModelSelector:
    """
    Reads available API keys from the environment and builds a prioritised
    list of models for each task type.
    """

    def __init__(self):
        self.available_models = self._detect_available_models()
        self.selection_log: list[dict] = []
        logger.info(
            f"[ModelSelector] Available models: "
            f"{[m['model_id'] for m in self.available_models]}"
        )

    def _detect_available_models(self) -> list[dict]:
        """Return only models whose API key exists and looks valid in .env."""
        available = []
        for model_id, config in MODEL_REGISTRY.items():
            key_value = os.getenv(config["env_key"], "")
            if key_value and len(key_value) > 10:
                available.append({"model_id": model_id, **config})
        return available

    def select_for_task(self, task_type: str) -> list[dict]:
        """
        Return a prioritised list of available models for `task_type`.
        First element is the primary choice; rest are fallbacks.
        """
        profile = TASK_PROFILES.get(task_type)
        if not profile:
            raise ValueError(f"Unknown task type: {task_type!r}")

        candidates = []
        for model in self.available_models:
            # Filter: minimum context window
            if model["context_window"] < profile["min_context_window"]:
                continue
            # Filter: must satisfy at least one required strength
            if not any(s in model["strengths"] for s in profile["required_strengths"]):
                continue

            # Score = base priority + strength match bonus + cost tier bonus
            strength_matches = sum(
                1 for s in profile["required_strengths"] if s in model["strengths"]
            )
            strength_score = (
                strength_matches / max(1, len(profile["required_strengths"]))
            ) * 40

            cost_table = (
                _COST_BONUS_LOW_COST if profile["prefer_low_cost"] else _COST_BONUS_HIGH_QUAL
            )
            cost_bonus = cost_table.get(model["cost_tier"], 0)

            task_score = model["priority_score"] + strength_score + cost_bonus
            candidates.append({**model, "task_score": task_score})

        candidates.sort(key=lambda m: m["task_score"], reverse=True)

        self.selection_log.append({
            "task_type": task_type,
            "selected": candidates[0]["model_id"] if candidates else "none",
            "fallbacks": [m["model_id"] for m in candidates[1:]],
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        })

        if not candidates:
            logger.warning(f"[ModelSelector] No candidates found for task: {task_type}")

        return candidates


class LLMOrchestrator:
    """
    Wraps every LLM call with automatic model selection, execution,
    and silent per-model fallback. Callers never need to know which
    model actually handled the request.
    """

    def __init__(self):
        self.selector = ModelSelector()
        self.call_log: list[dict] = []
        self._init_clients()

    def _init_clients(self):
        """Initialise SDK clients for each provider whose key is present."""
        self.clients: dict = {}

        if os.getenv("OPENAI_API_KEY"):
            try:
                from openai import AsyncOpenAI
                self.clients["openai"] = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
                logger.info("[LLMOrchestrator] OpenAI client initialised")
            except ImportError:
                logger.warning("[LLMOrchestrator] openai package not installed — skipping")

        if os.getenv("GROQ_API_KEY"):
            try:
                from groq import AsyncGroq
                self.clients["groq"] = AsyncGroq(api_key=os.getenv("GROQ_API_KEY"))
                logger.info("[LLMOrchestrator] Groq client initialised")
            except ImportError:
                logger.warning("[LLMOrchestrator] groq package not installed — skipping")

        if os.getenv("ANTHROPIC_API_KEY"):
            try:
                import anthropic
                self.clients["anthropic"] = anthropic.AsyncAnthropic(
                    api_key=os.getenv("ANTHROPIC_API_KEY")
                )
                logger.info("[LLMOrchestrator] Anthropic client initialised")
            except ImportError:
                logger.warning("[LLMOrchestrator] anthropic package not installed — skipping")

        # Gemini uses direct HTTP fetch (no SDK version conflicts)
        if os.getenv("GOOGLE_GEMINI_API_KEY"):
            self.clients["google"] = {"api_key": os.getenv("GOOGLE_GEMINI_API_KEY")}
            logger.info("[LLMOrchestrator] Google Gemini client initialised")

    async def query(
        self,
        task_type: str,
        system_prompt: str,
        user_message: str,
        options: dict | None = None,
    ) -> dict:
        """
        Execute a query for `task_type`, trying models in priority order.

        Returns:
            {"result": str, "model_used": str, "task_type": str}

        Raises:
            RuntimeError: if ALL available models fail.
        """
        options = options or {}
        model_queue = self.selector.select_for_task(task_type)

        if not model_queue:
            raise RuntimeError(
                f"No suitable models available for task '{task_type}'. "
                "Check your API keys in .env"
            )

        last_error: Exception | None = None

        for model in model_queue:
            try:
                logger.info(
                    f"[Dispatch] Trying {model['model_id']} for task: {task_type}"
                )
                result = await self._call_model(
                    model, system_prompt, user_message, options
                )
                self.call_log.append({
                    "task_type": task_type,
                    "model": model["model_id"],
                    "status": "success",
                    "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                })
                return {"result": result, "model_used": model["model_id"], "task_type": task_type}

            except Exception as exc:
                logger.warning(
                    f"[Dispatch] {model['model_id']} failed for {task_type}: {exc}"
                )
                last_error = exc
                self.call_log.append({
                    "task_type": task_type,
                    "model": model["model_id"],
                    "status": "failed",
                    "error": str(exc),
                    "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                })
                # continue to next model silently

        raise RuntimeError(
            f"All models exhausted for task '{task_type}'. "
            f"Last error: {last_error}"
        )

    async def _call_model(
        self,
        model: dict,
        system_prompt: str,
        user_message: str,
        options: dict,
    ) -> str:
        """Route to the correct provider implementation."""
        max_tokens = options.get("max_tokens", 4096)
        json_mode  = options.get("json_mode", False)

        provider = model["provider"]
        if provider == "google":
            return await self._call_gemini(model, system_prompt, user_message, max_tokens)
        elif provider == "openai":
            return await self._call_openai(model, system_prompt, user_message, max_tokens, json_mode)
        elif provider == "groq":
            return await self._call_groq(model, system_prompt, user_message, max_tokens)
        elif provider == "anthropic":
            return await self._call_claude(model, system_prompt, user_message, max_tokens)
        else:
            raise ValueError(f"Unknown provider: {provider!r}")

    async def _call_gemini(self, model, system_prompt, user_message, max_tokens):
        """Call Gemini via direct HTTP (avoids SDK conflicts)."""
        import httpx
        api_key = self.clients["google"]["api_key"]
        # Map friendly model ID to API model name
        model_id = model["model_id"]
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model_id}:generateContent?key={api_key}"
        )
        payload = {
            "system_instruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_message}]}],
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "responseMimeType": "application/json",
            },
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(url, json=payload)
        if not response.is_success:
            raise RuntimeError(f"Gemini HTTP {response.status_code}: {response.text[:300]}")
        data = response.json()
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as exc:
            raise RuntimeError(f"Unexpected Gemini response shape: {data}") from exc

    async def _call_openai(self, model, system_prompt, user_message, max_tokens, json_mode):
        """Call OpenAI chat completions."""
        client = self.clients.get("openai")
        if client is None:
            raise RuntimeError("OpenAI client not initialised")
        params = {
            "model": model["model_id"],
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_message},
            ],
        }
        if json_mode:
            params["response_format"] = {"type": "json_object"}
        resp = await client.chat.completions.create(**params)
        return resp.choices[0].message.content

    async def _call_groq(self, model, system_prompt, user_message, max_tokens):
        """Call Groq chat completions."""
        client = self.clients.get("groq")
        if client is None:
            raise RuntimeError("Groq client not initialised")
        resp = await client.chat.completions.create(
            model=model["model_id"],
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_message},
            ],
        )
        return resp.choices[0].message.content

    async def _call_claude(self, model, system_prompt, user_message, max_tokens):
        """Call Anthropic Claude messages."""
        client = self.clients.get("anthropic")
        if client is None:
            raise RuntimeError("Anthropic client not initialised")
        resp = await client.messages.create(
            model=model["model_id"],
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        return resp.content[0].text
