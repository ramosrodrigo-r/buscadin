"""Application entry point for collection, outbox delivery and polling."""

import asyncio
import logging
from contextlib import AsyncExitStack

from buscadin_bot.config import get_settings
from buscadin_bot.db.repository import JobRepository
from buscadin_bot.db.session import close_engine, create_engine, create_session_factory, init_db
from buscadin_bot.services.collector import Collector
from buscadin_bot.services.notifications import NotificationWorker
from buscadin_bot.services.referrals import ReferralResolver
from buscadin_bot.services.publication_gateway import HttpPublicationGateway
from buscadin_bot.services.site_alerts import SiteAlertWorker
from buscadin_bot.services.site_publications import SitePublicationService
from buscadin_bot.sources.himalayas import HimalayasSource
from buscadin_bot.telegram.api import TelegramClient
from buscadin_bot.telegram.poller import TelegramPoller

logger = logging.getLogger(__name__)


def _domains(value: str) -> list[str]:
    return [item.strip().lower() for item in value.split(",") if item.strip()]


async def bootstrap() -> None:
    settings = get_settings()
    engine = create_engine(settings)
    try:
        await init_db(engine)
    finally:
        await close_engine(engine)


async def run_service() -> None:
    settings = get_settings()
    token, chat_id, _ = settings.require_telegram()
    if settings.site_api_url or settings.site_api_token:
        settings.require_site_identity()
    engine = create_engine(settings)
    await init_db(engine)
    sessions = create_session_factory(engine)
    referral_resolver = ReferralResolver()
    collector = Collector(JobRepository(), referral_resolver=referral_resolver)
    worker = NotificationWorker(referral_resolver=referral_resolver)
    try:
        async with AsyncExitStack() as stack:
            source = await stack.enter_async_context(HimalayasSource(settings))
            telegram = await stack.enter_async_context(TelegramClient(token))
            site_gateway = None
            if settings.site_api_url and settings.site_api_token:
                site_gateway = HttpPublicationGateway(settings.site_api_url, settings.site_api_token.get_secret_value())
                stack.push_async_callback(site_gateway.aclose)
            site_service = None
            site_alerts = None
            if settings.site_api_url and settings.site_api_token:
                site_service = SitePublicationService(
                    sessions,
                    admin_actor=str(settings.telegram_admin_user_id),
                    official_domains=_domains(settings.site_official_domains),
                )
                site_alerts = SiteAlertWorker(sessions)
            poller = TelegramPoller(telegram, sessions, settings, site_gateway=site_gateway)
            next_collection = 0.0
            next_reconciliation = 0.0
            loop = asyncio.get_running_loop()
            while True:
                now = loop.time()
                if now >= next_collection:
                    async with sessions() as session:
                        await collector.collect_source(session, source)
                        await worker.send_pending(
                            session,
                            telegram,
                            chat_id=chat_id,
                            limit=settings.max_notifications_per_run,
                        )
                    next_collection = now + settings.collect_interval_hours * 3600
                if site_service is not None and now >= next_reconciliation:
                    try:
                        await site_service.reconcile()
                        if site_alerts is not None:
                            await site_alerts.send_pending(telegram, chat_id=chat_id)
                    except Exception as error:
                        logger.error("Site reconciliation failed (%s)", type(error).__name__)
                    next_reconciliation = now + max(300.0, settings.collect_interval_hours * 3600)
                try:
                    await poller.poll_once()
                except Exception as error:
                    # HTTP exception strings may contain a Telegram token URL.
                    logger.error("Telegram polling failed (%s); retrying", type(error).__name__)
                    await asyncio.sleep(2)
    finally:
        await close_engine(engine)


def main() -> None:
    asyncio.run(run_service())


if __name__ == "__main__":
    main()
