from datetime import datetime, timezone

import httpx

from buscadin_bot.db.models import Job
from buscadin_bot.telegram.api import TelegramClient
from buscadin_bot.telegram.formatters import format_job_message, job_keyboard
from buscadin_bot.telegram.handlers import is_authorized_update
from buscadin_bot.config import Settings


def test_authorization_requires_both_ids_and_private_chat():
    settings = Settings(_env_file=None, telegram_admin_chat_id=123, telegram_admin_user_id=456)
    update = {"message": {"chat": {"id": 123, "type": "private"}, "from": {"id": 456}}}
    assert is_authorized_update(update, settings)
    for kind in ('group', 'supergroup', 'channel', None):
        update['message']['chat']['type'] = kind
        assert not is_authorized_update(update, settings)
    update['message']['chat']['type'] = 'private'
    settings.telegram_admin_user_id = None
    assert not is_authorized_update(update, settings)


def sample_job() -> Job:
    return Job(
        id=9,
        source="himalayas",
        source_job_id="9",
        source_url="https://source.test/job",
        application_url="https://source.test/apply?a=1&b=2",
        company="A <Company>",
        title="Engineer <remote>",
        description="<b>External</b> description & details",
        category="development",
        eligible_countries=["BR"],
        eligibility_status="confirmed_br",
        salary_disclosed=False,
        language_requirements=[],
    )


def test_job_message_escapes_external_html_and_marks_missing_salary() -> None:
    message = format_job_message(sample_job())

    assert "Engineer &lt;remote&gt;" in message
    assert "A &lt;Company&gt;" in message
    assert "&lt;b&gt;External&lt;/b&gt;" in message
    assert "Não informado" in message
    assert "Indicação: não configurada" in message


def test_keyboard_has_review_actions_and_application_url() -> None:
    keyboard = job_keyboard(sample_job())

    assert keyboard["inline_keyboard"][0][0] == {"text": "Aprovar", "callback_data": "approve:9"}
    assert keyboard["inline_keyboard"][0][1] == {"text": "Descartar", "callback_data": "discard:9"}
    assert keyboard["inline_keyboard"][1][0]["url"] == "https://source.test/apply?a=1&b=2"


async def test_telegram_client_uses_official_method_payloads() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/sendMessage"):
            return httpx.Response(200, json={"ok": True, "result": {"message_id": 123}})
        return httpx.Response(200, json={"ok": True, "result": []})

    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    telegram = TelegramClient("secret-token", client=http_client, api_root="https://telegram.test")
    sent = await telegram.send_message(123, "hello")
    updates = await telegram.get_updates(offset=8)
    await http_client.aclose()

    assert sent.message_id == 123
    assert updates == []
    assert requests[0].url.path == "/botsecret-token/sendMessage"
    assert requests[1].url.path == "/botsecret-token/getUpdates"
    assert '"offset":8' in requests[1].content.decode()
