import json

import pytest
from sqlalchemy.ext.asyncio import create_async_engine

from buscadin_bot.db.models import Job
from buscadin_bot.db.session import create_session_factory, init_db
from buscadin_bot.services.catalogue import PublicCatalogue
from buscadin_bot.services.site_publications import SitePublicationService
from buscadin_bot.web.server import PortalApplication


@pytest.fixture
async def app(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'web.db'}")
    await init_db(engine)
    sessions = create_session_factory(engine)
    async with sessions.begin() as session:
        session.add(Job(
            id=1, source="test", source_job_id="1", title="Video annotator",
            company="Example", description="Private source description",
            source_url="https://source.example/1", application_url="https://jobs.example/1",
            category="data_labeling", eligibility_status="confirmed_br", eligible_countries=["BR"],
        ))
    publications = SitePublicationService(sessions, admin_actor="77", official_domains=["jobs.example"])
    catalogue = PublicCatalogue(sessions, publications)
    portal = PortalApplication(catalogue, publications, internal_token="internal-test")
    yield portal, publications
    await engine.dispose()


async def test_public_routes_and_security_headers(app):
    portal, _ = app
    health = await portal.handle("GET", "/healthz")
    assert health.status == 200
    assert json.loads(health.body) == {"status": "ok"}
    page = await portal.handle("GET", "/vagas")
    assert page.status == 200
    assert "Explore as vagas" in page.body.decode()
    static = await portal.handle("GET", "/static/../server.py")
    assert static.status == 404
    assert (await portal.handle("GET", "/privacidade")).status == 200
    assert (await portal.handle("GET", "/termos")).status == 200


async def test_private_api_requires_token_and_publishes_only_after_confirmation(app):
    portal, _ = app
    unauthorized = await portal.handle("GET", "/internal/jobs/1/publication")
    assert unauthorized.status == 401
    headers = {"Authorization": "Bearer internal-test", "X-Telegram-Actor": "77"}
    pending = await portal.handle("GET", "/internal/jobs/1/publication", headers=headers)
    assert json.loads(pending.body)["status"] == "NAO_PUBLICADA"
    requirements = await portal.handle(
        "POST", "/internal/jobs/1/requirements", headers=headers,
        body=json.dumps({"requirements": {
            "education": {"status": "not_required", "evidence": "Fonte explícita"},
            "experience": {"status": "unknown"},
        }}).encode(),
    )
    assert requirements.status == 200
    assert json.loads(requirements.body)["requirements"]["education"] == "not_required"
    preview = await portal.handle(
        "POST", "/internal/jobs/1/publication-preview", headers=headers,
        body=json.dumps({"destination_type": "OFFICIAL", "summary": "Resumo aprovado"}).encode(),
    )
    assert preview.status == 200
    payload = json.loads(preview.body)
    assert payload["public"]["title"] == "Video annotator"
    assert (await portal.handle("GET", "/vagas/1")).status == 404
    confirmed = await portal.handle(
        "POST", f"/internal/site-previews/{payload['token']}/confirm",
        headers=headers, body=b"{}",
    )
    assert confirmed.status == 200
    assert json.loads(confirmed.body)["status"] == "PUBLICADA"
    listing = await portal.handle("GET", "/internal/jobs?site_status=PUBLICADA&page=1", headers=headers)
    assert listing.status == 200
    assert json.loads(listing.body)["items"][0]["job_id"] == 1
    detail = await portal.handle("GET", "/vagas/video-annotator-1")
    assert detail.status == 200
    redirect = await portal.handle("GET", "/go/1")
    assert redirect.status == 303
    assert redirect.headers["Location"] == "https://jobs.example/1"


async def test_private_api_rejects_wrong_actor_and_sitemap_contains_only_approved(app):
    portal, _ = app
    headers = {"Authorization": "Bearer internal-test", "X-Telegram-Actor": "attacker"}
    denied = await portal.handle("GET", "/internal/jobs/1/publication", headers=headers)
    assert denied.status == 422
    sitemap = await portal.handle("GET", "/sitemap.xml")
    assert sitemap.status == 200
    assert "<url>" not in sitemap.body.decode()
