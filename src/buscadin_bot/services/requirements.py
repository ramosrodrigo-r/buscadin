"""Explicit requirement facts: missing information is never a waiver."""

from typing import Literal
import re

from pydantic import BaseModel, ConfigDict, Field, model_validator


class RequirementFact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["unknown", "required", "not_required"] = "unknown"
    evidence: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def require_evidence(self):
        if self.status != "unknown" and not (self.evidence and self.evidence.strip()):
            raise ValueError("Requisito ou dispensa precisa de evidência explícita")
        if self.status == "unknown":
            self.evidence = None
        return self


class JobRequirements(BaseModel):
    model_config = ConfigDict(extra="forbid")
    education: RequirementFact = Field(default_factory=RequirementFact)
    experience: RequirementFact = Field(default_factory=RequirementFact)

    def public_statuses(self) -> dict[str, str]:
        return {"education": self.education.status, "experience": self.experience.status}


def normalize_search(value: str) -> str:
    import unicodedata
    return " ".join("".join(
        character for character in unicodedata.normalize("NFKD", value.casefold())
        if not unicodedata.combining(character)
    ).split())


LANGUAGE_CODES = {
    "portugues": "pt", "portuguese": "pt", "pt": "pt", "pt-br": "pt",
    "ingles": "en", "english": "en", "en": "en",
    "espanhol": "es", "spanish": "es", "es": "es",
    "frances": "fr", "french": "fr", "fr": "fr",
    "alemao": "de", "german": "de", "de": "de",
}


def language_codes(languages: list[str]) -> list[str]:
    """Normalize only supplied language requirements; never infer from locale."""
    return sorted({LANGUAGE_CODES[value] for item in languages if (value := normalize_search(item)) in LANGUAGE_CODES})


def job_slug(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", normalize_search(title)).strip("-")[:120].rstrip("-") or "vaga"
