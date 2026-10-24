import pytest

from buscadin_bot.services.requirements import JobRequirements
from buscadin_bot.telegram.site_handlers import _parse_requirements


def test_parse_requirement_message_requires_evidence_for_explicit_status():
    parsed = _parse_requirements(
        "educação: não_exigida\n"
        "evidência_educação: A fonte diz que não exige graduação.\n"
        "experiência: desconhecida\n"
        "evidência_experiência:\n"
    )
    assert isinstance(parsed, JobRequirements)
    assert parsed.education.status == "not_required"
    assert parsed.education.evidence.startswith("A fonte")
    assert parsed.experience.status == "unknown"


def test_parse_requirement_message_rejects_explicit_status_without_evidence():
    with pytest.raises(ValueError):
        _parse_requirements(
            "educacao: nao_exigida\n"
            "experiencia: desconhecida\n"
        )
