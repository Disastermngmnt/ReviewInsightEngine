"""
Taxonomy Adaptation Gate — ReviewInsightEngine
================================================
Checks whether the default taxonomy covers the uploaded reviews adequately.

Algorithm (Dispatch v3.0 spec):
  1. Sample first N reviews (default: 50 or TAXONOMY_GATE_SAMPLE_SIZE).
  2. For each sampled review, check if it contains ≥ 1 keyword from any
     non-Other default taxonomy category.
  3. coverage = matched_reviews / total_sampled
  4. If coverage ≥ TAXONOMY_COVERAGE_THRESHOLD (0.70): gate PASSES — use default.
  5. If coverage < threshold: gate FAILS — propose custom taxonomy via AI.

Returns:
  {
    "passes": bool,
    "coverage": float (0.0–1.0),
    "matched_count": int,
    "total_sampled": int,
    "threshold": 0.70,
    "sample_texts": list[str]   # only populated on FAIL (for AI prompt)
  }
"""

from __future__ import annotations
from config.settings import (
    TAXONOMY,
    TAXONOMY_COVERAGE_THRESHOLD,
    TAXONOMY_GATE_SAMPLE_SIZE,
)


def _normalise(text: str) -> str:
    """Lowercase + collapse whitespace."""
    return " ".join(str(text).lower().split())


def check_coverage(
    review_texts: list[str],
    taxonomy: dict | None = None,
    sample_size: int | None = None,
) -> dict:
    """
    Run the taxonomy gate coverage check.

    Args:
        review_texts: Raw review strings (already extracted from uploaded data).
        taxonomy:     Taxonomy dict to check against. Defaults to TAXONOMY from settings.
        sample_size:  Max sample size. Defaults to TAXONOMY_GATE_SAMPLE_SIZE.

    Returns:
        Gate result dict.
    """
    if taxonomy is None:
        taxonomy = TAXONOMY
    if sample_size is None:
        sample_size = TAXONOMY_GATE_SAMPLE_SIZE

    # All non-Other keywords from the taxonomy, flattened into a single list.
    all_keywords: list[str] = []
    for category, keywords in taxonomy.items():
        if category != "Other":
            all_keywords.extend(kw.lower() for kw in keywords)

    # Sample: take first N reviews (or all if fewer).
    sample = [r for r in review_texts if r and str(r).strip()][:sample_size]
    total_sampled = len(sample)

    if total_sampled == 0:
        return {
            "passes": True,  # nothing to check — let it proceed
            "coverage": 1.0,
            "matched_count": 0,
            "total_sampled": 0,
            "threshold": TAXONOMY_COVERAGE_THRESHOLD,
            "sample_texts": [],
        }

    matched_count = 0
    for text in sample:
        normalised = _normalise(text)
        if any(kw in normalised for kw in all_keywords):
            matched_count += 1

    coverage = matched_count / total_sampled
    passes = coverage >= TAXONOMY_COVERAGE_THRESHOLD

    return {
        "passes": passes,
        "coverage": round(coverage, 4),
        "matched_count": matched_count,
        "total_sampled": total_sampled,
        "threshold": TAXONOMY_COVERAGE_THRESHOLD,
        # Provide sample texts only when gate fails (needed for AI taxonomy prompt).
        "sample_texts": sample if not passes else [],
    }


def build_taxonomy_from_proposal(proposal: dict) -> dict:
    """
    Convert an AI-proposed taxonomy (from AIEngine.propose_custom_taxonomy)
    into the same format as TAXONOMY in settings.py so the Analyzer can use it.

    The proposal format is:
      {
        "categories": [
          {"name": "...", "keywords": [...], ...},
          ...
        ]
      }

    Returns: dict matching TAXONOMY format, with "Other": [] appended.
    """
    custom_taxonomy: dict[str, list[str]] = {}
    for category in proposal.get("categories", []):
        name = category.get("name", "Unknown")
        keywords = [kw.lower() for kw in category.get("keywords", [])]
        custom_taxonomy[name] = keywords
    custom_taxonomy["Other"] = []  # always append catch-all last
    return custom_taxonomy


def format_gate_result_for_frontend(gate: dict, proposal: dict | None = None) -> dict:
    """
    Build the payload returned by /api/taxonomy_check to the frontend.

    Args:
        gate:     Result from check_coverage().
        proposal: AI-proposed taxonomy (only present if gate failed).

    Returns: Frontend-ready dict.
    """
    result: dict = {
        "passes": gate["passes"],
        "coverage_pct": round(gate["coverage"] * 100, 1),
        "matched": gate["matched_count"],
        "sampled": gate["total_sampled"],
        "threshold_pct": round(gate["threshold"] * 100, 1),
        "message": (
            f"Default taxonomy matches {round(gate['coverage'] * 100, 1)}% of sampled reviews "
            f"({'✓ above' if gate['passes'] else '⚠ below'} the {round(gate['threshold']*100)}% threshold)."
        ),
    }

    if not gate["passes"] and proposal:
        # Attach the AI proposal for display in the frontend dialog.
        categories_with_examples = []
        sample_texts = gate.get("sample_texts", [])

        for cat in proposal.get("categories", []):
            example_indices = cat.get("example_indices", [])
            examples = [
                sample_texts[i] for i in example_indices
                if 0 <= i < len(sample_texts)
            ]
            categories_with_examples.append({
                "name": cat.get("name", "Unknown"),
                "description": cat.get("description", ""),
                "keywords": cat.get("keywords", []),
                "examples": examples,
            })

        result["proposal"] = {
            "top_topics": proposal.get("top_topics", []),
            "categories": categories_with_examples,
            "reasoning": proposal.get("reasoning", ""),
        }

    return result
