import httpx
import pytest

from buscadin_bot.services.publication_gateway import HttpPublicationGateway, SiteApiError


async def test_gateway_sends_service_auth_and_actor_without_arbitrary_destination():
    requests = []

    def responder(request):
        requests.append(request)
        return httpx.Response(200, json={
            "job_id": 1, "version": 1, "status": "PUBLICADA", "title": "Annotator",
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(responder)) as client:
        gateway = HttpPublicationGateway("http://127.0.0.1:8000", "test-secret", client=client)
        result = await gateway.confirm("a" * 24, actor="77")
    assert result.status == "PUBLICADA"
    assert requests[0].headers["Authorization"] == "Bearer test-secret"
    assert requests[0].headers["X-Telegram-Actor"] == "77"
    assert requests[0].content == b"{}"


async def test_gateway_does_not_follow_redirect_or_expose_response_secret():
    requests = []

    def responder(request):
        requests.append(request)
        return httpx.Response(302, headers={"Location": "https://evil.example/"}, text="secret-token")

    async with httpx.AsyncClient(transport=httpx.MockTransport(responder), follow_redirects=True) as client:
        gateway = HttpPublicationGateway("http://localhost:8000", "secret-token", client=client)
        with pytest.raises(SiteApiError) as error:
            await gateway.status(1, actor="77")
    assert len(requests) == 1
    assert "secret-token" not in str(error.value)
    assert "evil.example" not in str(error.value)


@pytest.mark.parametrize("code", [401, 403, 404, 409, 422, 500])
async def test_gateway_maps_errors_without_leaking_body(code):
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: httpx.Response(code, json={"detail": "private-referral?token=secret"})
    )) as client:
        gateway = HttpPublicationGateway("http://localhost:8000", "token", client=client)
        with pytest.raises(SiteApiError) as error:
            await gateway.confirm("b" * 24, actor="77")
    assert error.value.status_code == code
    assert "private-referral" not in str(error.value)


async def test_gateway_rejects_incomplete_success_response():
    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={"status": "PUBLICADA"})
    )) as client:
        gateway = HttpPublicationGateway("http://localhost:8000", "token", client=client)
        with pytest.raises(SiteApiError):
            await gateway.confirm("c" * 24, actor="77")


@pytest.mark.parametrize("url", ["http://remote.example", "https://user:pass@example.com", "https://example.com?token=x"])
def test_gateway_rejects_unsafe_configuration(url):
    with pytest.raises(ValueError):
        HttpPublicationGateway(url, "token")
