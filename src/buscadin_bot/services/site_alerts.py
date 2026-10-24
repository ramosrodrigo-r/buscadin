"""Delivery of durable publication alerts to the administrator chat."""

from html import escape

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from buscadin_bot.db.models import SiteAlert, utcnow
from buscadin_bot.telegram.api import TelegramApiError, TelegramClient


class SiteAlertWorker:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions

    async def send_pending(
        self, telegram: TelegramClient, *, chat_id: int, limit: int = 20,
    ) -> tuple[int, int]:
        if not 1 <= limit <= 100:
            raise ValueError("Limite de alertas inválido")
        async with self.sessions() as session:
            alerts = list((await session.scalars(
                select(SiteAlert).where(SiteAlert.sent_at.is_(None))
                .order_by(SiteAlert.created_at, SiteAlert.id).limit(limit)
            )).all())
        sent = failed = 0
        for alert in alerts:
            try:
                await telegram.send_message(chat_id, escape(alert.message))
            except TelegramApiError:
                failed += 1
                continue
            async with self.sessions.begin() as session:
                result = await session.execute(update(SiteAlert).where(
                    SiteAlert.id == alert.id, SiteAlert.sent_at.is_(None),
                ).values(sent_at=utcnow()))
                sent += int(result.rowcount == 1)
        return sent, failed
