"""Long polling loop with durable update offsets."""

import asyncio
import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from buscadin_bot.config import Settings
from buscadin_bot.telegram.api import TelegramClient
from buscadin_bot.telegram.handlers import get_update_offset, handle_update, set_update_offset

logger = logging.getLogger(__name__)


class TelegramPoller:
    def __init__(self, telegram: TelegramClient, sessions: async_sessionmaker[AsyncSession], settings: Settings) -> None:
        self.telegram = telegram
        self.sessions = sessions
        self.settings = settings

    async def poll_once(self) -> int:
        async with self.sessions() as session:
            offset = await get_update_offset(session)
            updates = await self.telegram.get_updates(offset=offset)
            processed = 0
            for update in updates:
                await handle_update(update, session=session, telegram=self.telegram, settings=self.settings)
                update_id = update.get("update_id")
                if isinstance(update_id, int):
                    await set_update_offset(session, update_id + 1)
                processed += 1
            await session.commit()
            return processed

    async def run_forever(self, stop_event: asyncio.Event | None = None) -> None:
        stop_event = stop_event or asyncio.Event()
        while not stop_event.is_set():
            try:
                await self.poll_once()
            except Exception:
                logger.exception("Telegram polling failed")
                await asyncio.sleep(2)
