import httpx

from buscadin_bot.config import Settings
from buscadin_bot.sources.himalayas import HimalayasSource


async def test_himalayas_source_maps_public_payload() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "jobs": [
                    {
                        "guid": "acme/data-labeler",
                        "companySlug": "acme",
                        "companyName": "Acme",
                        "title": "Data Labeler",
                        "description": "<p>Label datasets.</p>",
                        "applicationLink": "https://acme.test/apply",
                        "locationRestrictions": ["Brazil"],
                        "categories": ["Data Labeling"],
                        "pubDate": "2026-10-20T12:00:00Z",
                    }
                ]
            },
        )

    settings = Settings(http_max_retries=0, database_url="sqlite+aiosqlite:///:memory:")
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    source = HimalayasSource(settings, client=client)

    jobs = await source.fetch_jobs()
    await client.aclose()

    assert len(jobs) == 1
    assert jobs[0].source_job_id == "acme/data-labeler"
    assert jobs[0].application_url == "https://acme.test/apply"
    assert requests[0].url.params["limit"] == "20"


async def test_himalayas_source_retries_rate_limit() -> None:
    calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json={"jobs": []})

    settings = Settings(http_max_retries=1, database_url="sqlite+aiosqlite:///:memory:")
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    source = HimalayasSource(settings, client=client)

    jobs = await source.fetch_jobs()
    await client.aclose()

    assert jobs == []
    assert calls == 2
