from buscadin_bot.services.classifier import classify_category, classify_eligibility
from buscadin_bot.sources.base import RawJob


def make_job(**overrides: object) -> RawJob:
    values: dict[str, object] = {
        "source": "test",
        "source_job_id": "1",
        "title": "Remote role",
        "company": "Example",
        "description": "A remote opportunity",
        "source_url": "https://example.test/job",
        "application_url": "https://example.test/apply",
    }
    values.update(overrides)
    return RawJob(**values)  # type: ignore[arg-type]


def test_category_prioritizes_annotation_signal() -> None:
    job = make_job(title="AI Data Annotation Specialist")

    assert classify_category(job) == "data_labeling"


def test_brazil_restriction_is_confirmed() -> None:
    job = make_job(location_restrictions=["Brazil"])

    status, countries, evidence = classify_eligibility(job)

    assert status == "confirmed_br"
    assert countries == ["BR"]
    assert "Brazil" in evidence


def test_latam_without_explicit_brazil_remains_unknown() -> None:
    job = make_job(location_restrictions=["LATAM"])

    status, _, _ = classify_eligibility(job)

    assert status == "unknown"


def test_us_only_is_excluded() -> None:
    job = make_job(location_restrictions=["United States"])

    status, _, evidence = classify_eligibility(job)

    assert status == "excluded_br"
    assert "without Brazil" in evidence


def test_salary_is_not_invented_by_raw_payload() -> None:
    job = make_job()

    assert job.min_salary is None
    assert job.max_salary is None


def test_company_presence_in_brazil_does_not_confirm_eligibility() -> None:
    job = make_job(description="Our company has offices in Brazil and Germany.")
    assert classify_eligibility(job)[0] == "unknown"


def test_brazil_mention_does_not_override_us_restriction() -> None:
    job = make_job(location_restrictions=["United States"], description="Help our customers in Brazil.")
    assert classify_eligibility(job)[0] == "excluded_br"


def test_explicit_exclusion_overrides_conflicting_structured_brazil() -> None:
    job = make_job(location_restrictions=["Brazil"], description="Not available in Brazil.")
    assert classify_eligibility(job)[0] == "excluded_br"


def test_worldwide_except_brazil_is_excluded() -> None:
    job = make_job(location_restrictions=["Worldwide"], description="Remote worldwide except Brazil.")
    assert classify_eligibility(job)[0] == "excluded_br"


def test_portuguese_exclusion_is_respected() -> None:
    job = make_job(description="Vaga indisponível no Brasil.")
    assert classify_eligibility(job)[0] == "excluded_br"


def test_confirmed_brazil_preserves_other_source_countries() -> None:
    job = make_job(location_restrictions=["Brazil", "Portugal"])
    status, countries, _ = classify_eligibility(job)
    assert status == "confirmed_br"
    assert countries == ["BR", "PORTUGAL"]
