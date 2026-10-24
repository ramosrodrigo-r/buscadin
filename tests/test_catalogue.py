import json

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import create_async_engine

from buscadin_bot.db.models import Job, SitePublication
from buscadin_bot.db.session import create_session_factory, init_db
from buscadin_bot.services.catalogue import CatalogueFilters, PublicCatalogue
from buscadin_bot.services.site_publications import SitePublicationService


@pytest.fixture
async def catalogue(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'catalogue.db'}")
    await init_db(engine)
    sessions = create_session_factory(engine)
    async with sessions.begin() as session:
        session.add_all([
            Job(id=1, source="test", source_job_id="1", title="Video annotator", company="Estúdio Brasil",
                category="data_labeling", source_url="https://jobs.example/1", application_url="https://jobs.example/1",
                language_requirements=["Português", "English"], eligibility_status="confirmed_br", eligible_countries=["BR"],
                requirements={"education": {"status": "not_required", "evidence": "No college degree required."}}),
            Job(id=2, source="test", source_job_id="2", title="Software engineer", company="Example",
                category="development", source_url="https://jobs.example/2", application_url="https://jobs.example/2",
                eligibility_status="unknown", language_requirements=["English"], salary_disclosed=True,
                salary_min=25, salary_max=40, currency="USD", salary_period="hour",
                requirements={"experience": {"status": "required", "evidence": "At least 3 years of experience required."}}),
            Job(id=3, source="test", source_job_id="3", title="Private pending role", company="Example",
                source_url="https://jobs.example/3", application_url="https://jobs.example/3"),
        ])
    publications = SitePublicationService(sessions, admin_actor="77", official_domains=["jobs.example"])
    for job_id in (1, 2):
        prepared = await publications.preview(job_id, actor="77", destination_type="OFFICIAL", summary="Resumo revisado com descrição das atividades.")
        await publications.confirm(prepared.token, actor="77")
    yield PublicCatalogue(sessions, publications), publications, sessions
    await engine.dispose()


async def test_catalogue_only_reads_publications_with_bounded_pagination(catalogue):
    public, _, _ = catalogue
    first = await public.search(CatalogueFilters(page_size=1))
    second = await public.search(CatalogueFilters(page_size=1, page=2))
    assert first.total == second.total == 2
    assert first.items[0]["id"] == 2
    assert second.items[0]["id"] == 1
    assert first.has_next and not second.has_next
    assert await public.detail(3) is None
    assert await public.detail(999) is None


async def test_search_handles_accents_and_matches_approved_content(catalogue):
    public, _, sessions = catalogue
    async with sessions.begin() as session:
        (await session.get(Job, 1)).company = "Changed in the source"
    page = await public.search(CatalogueFilters(q="ESTUDIO VIDEO"))
    assert [item["id"] for item in page.items] == [1]
    assert page.items[0]["company"] == "Estúdio Brasil"
    assert (await public.search(CatalogueFilters(q="Changed"))).total == 0
    assert (await public.search(CatalogueFilters(q="%"))).total == 0


@pytest.mark.parametrize("filters,ids", [
    ({"category": "development"}, [2]),
    ({"language": "pt"}, [1]),
    ({"language": "en"}, [2, 1]),
    ({"country": "BR"}, [1]),
    ({"eligibility": "unknown"}, [2]),
    ({"education": "not_required"}, [1]),
    ({"education": "unknown"}, [2]),
    ({"experience": "not_required"}, []),
    ({"experience": "required"}, [2]),
    ({"salary_available": True}, [2]),
    ({"category": "data_labeling", "education": "not_required", "language": "pt"}, [1]),
])
async def test_filters_do_not_turn_unknown_requirements_into_waivers(catalogue, filters, ids):
    public, _, _ = catalogue
    assert [item["id"] for item in (await public.search(CatalogueFilters(**filters))).items] == ids


async def test_public_projection_excludes_internal_data_even_if_added_to_snapshot(catalogue):
    public, _, sessions = catalogue
    async with sessions.begin() as session:
        row = await session.get(SitePublication, 1)
        row.public_snapshot = row.public_snapshot | {"private_notes": "secret-note", "payout": 123, "approved_by": "77"}
        row.destination_snapshot = row.destination_snapshot | {"url": "https://jobs.example/1?ref=secret-ref"}
    page = await public.search()
    body = json.dumps(page.items)
    assert "secret" not in body
    assert "approved_by" not in body
    assert "payout" not in body
    assert "evidence" not in body


async def test_withdrawn_or_inactive_jobs_disappear_from_catalogue_and_sitemap(catalogue):
    public, publications, sessions = catalogue
    await publications.unpublish(1, actor="77", expected_version=1, event_id="retire-1", reason="Encerrada")
    async with sessions.begin() as session:
        (await session.get(Job, 2)).status = "inactive"
    assert (await public.search()).total == 0
    assert await public.sitemap_batch() == []
    assert await public.detail(1) is None
    assert await public.detail(2) is None


async def test_lost_brazil_evidence_is_hidden_even_before_reconciliation(catalogue):
    public, publications, sessions = catalogue
    async with sessions.begin() as session:
        (await session.get(Job, 1)).eligibility_status = "unknown"
    assert [row["id"] for row in (await public.search()).items] == [2]
    assert await public.detail(1) is None
    await publications.reconcile()
    async with sessions() as session:
        assert (await session.get(SitePublication, 1)).status == "DESPUBLICADA"


async def test_approved_title_update_preserves_public_path(catalogue):
    public, publications, sessions = catalogue
    before = await public.detail(1)
    async with sessions.begin() as session:
        (await session.get(Job, 1)).title = "New title in source"
    prepared = await publications.preview(1, actor="77", destination_type="OFFICIAL", summary="Novo resumo revisado")
    await publications.confirm(prepared.token, actor="77")
    after = await public.detail(1)
    assert after["path"] == before["path"]
    assert after["title"] == "New title in source"


@pytest.mark.parametrize("filters", [{"page_size": 1000}, {"page": 0}, {"q": "x" * 121}, {"education": "maybe"}])
def test_query_rejects_unbounded_or_invalid_filters(filters):
    with pytest.raises(ValidationError):
        CatalogueFilters(**filters)
