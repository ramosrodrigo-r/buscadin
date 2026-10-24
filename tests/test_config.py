from pydantic import SecretStr
import pytest

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


def test_site_integration_requires_both_telegram_identities_and_credentials() -> None:
    settings = Settings(_env_file=None, site_api_url="http://localhost:8000", site_api_token="private-token", telegram_admin_chat_id=123)
    with pytest.raises(ValueError, match="TELEGRAM_ADMIN_USER_ID"):
        settings.require_site_identity()
    settings.telegram_admin_user_id = 456
    settings.require_site_identity()
    assert "private-token" not in repr(settings)
    settings.site_api_token = None
    with pytest.raises(ValueError, match="SITE_API_TOKEN"):
        settings.require_site_identity()
