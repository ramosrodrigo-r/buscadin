import pytest
from pydantic import ValidationError

from buscadin_bot.services.requirements import JobRequirements, language_codes
from buscadin_bot.services.normalizer import normalize_raw_job
from buscadin_bot.sources.base import RawJob


def test_absence_is_unknown_for_each_requirement():
    facts = JobRequirements()
    assert facts.public_statuses() == {"education": "unknown", "experience": "unknown"}


@pytest.mark.parametrize("status", ["required", "not_required"])
def test_claims_require_explicit_evidence(status):
    with pytest.raises(ValidationError):
        JobRequirements.model_validate({"education": {"status": status}})
    facts = JobRequirements.model_validate({"education": {"status": status, "evidence": "Explicit source statement"}})
    assert facts.education.status == status


def test_language_normalization_does_not_infer_portuguese_from_brazil():
    assert language_codes([]) == []
    assert language_codes(["Português", "English", "pt-BR"]) == ["en", "pt"]
    raw = RawJob(source="test", source_job_id="1", title="Video annotator no Brasil",
                 company="Example", description="Anotação de vídeos em português",
                 source_url="https://jobs.example/1", application_url="https://jobs.example/1")
    normalized = normalize_raw_job(raw, category="data_labeling", eligibility=("unknown", [], "unknown"))
    assert normalized.requirements["education"]["status"] == "unknown"
    assert normalized.language_requirements == []
