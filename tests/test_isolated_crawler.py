import asyncio
from dataclasses import asdict
import json

import httpx
import pytest
from pydantic import ValidationError

from buscadin_bot.sources.base import RawJob
from buscadin_bot.sources.company_crawler import CrawlError, CrawlReport
from buscadin_bot.sources.crawl_contract import CrawlRequest
from buscadin_bot.sources.remote_company import RemoteCompanyCrawler, MAX_RESPONSE_BYTES
from buscadin_bot.services.crawl_runs import CrawlRuns
from buscadin_bot.web.crawler import CrawlerApplication


DESCRIPTION = 'Review video clips following the project guidelines. No education or experience requirement is stated.'


def payload():
    raw = RawJob(source='turing', source_job_id='116917', company='Turing',
                 title='Clinical & Health Specialist', description=DESCRIPTION,
                 source_url='https://work.turing.com/jobs?jobId=116917&search=Clinical',
                 application_url='https://work.turing.com/jobs?jobId=116917&search=Clinical')
    return {'jobs': [asdict(raw)], 'report': asdict(CrawlReport('turing', discovered=1, pages=1))}


async def test_adapter_transmits_only_bounded_crawl_inputs(monkeypatch):
    monkeypatch.setenv('ADMIN_PASSWORD', 'private-never-forward')
    monkeypatch.setenv('DATABASE_URL', 'private-never-forward')
    def handle(request):
        assert request.url.host == 'buscadin-crawler'
        assert 'private-never-forward' not in request.content.decode()
        assert 'authorization' not in request.headers
        assert json.loads(request.content) == {'source': 'turing', 'known_ids': ['already-seen'],
                                               'max_new': 30, 'max_pages': 5}
        return httpx.Response(200, json=payload())
    source = RemoteCompanyCrawler('turing', ['already-seen'], transport=httpx.MockTransport(handle))
    jobs = await source.fetch_jobs()
    assert jobs[0].source_job_id == '116917'
    assert source.report.discovered == 1


@pytest.mark.parametrize('mutation', ['host', 'identity', 'source', 'extra'])
async def test_compromised_worker_response_is_rejected(mutation):
    data = payload()
    if mutation == 'host':
        data['jobs'][0]['source_url'] = 'https://127.0.0.1/private'
    elif mutation == 'identity':
        data['jobs'][0]['source_job_id'] = '999'
    elif mutation == 'source':
        data['report']['source'] = 'mercor'
    else:
        data['jobs'][0]['command'] = 'arbitrary-command'
    source = RemoteCompanyCrawler('turing', transport=httpx.MockTransport(lambda r: httpx.Response(200, json=data)))
    with pytest.raises(CrawlError):
        await source.fetch_jobs()


async def test_worker_redirect_and_oversized_response_are_rejected():
    calls = []
    def redirect(request):
        calls.append(str(request.url))
        return httpx.Response(303, headers={'Location': 'http://127.0.0.1/private'})
    with pytest.raises(CrawlError):
        await RemoteCompanyCrawler('turing', transport=httpx.MockTransport(redirect)).fetch_jobs()
    assert len(calls) == 1
    transport = httpx.MockTransport(lambda r: httpx.Response(200, headers={"Content-Type": "application/json"}, content=b'x' * (MAX_RESPONSE_BYTES + 1)))
    with pytest.raises(CrawlError):
        await RemoteCompanyCrawler('turing', transport=transport).fetch_jobs()


async def test_unavailable_worker_has_no_local_browser_fallback(monkeypatch):
    from buscadin_bot.sources.company_crawler import CompanyCrawler
    async def forbidden(*args):
        raise AssertionError('Admin attempted to launch browser')
    monkeypatch.setattr(CompanyCrawler, 'fetch_jobs', forbidden)
    def unavailable(request):
        raise httpx.ConnectError('offline', request=request)
    with pytest.raises(CrawlError):
        await RemoteCompanyCrawler('turing', transport=httpx.MockTransport(unavailable)).fetch_jobs()
    assert CrawlRuns(None).factory is RemoteCompanyCrawler


@pytest.mark.parametrize('extra', [{'url': 'https://127.0.0.1'}, {'command': 'id'}, {'max_new': 1000}, {'max_pages': 0}])
async def test_worker_rejects_arbitrary_targets_commands_and_limits(extra):
    app = CrawlerApplication()
    response = await app.handle('POST', '/crawl', headers={'content-type': 'application/json'},
                                body=json.dumps({'source': 'turing', **extra}).encode())
    assert response.status == 422


async def test_only_one_browser_crawl_is_admitted():
    entered, release = asyncio.Event(), asyncio.Event()
    class Fake:
        def __init__(self, name, **kwargs):
            self.report = CrawlReport(name)
        async def fetch_jobs(self):
            entered.set()
            await release.wait()
            return []
    app = CrawlerApplication(factory=Fake)
    async def invoke():
        return await app.handle('POST', '/crawl', headers={'content-type': 'application/json'},
                                body=b'{"source":"turing"}')
    first = asyncio.create_task(invoke())
    await entered.wait()
    try:
        assert (await invoke()).status == 409
    finally:
        release.set()
    assert (await first).status == 200


def test_worker_startup_rejects_application_credentials(monkeypatch):
    from buscadin_bot.web.crawler import require_credential_free_environment
    monkeypatch.setenv('DATABASE_URL', 'must-not-be-here')
    with pytest.raises(RuntimeError, match='credentials'):
        require_credential_free_environment()


async def test_worker_rejects_credentialed_urls():
    data = payload()
    data['jobs'][0]['source_url'] = 'https://:password@work.turing.com/jobs?jobId=116917'
    with pytest.raises(CrawlError):
        await RemoteCompanyCrawler('turing', transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json=data))).fetch_jobs()


async def test_compressed_worker_response_is_rejected_before_reading():
    class ForbiddenRead(httpx.AsyncByteStream):
        async def __aiter__(self):
            raise AssertionError('Compressed response must not be read')
            yield b''
    transport = httpx.MockTransport(lambda r: httpx.Response(200,
        headers={'Content-Type': 'application/json', 'Content-Encoding': 'gzip'},
        stream=ForbiddenRead()))
    with pytest.raises(CrawlError, match='comprimida'):
        await RemoteCompanyCrawler('turing', transport=transport).fetch_jobs()


async def test_worker_does_not_listen_when_sandbox_probe_fails(monkeypatch):
    from buscadin_bot.web import crawler
    monkeypatch.setattr(crawler, 'require_credential_free_environment', lambda: None)
    async def fail():
        raise RuntimeError('Sandbox missing')
    async def forbidden(*args, **kwargs):
        raise AssertionError('RPC must not start without a verified sandbox')
    monkeypatch.setattr(crawler, 'verify_browser_sandbox', fail)
    monkeypatch.setattr(crawler, 'serve', forbidden)
    with pytest.raises(RuntimeError, match='Sandbox missing'):
        await crawler.run()
