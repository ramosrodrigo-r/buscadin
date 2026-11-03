"""Admin-side source adapter. The admin never starts a browser locally."""
import httpx
from pydantic import ValidationError

from buscadin_bot.sources.company_crawler import CrawlError, CrawlReport, SOURCES
from buscadin_bot.sources.crawl_contract import CrawlRequest, CrawlResponse

CRAWLER_URL = 'http://buscadin-crawler:8082/crawl'
MAX_RESPONSE_BYTES = 4 * 1024 * 1024


class RemoteCompanyCrawler:
    def __init__(self, name, known_ids=(), *, max_new=30, max_pages=5, transport=None):
        if name not in SOURCES:
            raise ValueError('Unknown source')
        self.name = name
        self.known = set(known_ids)
        self.max_new, self.max_pages = max_new, max_pages
        self.report = CrawlReport(name)
        self.transport = transport

    async def fetch_jobs(self):
        # Known IDs only reduce work; persistence still enforces uniqueness.
        request = CrawlRequest(source=self.name, known_ids=sorted(self.known)[-3000:],
                               max_new=self.max_new, max_pages=self.max_pages)
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(590, connect=5), follow_redirects=False,
                trust_env=False, transport=self.transport, headers={"Accept-Encoding": "identity"},
            ) as client:
                async with client.stream('POST', CRAWLER_URL, json=request.model_dump()) as response:
                    if response.status_code != 200:
                        raise CrawlError(f'Serviço isolado de coleta retornou HTTP {response.status_code}')
                    if response.headers.get('content-encoding', 'identity').lower() not in {'', 'identity'}:
                        raise CrawlError('Resposta comprimida da coleta não permitida')
                    if response.headers.get('content-type', '').split(';')[0] != 'application/json':
                        raise CrawlError('Formato de resposta da coleta inválido')
                    content = bytearray()
                    async for chunk in response.aiter_bytes():
                        content.extend(chunk)
                        if len(content) > MAX_RESPONSE_BYTES:
                            raise CrawlError('Resposta da coleta excedeu o limite de tamanho')
            result = CrawlResponse.model_validate_json(bytes(content))
            if result.report.source != self.name or len(result.jobs) > self.max_new:
                raise CrawlError('Resposta da coleta não corresponde à solicitação')
            self.report = CrawlReport(**result.report.model_dump())
            return [job.raw_job() for job in result.jobs]
        except (httpx.HTTPError, ValidationError, ValueError, RecursionError) as error:
            if isinstance(error, CrawlError):
                raise
            raise CrawlError('Serviço isolado de coleta indisponível ou resposta inválida') from None
