"""Private RPC on an exclusive Docker network; no public ports or credentials."""
import asyncio
from dataclasses import asdict
import os
from pathlib import Path
import logging

from pydantic import ValidationError

from buscadin_bot.sources.browser_runtime import verify_browser_sandbox
from buscadin_bot.sources.company_crawler import CompanyCrawler
from buscadin_bot.sources.crawl_contract import CrawlRequest, CrawlResponse
from buscadin_bot.web.server import MAX_BODY_BYTES, WebResponse, serve

logger = logging.getLogger(__name__)


class CrawlerApplication:
    def __init__(self, *, factory=CompanyCrawler):
        self.factory = factory
        self.lock = asyncio.Lock()

    @staticmethod
    def _error(status, message):
        return WebResponse.json(status, {'error': message})

    async def handle(self, method, target, *, headers=None, body=b''):
        headers = {k.lower(): v for k, v in (headers or {}).items()}
        if target == '/health' and method == 'GET':
            return WebResponse.json(200, {'status': 'ok'})
        if target != '/crawl' or method != 'POST':
            return self._error(404, 'Rota não encontrada')
        if len(body) > MAX_BODY_BYTES:
            return self._error(413, 'Solicitação muito grande')
        if headers.get('content-type', '').split(';')[0] != 'application/json':
            return self._error(415, 'Envie JSON')
        try:
            request = CrawlRequest.model_validate_json(body)
        except (ValidationError, ValueError, RecursionError):
            return self._error(422, 'Solicitação inválida')
        if self.lock.locked():
            return self._error(409, 'Uma coleta está em andamento')
        async with self.lock:
            crawler = self.factory(request.source, known_ids=request.known_ids,
                                   max_new=request.max_new, max_pages=request.max_pages)
            try:
                async with asyncio.timeout(570):
                    jobs = await crawler.fetch_jobs()
                result = CrawlResponse.model_validate({
                    'jobs': [asdict(job) for job in jobs], 'report': asdict(crawler.report),
                })
                return WebResponse.json(200, result.model_dump(mode='json'))
            except Exception as error:
                logger.warning('Isolated crawl failed: %s (%s)', request.source, type(error).__name__)
                return self._error(502, 'A fonte não concluiu a coleta')


def require_credential_free_environment():
    forbidden = {'DATABASE_URL', 'ADMIN_PASSWORD', 'CAROUSEL_WORKER_TOKEN',
                 'BUSCADIN_CAROUSEL_WORKER_TOKEN', 'CF_ACCESS_CLIENT_SECRET',
                 'TELEGRAM_BOT_TOKEN', 'SITE_API_TOKEN'}
    if (any(os.environ.get(key) for key in forbidden)
            or Path('/var/run/docker.sock').exists()
            or (Path('/run/secrets').is_dir() and any(Path('/run/secrets').iterdir()))
            or Path('/app/.env').exists()):
        raise RuntimeError('Crawler must not receive application credentials or Docker access')


async def run():
    require_credential_free_environment()
    evidence = await verify_browser_sandbox()
    logger.info('Crawler sandbox verified: %s', evidence)
    await serve(CrawlerApplication(), host='0.0.0.0', port=8082)


def main():
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run())


if __name__ == '__main__':
    main()
