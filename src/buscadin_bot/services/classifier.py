"""Deterministic category and Brazil eligibility heuristics."""

import re
from collections.abc import Iterable

from buscadin_bot.sources.base import RawJob

BRAZIL_ALIASES = {"br", "brazil", "brasil", "republic of brazil"}
UNKNOWN_REGIONS = {"latam", "latin america", "global", "worldwide", "anywhere", "remote"}
EXCLUSION_PATTERNS = (
    r"\bnot available in brazil\b",
    r"\bunavailable in brazil\b",
    r"\bbrazil (?:is )?excluded\b",
    r"\b(?:us|u\.s\.|united states) only\b",
    r"\bmust be located in (?:the )?(?:us|u\.s\.|united states)\b",
)

CATEGORY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("data_labeling", ("data label", "data annot", "annotation", "annotator")),
    ("ai_training", ("ai training", "model training", "rlhf", "reinforcement learning")),
    ("ai_evaluation", ("ai evaluator", "model evaluator", "ai evaluation", "quality rater")),
    ("search_quality", ("search quality", "search evaluator", "search relevance")),
    ("qa", ("quality assurance", "qa engineer", "test engineer", "software tester")),
    ("development", ("software engineer", "developer", "backend", "frontend", "full stack")),
)


def classify_category(raw: RawJob) -> str:
    text = " ".join([raw.title, raw.description, *raw.categories]).lower()
    for category, keywords in CATEGORY_RULES:
        if any(keyword in text for keyword in keywords):
            return category
    return "other"


def classify_eligibility(raw: RawJob) -> tuple[str, list[str], str]:
    """Return status, normalized countries and the evidence used.

    LATAM/global language remains ``unknown``; only explicit Brazil acceptance is
    ``confirmed_br``. A bounded non-Brazil country list is exclusionary.
    """

    restrictions = [item.strip() for item in raw.location_restrictions if item.strip()]
    normalized = [normalize_country(item) for item in restrictions]
    restriction_text = " ".join(restrictions).lower()
    description = raw.description.lower()
    combined = f"{restriction_text} {description}"

    if any(country == "BR" for country in normalized) or _mentions_brazil_positively(description):
        evidence = _evidence("Brazil explicitly accepted", restrictions, description)
        return "confirmed_br", ["BR"], evidence

    if any(re.search(pattern, combined) for pattern in EXCLUSION_PATTERNS):
        return "excluded_br", normalized, _evidence("Brazil excluded by source text", restrictions, description)

    if restrictions and not any(country.lower() in UNKNOWN_REGIONS for country in normalized):
        return "excluded_br", normalized, _evidence("Source lists countries without Brazil", restrictions, description)

    return "unknown", normalized, _evidence("Brazil eligibility not explicitly confirmed", restrictions, description)


def normalize_country(value: str) -> str:
    compact = re.sub(r"\s+", " ", value.strip().lower())
    if compact in BRAZIL_ALIASES:
        return "BR"
    return compact.upper()


def _mentions_brazil_positively(description: str) -> bool:
    if not re.search(r"\b(?:brazil|brasil)\b", description):
        return False
    return not any(re.search(pattern, description) for pattern in EXCLUSION_PATTERNS)


def _evidence(reason: str, restrictions: Iterable[str], description: str) -> str:
    evidence_parts = [reason]
    if restrictions:
        evidence_parts.append(f"restrictions={', '.join(restrictions)}")
    if "brazil" in description or "brasil" in description:
        evidence_parts.append("description mentions Brazil/ Brasil")
    return "; ".join(evidence_parts)
