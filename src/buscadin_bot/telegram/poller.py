"""Long polling loop with durable update offsets."""

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from buscadin_bot.config import Settings
from buscadin_bot.services.publication_gateway import PublicationGateway
from buscadin_bot.telegram.api import TelegramClient
from buscadin_bot.telegram.handlers import get_update_offset, handle_update, set_update_offset

logger = logging.getLogger(__name__)


class TelegramPoller:
    def __init__(self, telegram: TelegramClient, sessions: async_sessionmaker[AsyncSession], settings: Settings, site_gateway: PublicationGateway | None = None) -> None:
        self.telegram = telegram
        self.sessions = sessions
        self.settings = settings
        self.site_gateway = site_gateway

    async def poll_once(self) -> int:
        async with self.sessions() as session:
            offset = await get_update_offset(session)
        updates = await self.telegram.get_updates(offset=offset)
        processed = 0
        for update in updates:
            update_id = update.get("update_id")
            if not isinstance(update_id, int) or (offset is not None and update_id < offset):
                continue
            async with self.sessions() as session:
                await handle_update(update, session=session, telegram=self.telegram, settings=self.settings, site_gateway=self.site_gateway)
                await set_update_offset(session, update_id + 1)
                await session.commit()
            offset = update_id + 1
            processed += 1
        return processed

    async def run_forever(self, stop_event: asyncio.Event | None = None) -> None:
        stop_event = stop_event or asyncio.Event()
        while not stop_event.is_set():
            try:
                await self.poll_once()
            except Exception as error:
                logger.error("Telegram polling failed (%s)", type(error).__name__)
                await asyncio.sleep(2)
