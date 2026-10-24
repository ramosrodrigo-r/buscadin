import pytest

from buscadin_bot.services.publication_policy import (
    PublicationRejected,
    preview_fingerprint,
    require_publishable_job,
    validate_destination,
)


def test_referral_url_is_preserved_byte_for_byte() -> None:
    url = "https://jobs.example/apply?ref=a%2Fb&campaign=br%20video#details"
    assert validate_destination(url, ["JOBS.EXAMPLE"]) == url


@pytest.mark.parametrize("url,domains", [
    ("http://jobs.example/apply", ["jobs.example"]),
    ("javascript:alert(1)", ["jobs.example"]),
    ("//jobs.example/apply", ["jobs.example"]),
    ("https://jobs.example/apply", []),
    ("https://jobs.example.evil.example/apply", ["jobs.example"]),
    ("https://tenant.jobs.example/apply", ["jobs.example"]),
    ("https://jobs.example@evil.example/apply", ["evil.example"]),
    ("https://jobs.example:8443/apply", ["jobs.example"]),
    ("https://jobs.example:bad/apply", ["jobs.example"]),
    ("https://jobs.example./apply", ["jobs.example"]),
    ("https://127.0.0.1/apply", ["127.0.0.1"]),
    ("https://[::1]/apply", ["::1"]),
    ("https://localhost/apply", ["localhost"]),
    ("https://jobs.internal/apply", ["jobs.internal"]),
    ("https://jobs.example/apply%0d%0aLocation:evil", ["jobs.example"]),
    ("https://jobs.example\\@evil.example/apply", ["evil.example"]),
    (" https://jobs.example/apply", ["jobs.example"]),
])
def test_unsafe_or_unapproved_destinations_are_rejected(url: str, domains: list[str]) -> None:
    with pytest.raises(PublicationRejected):
        validate_destination(url, domains)


@pytest.mark.parametrize("eligibility", ["confirmed_br", "unknown"])
def test_brazil_eligible_or_explicitly_unknown_can_reach_preview(eligibility: str) -> None:
    require_publishable_job(status="active", eligibility=eligibility)


@pytest.mark.parametrize("status,eligibility", [
    ("inactive", "confirmed_br"),
    ("stale", "confirmed_br"),
    ("active", "excluded_br"),
    ("active", "unexpected"),
])
def test_inactive_or_incompatible_jobs_cannot_publish(status: str, eligibility: str) -> None:
    with pytest.raises(PublicationRejected):
        require_publishable_job(status=status, eligibility=eligibility)


def test_preview_digest_changes_when_destination_or_content_changes() -> None:
    approved = {"title": "Video annotator", "destination": "https://jobs.example/a", "version": 1}
    assert preview_fingerprint(approved) == preview_fingerprint(dict(reversed(list(approved.items()))))
    for change in ({"title": "Another role"}, {"destination": "https://jobs.example/b"}, {"version": 2}):
        assert preview_fingerprint(approved) != preview_fingerprint(approved | change)
