from pydantic import SecretStr

from buscadin_bot.config import Settings


def test_telegram_configuration_is_validated_only_when_required() -> None:
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:")

    try:
        settings.require_telegram()
    except ValueError as error:
        assert "TELEGRAM_BOT_TOKEN" in str(error)
        assert "TELEGRAM_ADMIN_CHAT_ID" in str(error)
    else:
        raise AssertionError("missing Telegram settings should fail")


def test_telegram_credentials_are_returned_without_exposing_secret_repr() -> None:
    settings = Settings(
        telegram_bot_token=SecretStr("token-value"),
        telegram_admin_chat_id=123,
        telegram_admin_user_id=456,
    )

    token, chat_id, user_id = settings.require_telegram()

    assert token == "token-value"
    assert (chat_id, user_id) == (123, 456)
    assert "token-value" not in repr(settings)
