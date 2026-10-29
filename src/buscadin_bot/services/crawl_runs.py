"""Manual admin-only crawl runs; no scheduler and no automatic publication."""
import asyncio
from dataclasses import asdict
import json
import logging
import secrets

from sqlalchemy import select

from buscadin_bot.db.models import AuditEvent, BotState, Job, utcnow
from buscadin_bot.services.collector import Collector
from buscadin_bot.sources.company_crawler import CompanyCrawler, CrawlError, SOURCES

logger = logging.getLogger(__name__)
STATE_KEY = "admin_manual_crawl"


class CrawlRuns:
    def __init__(self, sessions, *, factory=CompanyCrawler):
        self.sessions, self.factory = sessions, factory
        self.task = None
        self.state = None

    async def status(self):
        if self.state is not None:
            return self.state
        async with self.sessions() as session:
            row = await session.get(BotState, STATE_KEY)
        if row:
            result = json.loads(row.value)
            if result["status"] == "running":
                result["status"] = "interrupted"
                result["message"] = "O serviço reiniciou. Execute novamente; vagas já salvas serão ignoradas."
            return result
        return {"status": "idle", "results": []}

    async def start(self, source):
        if source not in {*SOURCES, "all"}:
            raise ValueError("Escolha micro1, turing, mercor, alignerr ou all")
        if self.task and not self.task.done():
            raise RuntimeError("Uma coleta já está em andamento")
        # No await before assigning task: atomic start within one event loop.
        self.state = {"id": secrets.token_hex(12), "status": "running", "started_at": utcnow().isoformat(),
                      "sources": list(SOURCES) if source == "all" else [source], "current": None, "results": []}
        self.task = asyncio.create_task(self._run())
        return self.state

    async def persist(self):
        async with self.sessions.begin() as session:
            await session.merge(BotState(key=STATE_KEY, value=json.dumps(self.state)))

    async def _run(self):
        try:
            for name in self.state["sources"]:
                self.state["current"] = name
                await self.persist()
                async with self.sessions() as session:
                    known = set((await session.scalars(select(Job.source_job_id).where(Job.source == name))).all())
                crawler = self.factory(name, known_ids=known)
                result = {"source": name, "inserted": 0, "skipped": 0, "failed": 0}
                try:
                    async with asyncio.timeout(600):
                        async with self.sessions() as session:
                            collected = await Collector().collect_source(session, crawler, new_only=True)
                    result = {**asdict(collected), **asdict(crawler.report), "inserted": collected.inserted,
                              "skipped": collected.skipped + crawler.report.skipped,
                              "failed": collected.failed + crawler.report.failed}
                    if collected.error:
                        result["error"] = "A fonte não concluiu a coleta. Verifique os detalhes ou tente novamente."
                except asyncio.TimeoutError:
                    result.update(failed=1, error="Tempo máximo de dez minutos atingido nesta fonte.")
                except Exception as error:
                    logger.warning("Manual crawl failed: %s (%s)", name, type(error).__name__)
                    result.update(failed=1, error=str(error) if isinstance(error, CrawlError) else "Falha ao consultar a fonte")
                self.state["results"].append(result)
                await self.persist()
            self.state["status"] = "partial" if any(row["failed"] for row in self.state["results"]) else "completed"
        except asyncio.CancelledError:
            self.state["status"] = "interrupted"
            raise
        except Exception as error:
            logger.error("Crawl supervisor failed (%s)", type(error).__name__)
            self.state["status"] = "failed"
            self.state["message"] = "Falha na operação; consulte o histórico e execute novamente."
        finally:
            self.state["current"] = None
            self.state["finished_at"] = utcnow().isoformat()
            await self.persist()
            async with self.sessions.begin() as session:
                session.add(AuditEvent(event_type="admin_manual_crawl", actor="admin:web", after_json=json.loads(json.dumps(self.state))))

    async def close(self):
        if self.task and not self.task.done():
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
