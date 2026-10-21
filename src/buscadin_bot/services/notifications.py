"""Reliable delivery of pending jobs through the Telegram outbox."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from buscadin_bot.db.models import Notification
from buscadin_bot.services.referrals import ReferralResolver
from buscadin_bot.telegram.api import TelegramApiError, TelegramClient
from buscadin_bot.telegram.formatters import format_job_message, job_keyboard


class NotificationWorker:
    def __init__(self, max_attempts: int = 8, referral_resolver: ReferralResolver | None = None) -> None:
        self.max_attempts = max_attempts
        self.referral_resolver = referral_resolver

    async def send_pending(
        self,
        session: AsyncSession,
        telegram: TelegramClient,
        *,
        chat_id: int,
        limit: int = 20,
    ) -> tuple[int, int]:
        now = datetime.now(timezone.utc)
        result = await session.execute(
            select(Notification)
            .options(selectinload(Notification.job))
            .where(
                Notification.status.in_(["pending", "failed"]),
                (Notification.next_attempt_at.is_(None) | (Notification.next_attempt_at <= now)),
            )
            .order_by(Notification.created_at)
            .limit(limit)
        )
        sent = 0
        failed = 0
        for notification in result.scalars().all():
            try:
                resolution = (
                    await self.referral_resolver.apply_resolution(session, notification.job)
                    if self.referral_resolver is not None
                    else None
                )
                legacy_referral = None
                if resolution is None and self.referral_resolver is not None:
                    legacy_referral = await self.referral_resolver.resolve(session, notification.job)
                message = await telegram.send_message(
                    chat_id,
                    format_job_message(
                        notification.job,
                        legacy_referral,
                        referral_status=resolution.status if resolution else None,
                        referral_reason=resolution.reason if resolution else None,
                        referral_url=resolution.link.url if resolution and resolution.link else None,
                    ),
                    reply_markup=job_keyboard(
                        notification.job,
                        editorial=resolution is not None,
                        destination_url=resolution.link.url
                        if resolution and resolution.status == "LINK_VALIDADO" and resolution.link
                        else notification.job.application_url,
                    ),
                )
            except TelegramApiError as error:
                notification.attempts += 1
                notification.status = "failed" if notification.attempts < self.max_attempts else "dead"
                notification.last_error = str(error)
                delay = error.retry_after or min(3600, 2 ** min(notification.attempts, 10))
                notification.next_attempt_at = now + timedelta(seconds=delay)
                failed += 1
                continue
            notification.status = "sent"
            notification.sent_at = now
            notification.telegram_message_id = message.message_id
            notification.last_error = None
            notification.next_attempt_at = None
            if resolution is not None:
                notification.last_notified_referral_status = resolution.status
            sent += 1
        await session.commit()
        return sent, failed
