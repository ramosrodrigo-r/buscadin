import json
import asyncio
import time

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine

from buscadin_bot.config import Settings
from buscadin_bot.db.models import AuditEvent, Job
from buscadin_bot.db.repository import JobRepository
from buscadin_bot.db.session import create_session_factory, init_db
from buscadin_bot.services.normalizer import normalize_raw_job
from buscadin_bot.sources.base import RawJob
from buscadin_bot.web.admin import AdminApplication
from buscadin_bot.web.server import _serve_connection

PASSWORD = "a-long-test-password-for-admin"
ORIGIN = "http://127.0.0.1:8081"
DRAFT = dict(title="Video annotator", company="Example", source_url="https://jobs.example/source",
             application_url="https://jobs.example/apply", eligibility_status="confirmed_br",
             evidence="A fonte aceita residentes no Brasil", category="data_labeling")


@pytest.fixture
async def admin(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'admin.db'}")
    await init_db(engine)
    app = AdminApplication(create_session_factory(engine), Settings(site_official_domains="jobs.example"), PASSWORD)
    yield app
    await engine.dispose()


async def request(app, path, data=None, auth=None, headers=None):
    return await app.handle("GET" if data is None else "POST", path,
        headers={"Host": "127.0.0.1:8081", "Origin": ORIGIN, "Content-Type": "application/json", **(auth or {}), **(headers or {})},
        body=json.dumps(data).encode() if data is not None else b"")


async def login(app):
    response = await request(app, "/api/login", {"password": PASSWORD})
    assert response.status == 200
    return {"Cookie": response.headers["Set-Cookie"].split(";")[0], "X-CSRF-Token": json.loads(response.body)["csrf"]}


async def test_auth_origin_csrf_logout_and_expiry(admin):
    assert (await request(admin, "/api/jobs")).status == 401
    assert (await request(admin, "/api/login", {"password": PASSWORD}, headers={"Origin": "https://evil.example"})).status == 403
    assert (await request(admin, "/", headers={"Host": "evil.example"})).status == 403
    auth = await login(admin)
    assert "HttpOnly" in (await request(admin, "/api/login", {"password": PASSWORD})).headers["Set-Cookie"]
    assert (await request(admin, "/api/jobs", DRAFT, auth, {"X-CSRF-Token": "bad"})).status == 403
    page = await request(admin, "/api/jobs", auth=auth)
    assert page.status == 200 and page.headers["Cache-Control"] == "no-store"
    assert (await request(admin, "/api/logout", {}, auth)).status == 200
    assert (await request(admin, "/api/jobs", auth=auth)).status == 401
    auth = await login(admin)
    token = auth["Cookie"].split("=", 1)[1]
    admin.tokens[token] = (auth["X-CSRF-Token"], time.monotonic() - 1)
    assert (await request(admin, "/api/jobs", auth=auth)).status == 401


async def test_login_rate_limit(admin):
    for _ in range(5):
        assert (await request(admin, "/api/login", {"password": "incorrect"})).status == 401
    assert (await request(admin, "/api/login", {"password": PASSWORD})).status == 429


async def test_create_edit_preview_publish_conflict_and_withdraw(admin):
    auth = await login(admin)
    created = await request(admin, "/api/jobs", DRAFT, auth)
    assert created.status == 200, created.body
    job_id = json.loads(created.body)["id"]
    detail = json.loads((await request(admin, f"/api/jobs/{job_id}", auth=auth)).body)
    assert detail["publication"] is None
    edited = {**DRAFT, "title": "Anotação de vídeos", "revision": detail["revision"]}
    assert (await request(admin, f"/api/jobs/{job_id}", edited, auth)).status == 200
    assert (await request(admin, f"/api/jobs/{job_id}", edited, auth)).status == 409
    preview = await request(admin, f"/api/internal/jobs/{job_id}/publication-preview", {"summary": "Resumo revisado", "destination_type": "OFFICIAL"}, auth)
    assert preview.status == 200, preview.body
    token = json.loads(preview.body)["token"]
    assert (await admin.portal.handle("GET", f"/vagas/{job_id}")).status == 404
    published = await request(admin, f"/api/internal/site-previews/{token}/confirm", {}, auth)
    assert published.status == 200, published.body
    assert (await admin.portal.handle("GET", f"/vagas/{job_id}")).status == 200
    state = json.loads(published.body)
    removed = await request(admin, f"/api/internal/jobs/{job_id}/unpublish", {"expected_version": state["version"], "event_id": "admin-test-remove", "reason": "Encerrada"}, auth)
    assert removed.status == 200, removed.body
    assert (await admin.portal.handle("GET", f"/vagas/{job_id}")).status == 404
    history = json.loads((await request(admin, "/api/audit", auth=auth)).body)
    assert len(history["events"]) == 2
    assert len(history["publications"]) == 2


async def test_invalid_facts_urls_and_external_token_do_not_bypass_login(admin):
    auth = await login(admin)
    for patch in [{"evidence": ""}, {"application_url": "javascript:alert(1)"},
                  {"requirements": {"education": {"status": "not_required"}}},
                  {"salary_min": 200, "salary_max": 100}]:
        assert (await request(admin, "/api/jobs", {**DRAFT, **patch}, auth)).status == 422
    assert (await request(admin, "/api/internal/jobs", headers={"Authorization": f"Bearer {admin.portal.internal_token}"})).status == 401
    assert (await request(admin, "/assets/../admin.py")).status == 404


async def test_recollection_preserves_admin_curated_content(admin):
    auth = await login(admin)
    await request(admin, "/api/jobs", DRAFT, auth)
    async with admin.sessions.begin() as session:
        job = await session.get(Job, 1)
        raw = RawJob(source=job.source, source_job_id=job.source_job_id, title="Changed upstream", company="Other", description="", source_url=DRAFT["source_url"], application_url=DRAFT["application_url"])
        data = normalize_raw_job(raw, category="other", eligibility=("unknown", [], ""))
        updated, is_new = await JobRepository().upsert_job(session, data)
        assert not is_new
        assert updated.title == DRAFT["title"]
        assert updated.eligibility_status == "confirmed_br"


async def test_referral_permissions_domains_and_disable(admin):
    auth = await login(admin)
    program = {"company": "Example", "name": "Programa", "scope_type": "GLOBAL", "allowed_domains": ["jobs.example"], "evidence_url": "https://jobs.example/terms", "public_sharing_allowed": True}
    response = await request(admin, "/api/programs", program, auth)
    assert response.status == 200, response.body
    program_id = json.loads(response.body)["id"]
    link = {"program_id": program_id, "url": "https://evil.example/ref", "official_confirmed": True}
    assert (await request(admin, "/api/links", link, auth)).status == 422
    link["url"] = "https://jobs.example/ref"
    link["official_confirmed"] = False
    assert (await request(admin, "/api/links", link, auth)).status == 422
    link["official_confirmed"] = True
    response = await request(admin, "/api/links", link, auth)
    assert response.status == 200, response.body
    assert (await request(admin, "/api/referrals/disable", {"kind": "program", "id": program_id}, auth)).status == 200
    result = json.loads((await request(admin, "/api/referrals", auth=auth)).body)
    assert result["programs"][0]["is_active"] is False


async def test_collection_uses_existing_connector_and_records_result(admin, monkeypatch):
    async def fake_fetch(self):
        return [RawJob(source="test", source_job_id="a", title="Annotator", company="Example", description="", source_url="https://jobs.example/a", application_url="https://jobs.example/a")]
    monkeypatch.setattr("buscadin_bot.web.admin.HimalayasSource.fetch_jobs", fake_fetch)
    auth = await login(admin)
    result = await request(admin, "/api/collect", {}, auth)
    assert result.status == 200
    assert json.loads(result.body)["inserted"] == 1
    result = await request(admin, "/api/collect", {}, auth)
    assert json.loads(result.body)["inserted"] == 0
    async with admin.sessions() as session:
        events = (await session.scalars(select(AuditEvent).where(AuditEvent.event_type == "admin_collection"))).all()
        assert len(events) == 2


async def test_http_transport_handles_lowercase_and_rejects_ambiguous_lengths(admin):
    server = await asyncio.start_server(lambda r, w: _serve_connection(admin, r, w), "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    payload = json.dumps({"password": PASSWORD}).encode()
    async def exchange(extra):
        reader, writer = await asyncio.open_connection("127.0.0.1", port)
        writer.write(b"POST /api/login HTTP/1.1\r\nhost: 127.0.0.1:8081\r\norigin: http://127.0.0.1:8081\r\ncontent-type: application/json\r\n" + extra + b"\r\n" + payload)
        await writer.drain()
        response = await reader.read()
        writer.close()
        await writer.wait_closed()
        return response
    try:
        length = f"content-length: {len(payload)}\r\n".encode()
        assert (await exchange(length)).startswith(b"HTTP/1.1 200")
        assert (await exchange(length + b"Content-Length: 0\r\n")).startswith(b"HTTP/1.1 400")
        assert (await exchange(length + b"transfer-encoding: chunked\r\n")).startswith(b"HTTP/1.1 400")
    finally:
        server.close()
        await server.wait_closed()


async def test_crawl_api_is_manual_authenticated_and_insert_only(admin):
    from buscadin_bot.sources.company_crawler import CrawlReport
    class Fake:
        def __init__(self, name, known_ids=()):
            self.name = name
            self.report = CrawlReport(name, discovered=1)
        async def fetch_jobs(self):
            return [RawJob(source=self.name, source_job_id="one", title="One", company=self.name,
                           description="Description", source_url="https://jobs.example/one", application_url="https://jobs.example/one")]
    admin.crawls.factory = Fake
    assert admin.crawls.task is None
    assert (await request(admin, "/api/crawl", {"source":"all"})).status == 401
    auth = await login(admin)
    assert (await request(admin, "/api/crawl", {"source":"all"}, auth, {"X-CSRF-Token":"bad"})).status == 403
    assert (await request(admin, "/api/crawl", {"source":"unknown"}, auth)).status == 422
    assert (await request(admin, "/api/crawl", {"source":"all"}, auth)).status == 200
    assert (await request(admin, "/api/crawl", {"source":"all"}, auth)).status == 409
    await admin.crawls.task
    first = json.loads((await request(admin, "/api/crawl", auth=auth)).body)
    assert sum(row["inserted"] for row in first["results"]) == 4
    await request(admin, "/api/crawl", {"source":"all"}, auth)
    await admin.crawls.task
    second = json.loads((await request(admin, "/api/crawl", auth=auth)).body)
    assert sum(row["inserted"] for row in second["results"]) == 0
    assert sum(row["skipped"] for row in second["results"]) == 4
