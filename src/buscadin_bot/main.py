"""Application entry point for collection, outbox delivery and polling."""

import asyncio

from buscadin_bot.config import get_settings
from buscadin_bot.db.repository import JobRepository
from buscadin_bot.db.session import close_engine, create_engine, create_session_factory, init_db
from buscadin_bot.services.collector import Collector
from buscadin_bot.services.notifications import NotificationWorker
from buscadin_bot.services.referrals import ReferralResolver
from buscadin_bot.sources.himalayas import HimalayasSource
from buscadin_bot.telegram.api import TelegramClient
from buscadin_bot.telegram.poller import TelegramPoller


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
    engine = create_engine(settings)
    await init_db(engine)
    sessions = create_session_factory(engine)
    referral_resolver = ReferralResolver()
    collector = Collector(JobRepository(), referral_resolver=referral_resolver)
    worker = NotificationWorker(referral_resolver=referral_resolver)
    try:
        async with HimalayasSource(settings) as source, TelegramClient(token) as telegram:
            poller = TelegramPoller(telegram, sessions, settings)
            next_collection = 0.0
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
                await poller.poll_once()
    finally:
        await close_engine(engine)


def main() -> None:
    asyncio.run(run_service())


if __name__ == "__main__":
    main()
