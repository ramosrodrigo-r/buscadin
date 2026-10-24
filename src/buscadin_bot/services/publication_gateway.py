"""Bot-side contract for the private publication API (no platform DB access)."""

from typing import Any, Literal, Protocol
from urllib.parse import urlsplit

import httpx
from pydantic import BaseModel, Field, ValidationError


class SitePreviewResponse(BaseModel):
    token: str = Field(pattern=r"^[a-f0-9]{24}$")
    job_id: int = Field(gt=0)
    expected_version: int = Field(ge=0)
    public: dict[str, Any]
    destination_type: Literal["OFFICIAL", "REFERRAL"]
    destination_url: str
    expires_at: str


class SiteStatusResponse(BaseModel):
    job_id: int = Field(gt=0)
    version: int = Field(ge=0)
    status: Literal["NAO_PUBLICADA", "PUBLICADA", "DESPUBLICADA"]
    title: str
    application_suspended: bool = False
    public_url: str | None = None


class SiteRequirementsResponse(BaseModel):
    job_id: int = Field(gt=0)
    title: str
    requirements: dict[str, Literal["required", "not_required", "unknown"]]


class PublicationGateway(Protocol):
    async def preview(self, job_id: int, *, actor: str, destination_type: str, summary: str) -> SitePreviewResponse: ...
    async def confirm(self, token: str, *, actor: str) -> SiteStatusResponse: ...
    async def status(self, job_id: int, *, actor: str) -> SiteStatusResponse: ...
    async def listing(self, *, actor: str, status: str, page: int) -> list[SiteStatusResponse]: ...
    async def unpublish(self, job_id: int, *, actor: str, expected_version: int, event_id: str, reason: str) -> SiteStatusResponse: ...
    async def set_requirements(self, job_id: int, *, actor: str, requirements: dict[str, Any]) -> SiteRequirementsResponse: ...


class SiteApiError(RuntimeError):
    """Safe user-facing message; never includes a token or response body."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class HttpPublicationGateway:
    def __init__(self, base_url: str, token: str, *, client: httpx.AsyncClient | None = None) -> None:
        parsed = urlsplit(base_url)
        if (
            parsed.scheme not in {"http", "https"} or not parsed.hostname
            or parsed.username or parsed.password or parsed.query or parsed.fragment
        ):
            raise ValueError("SITE_API_URL deve ser uma URL interna sem credenciais ou parâmetros")
        if parsed.scheme == "http" and parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("HTTP sem TLS permitido somente em loopback")
        if not token.strip():
            raise ValueError("SITE_API_TOKEN obrigatório")
        self.base_url = base_url.rstrip("/")
        self._token = token
        self._client = client or httpx.AsyncClient(timeout=15.0, follow_redirects=False)
        self._owns_client = client is None

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def _call(self, method: str, path: str, *, actor: str, body: dict | None = None, params: dict | None = None) -> Any:
        try:
            response = await self._client.request(
                method, self.base_url + path, json=body, params=params,
                headers={"Authorization": f"Bearer {self._token}", "X-Telegram-Actor": actor},
                follow_redirects=False,
            )
        except httpx.HTTPError:
            raise SiteApiError("Não foi possível confirmar o resultado. Consulte /site e tente novamente.") from None
        if response.status_code == 409:
            raise SiteApiError("A vaga ou o destino mudou. Gere uma nova prévia.", status_code=409)
        if response.status_code in {401, 403}:
            raise SiteApiError("A plataforma recusou a autorização do administrador.", status_code=response.status_code)
        if response.status_code == 404:
            raise SiteApiError("Vaga ou prévia não encontrada na plataforma.", status_code=404)
        if response.status_code in {400, 422}:
            raise SiteApiError("Dados, elegibilidade ou destino não permitem esta ação. Revise a vaga.", status_code=response.status_code)
        if not response.is_success:
            raise SiteApiError("Plataforma indisponível. Consulte /site antes de repetir a ação.", status_code=response.status_code)
        try:
            return response.json()
        except ValueError:
            raise SiteApiError("Resposta inválida da plataforma; resultado não confirmado.") from None

    @staticmethod
    def _parse(model: type[BaseModel], data: Any):
        try:
            return model.model_validate(data)
        except ValidationError:
            raise SiteApiError("Resposta incompleta da plataforma; resultado não confirmado.") from None

    async def preview(self, job_id: int, *, actor: str, destination_type: str, summary: str) -> SitePreviewResponse:
        data = await self._call("POST", f"/internal/jobs/{job_id}/publication-preview", actor=actor,
                                body={"destination_type": destination_type, "summary": summary})
        return self._parse(SitePreviewResponse, data)

    async def confirm(self, token: str, *, actor: str) -> SiteStatusResponse:
        # Token is generated by the backend, not interpolated from an arbitrary URL.
        import re
        if re.fullmatch(r"[a-f0-9]{24}", token) is None:
            raise SiteApiError("Identificador de prévia inválido.")
        data = await self._call("POST", f"/internal/site-previews/{token}/confirm", actor=actor, body={})
        return self._parse(SiteStatusResponse, data)

    async def status(self, job_id: int, *, actor: str) -> SiteStatusResponse:
        return self._parse(SiteStatusResponse, await self._call("GET", f"/internal/jobs/{job_id}/publication", actor=actor))

    async def listing(self, *, actor: str, status: str, page: int) -> list[SiteStatusResponse]:
        data = await self._call("GET", "/internal/jobs", actor=actor, params={"site_status": status, "page": page})
        if not isinstance(data, dict) or not isinstance(data.get("items"), list) or len(data["items"]) > 20:
            raise SiteApiError("Listagem inválida da plataforma.")
        return [self._parse(SiteStatusResponse, item) for item in data["items"]]

    async def unpublish(self, job_id: int, *, actor: str, expected_version: int, event_id: str, reason: str) -> SiteStatusResponse:
        data = await self._call("POST", f"/internal/jobs/{job_id}/unpublish", actor=actor, body={
            "expected_version": expected_version, "event_id": event_id, "reason": reason,
        })
        return self._parse(SiteStatusResponse, data)

    async def set_requirements(self, job_id: int, *, actor: str, requirements: dict[str, Any]) -> SiteRequirementsResponse:
        data = await self._call(
            "POST", f"/internal/jobs/{job_id}/requirements", actor=actor,
            body={"requirements": requirements},
        )
        return self._parse(SiteRequirementsResponse, data)
