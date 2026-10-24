import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine

from buscadin_bot.db.models import SiteAlert
from buscadin_bot.db.session import create_session_factory, init_db
from buscadin_bot.services.site_alerts import SiteAlertWorker
from buscadin_bot.telegram.api import SentMessage, TelegramApiError


class FakeTelegram:
    def __init__(self, *, fail=False):
        self.messages = []
        self.fail = fail

    async def send_message(self, chat_id, text, **kwargs):
        if self.fail:
            raise TelegramApiError("temporary")
        self.messages.append((chat_id, text))
        return SentMessage(len(self.messages), {})


@pytest.fixture
async def alerts(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'alerts.db'}")
    await init_db(engine)
    sessions = create_session_factory(engine)
    async with sessions.begin() as session:
        session.add(SiteAlert(event_key="suspend:1:1", job_id=1, message="Link <expirado>"))
    yield sessions
    await engine.dispose()


async def test_alert_delivery_escapes_and_is_idempotent(alerts):
    worker = SiteAlertWorker(alerts)
    telegram = FakeTelegram()
    assert await worker.send_pending(telegram, chat_id=99) == (1, 0)
    assert telegram.messages == [(99, "Link &lt;expirado&gt;")]
    assert await worker.send_pending(telegram, chat_id=99) == (0, 0)


async def test_alert_failure_remains_pending(alerts):
    worker = SiteAlertWorker(alerts)
    assert await worker.send_pending(FakeTelegram(fail=True), chat_id=99) == (0, 1)
    async with alerts() as session:
        alert = await session.scalar(select(SiteAlert))
        assert alert.sent_at is None
