"""Small async client for the official Telegram Bot API over HTTP."""

from dataclasses import dataclass
from typing import Any

import httpx


class TelegramApiError(RuntimeError):
    """Represents a non-successful response from Telegram."""

    def __init__(self, message: str, *, status_code: int | None = None, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after


@dataclass(slots=True)
class SentMessage:
    message_id: int
    raw: dict[str, Any]


class TelegramClient:
    def __init__(
        self,
        token: str,
        client: httpx.AsyncClient | None = None,
        api_root: str = "https://api.telegram.org",
    ) -> None:
        self._client = client or httpx.AsyncClient(timeout=30.0)
        self._owns_client = client is None
        self._base_url = f"{api_root.rstrip('/')}/bot{token}"

    async def __aenter__(self) -> "TelegramClient":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def call(self, method: str, payload: dict[str, Any]) -> Any:
        response = await self._client.post(f"{self._base_url}/{method}", json=payload)
        try:
            body = response.json()
        except ValueError as error:
            raise TelegramApiError("Telegram returned invalid JSON", status_code=response.status_code) from error

        if not response.is_success:
            raise TelegramApiError(
                f"Telegram HTTP error {response.status_code}",
                status_code=response.status_code,
                retry_after=_retry_after(body),
            )
        if not isinstance(body, dict) or body.get("ok") is not True:
            description = body.get("description", "unknown Telegram error") if isinstance(body, dict) else "invalid response"
            parameters = body.get("parameters", {}) if isinstance(body, dict) else {}
            retry_after = parameters.get("retry_after") if isinstance(parameters, dict) else None
            raise TelegramApiError(str(description), status_code=body.get("error_code") if isinstance(body, dict) else None, retry_after=retry_after)
        return body.get("result")

    async def send_message(
        self,
        chat_id: int,
        text: str,
        *,
        reply_markup: dict[str, Any] | None = None,
        parse_mode: str = "HTML",
    ) -> SentMessage:
        payload: dict[str, Any] = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        result = await self.call("sendMessage", payload)
        if not isinstance(result, dict) or not isinstance(result.get("message_id"), int):
            raise TelegramApiError("Telegram sendMessage returned no message_id")
        return SentMessage(message_id=result["message_id"], raw=result)

    async def get_updates(
        self,
        *,
        offset: int | None,
        timeout: int = 25,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {"timeout": timeout, "limit": limit}
        if offset is not None:
            payload["offset"] = offset
        result = await self.call("getUpdates", payload)
        if not isinstance(result, list):
            raise TelegramApiError("Telegram getUpdates returned an invalid result")
        return [item for item in result if isinstance(item, dict)]

    async def answer_callback_query(self, callback_query_id: str, text: str | None = None) -> bool:
        payload: dict[str, Any] = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
        result = await self.call("answerCallbackQuery", payload)
        return bool(result)

    async def edit_message_reply_markup(
        self,
        *,
        chat_id: int,
        message_id: int,
        reply_markup: dict[str, Any] | None = None,
    ) -> Any:
        payload: dict[str, Any] = {"chat_id": chat_id, "message_id": message_id}
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        return await self.call("editMessageReplyMarkup", payload)

    async def edit_message_text(
        self,
        *,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: dict[str, Any] | None = None,
        parse_mode: str = "HTML",
    ) -> Any:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": parse_mode,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        return await self.call("editMessageText", payload)


def _retry_after(body: Any) -> int | None:
    if not isinstance(body, dict):
        return None
    parameters = body.get("parameters")
    if not isinstance(parameters, dict):
        return None
    value = parameters.get("retry_after")
    return int(value) if isinstance(value, (int, float)) else None
