import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine

from buscadin_bot.db.models import Job
from buscadin_bot.db.session import create_session_factory, init_db
from buscadin_bot.services.classifier import classify_eligibility
from buscadin_bot.services.crawl_runs import CrawlRuns
from buscadin_bot.sources.company_crawler import (CompanyCrawler, CrawlError, CrawlReport,
    job_identity, parse_detail, mercor_public_links, mercor_listing_response, mercor_embedded_links)
from buscadin_bot.sources.base import RawJob

MICRO = 'https://jobs.micro1.ai/post/5ed081d3-01aa-4840-9ac6-c75a61993136'
ALIGN = 'https://www.alignerr.com/jobs/62eb97fa-c5aa-4af4-8d71-2ebb8f7e1077'
DESCRIPTION = 'Review and label video clips following the project guidelines. The source does not state education requirements.'


def test_mercor_public_batch_filters_private_closed_and_deduplicates():
    public = {'listingId': 'list_abc', 'isPrivate': False, 'status': 'active',
              'url': 'http://127.0.0.1/private'}
    links = mercor_public_links({'listings': [public, public,
        {**public, 'listingId': 'list_private', 'isPrivate': True},
        {**public, 'listingId': 'list_closed', 'status': 'closed'},
        {'listingId': 'list_unknown', 'status': 'active'}]})
    assert links == ['https://work.mercor.com/jobs/list_abc']
    crawler = CompanyCrawler('mercor', known_ids={'list_abc'})
    assert not crawler.accept(links[0])
    assert crawler.report.skipped == 1
    assert not crawler.accept(links[0])
    assert crawler.report.skipped == 1


def test_mercor_reads_public_initial_query_cache_without_cards():
    payload = {'props': {'pageProps': {'dehydratedState': {'queries': [
        {'queryKey': ['listings-explore-page', 'listingsPublicQuery'],
         'state': {'data': {'listings': [{'listingId': 'list_abc', 'isPrivate': False, 'status': 'active'}]}}}
    ]}}}}
    html = '<script id="__NEXT_DATA__">' + json.dumps(payload) + '</script>'
    assert mercor_embedded_links(html) == ['https://work.mercor.com/jobs/list_abc']
    assert mercor_embedded_links('<html>Loading</html>') is None


@pytest.mark.parametrize('payload', [{}, {'listings': {}}, {'listings': [None]},
    {'listings': [{'listingId': '../internal', 'isPrivate': False, 'status': 'active'}]}])
def test_mercor_public_batch_rejects_changed_schema_and_invalid_ids(payload):
    with pytest.raises(CrawlError):
        mercor_public_links(payload)


@pytest.mark.parametrize('url,method,matched', [
    ('https://aws.api.mercor.com/work/listings-explore-page?offset=0', 'GET', True),
    ('https://aws.api.mercor.com/work/private', 'GET', False),
    ('https://evil.example/work/listings-explore-page', 'GET', False),
    ('https://aws.api.mercor.com/work/listings-explore-page', 'POST', False),
])
def test_mercor_observes_only_public_listing_response(url, method, matched):
    assert mercor_listing_response(SimpleNamespace(url=url, request=SimpleNamespace(method=method))) == matched


async def test_mercor_capture_and_missing_pagination_report_partial():
    crawler = CompanyCrawler('mercor')
    async def body():
        return json.dumps({'listings': [{'listingId': 'list_abc', 'isPrivate': False, 'status': 'active'}]}).encode()
    await crawler.capture_mercor_response(SimpleNamespace(status=200, body=body))
    # Reading links never inspects cards, page HTML, or JSON-LD of the listing.
    assert await crawler.links(None) == ['https://work.mercor.com/jobs/list_abc']
    async def count(): return 0
    page = SimpleNamespace(locator=lambda _: SimpleNamespace(count=count))
    assert not await crawler.next_page(page)
    assert crawler.report.limited


async def test_mercor_empty_batch_is_valid_but_http_errors_are_not():
    crawler = CompanyCrawler('mercor')
    async def body(): return b'{"listings":[]}'
    await crawler.capture_mercor_response(SimpleNamespace(status=200, body=body))
    assert crawler.mercor_urls == []
    with pytest.raises(CrawlError, match='HTTP 403'):
        await crawler.capture_mercor_response(SimpleNamespace(status=403))


@pytest.mark.parametrize('url,blocked', [
    ('http://dokploy-postgres:5432/', True),
    ('http://127.0.0.1:3000/', True),
    ('https://rebind.example.org/', True),
    ('https://jobs.micro1.ai.evil.example/', True),
    ('https://jobs.micro1.ai:8443/', True),
    ('https://user:pass@jobs.micro1.ai/', True),
    ('https://jobs.micro1.ai/api/jobs', False),
])
async def test_subresources_cannot_bypass_source_allowlist(url, blocked):
    actions = []
    async def abort(): actions.append('blocked')
    async def proceed(): actions.append('allowed')
    route = SimpleNamespace(request=SimpleNamespace(url=url, resource_type='fetch',
        is_navigation_request=lambda: False), abort=abort, continue_=proceed)
    await CompanyCrawler('micro1').guard(route)
    assert actions == ['blocked' if blocked else 'allowed']


def ld(data):
    return '<script type="application/ld+json">' + json.dumps(data) + '</script>'


def test_identity_ignores_tracking_and_keeps_source_id():
    assert job_identity('micro1', MICRO+'?referralCode=someone') == job_identity('micro1', MICRO)
    assert job_identity('mercor','https://work.mercor.com/jobs/list_abc/title')[0] == job_identity('mercor','https://work.mercor.com/explore?listingId=list_abc')[0]
    assert job_identity('turing','https://work.turing.com/jobs?jobId=123&utm_source=test')[0]=='123'
    assert job_identity('alignerr',ALIGN)[0] == ALIGN.rsplit('/',1)[1]
    assert job_identity('micro1','https://evil.example/post/5ed081d3-01aa-4840-9ac6-c75a61993136') is None
    assert job_identity('micro1','https://jobs.micro1.ai/login') is None


def test_structured_location_and_no_invented_requirements():
    data={'@type':'JobPosting','title':'Video annotator','description':DESCRIPTION,'applicantLocationRequirements':[{'@type':'Country','name':'Brazil'}]}
    job=parse_detail('micro1',MICRO,ld(data))
    assert classify_eligibility(job)[0]=='confirmed_br'
    assert job.requirements == {}
    data['applicantLocationRequirements']=[{'@type':'Country','name':'US'}]
    assert classify_eligibility(parse_detail('micro1',MICRO,ld(data)))[0]=='excluded_br'
    data['applicantLocationRequirements']=[]
    assert classify_eligibility(parse_detail('micro1',MICRO,ld(data)))[0]=='unknown'


def test_alignerr_conflicting_country_is_not_confirmed():
    job={'name':'Portuguese role','htmlLongDescription':DESCRIPTION,'countryCode':'BR','location':'United States','isActive':True}
    html='<script id="__NEXT_DATA__">'+json.dumps({'props':{'pageProps':{'job':job}}})+'</script>'
    raw=parse_detail('alignerr',ALIGN,html)
    assert classify_eligibility(raw)[0]=='unknown'
    assert 'conflitante' in raw.description


def test_missing_description_and_expired_jobs_are_rejected():
    with pytest.raises(CrawlError):parse_detail('micro1',MICRO,'<h1>Login</h1>')
    with pytest.raises(CrawlError):parse_detail('micro1',MICRO,ld({'@type':'JobPosting','title':'Expired','description':DESCRIPTION,'validThrough':'2020-01-01'}))


async def test_robots_denies_private_path_and_unknown_host():
    crawler=CompanyCrawler('mercor')
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda req:httpx.Response(200,text='User-agent: *\nDisallow: /api/\nDisallow: /apply/'))) as client:
        crawler.http=client
        assert not await crawler.allowed('https://work.mercor.com/api/private')
        assert not await crawler.allowed('https://evil.example/')
        assert await crawler.allowed('https://work.mercor.com/explore')


@pytest.fixture
async def sessions(tmp_path):
    engine=create_async_engine(f"sqlite+aiosqlite:///{tmp_path/'crawl.db'}")
    await init_db(engine)
    yield create_session_factory(engine)
    await engine.dispose()


class FakeCrawler:
    def __init__(self,name,known_ids=()):
        self.name=name
        self.report=CrawlReport(name)
    async def fetch_jobs(self):
        await asyncio.sleep(0)
        self.report.discovered=2
        # Deliberately return duplicate rows: persistence must still protect us.
        return [RawJob(source=self.name,source_job_id='stable-id',title='Original',company=self.name,
                       description=DESCRIPTION,source_url=MICRO,application_url=MICRO)]*2


async def test_manual_start_and_second_round_does_not_modify_discarded_job(sessions):
    runs=CrawlRuns(sessions,factory=FakeCrawler)
    assert (await runs.status())['status']=='idle'
    assert runs.task is None
    await runs.start('all')
    with pytest.raises(RuntimeError):await runs.start('micro1')
    await runs.task
    first=await runs.status()
    assert sum(row['inserted'] for row in first['results'])==4
    async with sessions.begin() as session:
        jobs=(await session.scalars(select(Job))).all()
        for job in jobs:
            job.title='Edited by curator';job.editorial_status='DESCARTADA'
    await runs.start('all');await runs.task
    assert sum(row['inserted'] for row in (await runs.status())['results'])==0
    async with sessions() as session:
        jobs=(await session.scalars(select(Job))).all()
        assert len(jobs)==4
        assert all(job.title=='Edited by curator' and job.editorial_status=='DESCARTADA' for job in jobs)
    assert (await CrawlRuns(sessions).status())['status']=='completed'


async def test_one_source_failure_does_not_stop_others(sessions):
    class Mixed(FakeCrawler):
        async def fetch_jobs(self):
            if self.name=='micro1':raise CrawlError('Source changed')
            return await super().fetch_jobs()
    runs=CrawlRuns(sessions,factory=Mixed)
    await runs.start('all');await runs.task
    state=await runs.status()
    assert state['status']=='partial'
    assert sum(row['inserted'] for row in state['results'])==3
    assert state['results'][0]['failed']==1


async def test_restart_marks_unfinished_run_as_interrupted(sessions):
    class Slow(FakeCrawler):
        async def fetch_jobs(self):
            await asyncio.sleep(20)
    runs=CrawlRuns(sessions,factory=Slow)
    await runs.start('micro1')
    await asyncio.sleep(.05)
    assert (await CrawlRuns(sessions).status())['status']=='interrupted'
    await runs.close()
    assert (await runs.status())['status']=='interrupted'
