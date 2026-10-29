"\"\"\"Small dependency-free HTTP transport for the public portal and private API.\"\"\""

from __future__ import annotations

import asyncio
import json
import mimetypes
import re
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from buscadin_bot.services.catalogue import CatalogueFilters, PublicCatalogue
from buscadin_bot.services.publication_policy import PublicationRejected
from buscadin_bot.services.requirements import JobRequirements
from buscadin_bot.services.site_publications import PublicationConflict, SitePublicationService
from buscadin_bot.web.rendering import PortalRenderer

MAX_REQUEST_BYTES = 512 * 1024
MAX_BODY_BYTES = 256 * 1024
_JOB_PATH = re.compile(r"^/vagas/(?:[a-z0-9-]+-)?([1-9][0-9]*)$")
_ID_PATH = re.compile(r"^/internal/jobs/([1-9][0-9]*)/publication$")


@dataclass(frozen=True)
class WebResponse:
    status: int
    body: bytes
    content_type: str = "text/html; charset=utf-8"
    headers: dict[str, str] | None = None

    @classmethod
    def html(cls, status: int, content: str, *, headers: dict[str, str] | None = None) -> "WebResponse":
        return cls(status, content.encode("utf-8"), headers=headers)

    @classmethod
    def json(cls, status: int, payload: Any) -> "WebResponse":
        return cls(
            status,
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
            content_type="application/json; charset=utf-8",
        )


class PortalApplication:
    """Route requests without coupling the domain to a web framework."""

    def __init__(
        self,
        catalogue: PublicCatalogue,
        publications: SitePublicationService,
        *,
        renderer: PortalRenderer | None = None,
        internal_token: str,
        static_dir: Path | None = None,
    ) -> None:
        if not internal_token.strip():
            raise ValueError("Token interno obrigatório")
        self.catalogue = catalogue
        self.publications = publications
        self.renderer = renderer or PortalRenderer()
        self.internal_token = internal_token
        self.static_dir = (static_dir or Path(__file__).parent / "static").resolve()

    async def handle(
        self,
        method: str,
        target: str,
        *,
        headers: dict[str, str] | None = None,
        body: bytes = b"",
    ) -> WebResponse:
        headers = {key.lower(): value for key, value in (headers or {}).items()}
        if len(body) > MAX_BODY_BYTES:
            return self._error(413, "Corpo da requisição muito grande")
        try:
            parsed = urlsplit(target)
            if parsed.scheme or parsed.netloc or not parsed.path.startswith("/"):
                return self._error(400, "URL inválida")
            path = unquote(parsed.path)
        except ValueError:
            return self._error(400, "URL inválida")
        method = method.upper()
        if method not in {"GET", "HEAD", "POST"}:
            return self._error(405, "Método não permitido", headers={"Allow": "GET, HEAD, POST"})
        if path.startswith("/internal/"):
            return await self._internal(method, path, parsed.query, headers, body)
        if method not in {"GET", "HEAD"}:
            return self._error(405, "Método não permitido", headers={"Allow": "GET, HEAD"})
        return await self._public(method, path, parsed.query)

    async def _public(self, method: str, path: str, query: str) -> WebResponse:
        if path == "/healthz":
            try:
                await self.catalogue.health()
            except SQLAlchemyError:
                response = WebResponse.json(503, {"status": "unavailable"})
            else:
                response = WebResponse.json(200, {"status": "ok"})
        elif path == "/robots.txt":
            response = WebResponse(
                200,
                f"User-agent: *\nAllow: /\nSitemap: {self.renderer.base_url}/sitemap.xml\n".encode(),
                content_type="text/plain; charset=utf-8",
            )
        elif path == "/sitemap.xml":
            response = await self._sitemap()
        elif path.startswith("/static/"):
            response = self._static(path.removeprefix("/static/"))
        elif path == "/":
            page = await self.catalogue.search(CatalogueFilters(page_size=6))
            response = WebResponse.html(200, self.renderer.home(page))
        elif path == "/vagas":
            try:
                filters = self._filters(query)
            except (ValidationError, ValueError):
                return self._error(400, "Filtro inválido")
            response = WebResponse.html(200, self.renderer.catalogue(await self.catalogue.search(filters), filters))
        elif path.startswith("/vagas/"):
            match = _JOB_PATH.fullmatch(path)
            if not match:
                response = WebResponse.html(404, self.renderer.unavailable())
            else:
                job = await self.catalogue.detail(int(match.group(1)))
                response = (
                    WebResponse.html(200, self.renderer.detail(job))
                    if job
                    else WebResponse.html(404, self.renderer.unavailable(removed=True))
                )
        elif path.startswith("/go/"):
            response = await self._redirect(path)
        elif path == "/sobre":
            response = WebResponse.html(200, self.renderer.about())
        elif path == "/contato":
            response = WebResponse.html(200, self.renderer.contact(self._query_job_id(query)))
        elif path == "/privacidade":
            response = WebResponse.html(200, self.renderer.privacy())
        elif path == "/termos":
            response = WebResponse.html(200, self.renderer.terms())
        else:
            response = WebResponse.html(404, self.renderer.unavailable())
        if method == "HEAD":
            return WebResponse(response.status, b"", response.content_type, response.headers)
        return response

    async def _redirect(self, path: str) -> WebResponse:
        match = re.fullmatch(r"/go/([1-9][0-9]*)", path)
        if not match:
            return WebResponse.html(404, self.renderer.unavailable())
        destination = await self.publications.destination(int(match.group(1)))
        if not destination:
            return WebResponse.html(410, self.renderer.unavailable(removed=True))
        return WebResponse(303, b"", headers={"Location": destination, "Cache-Control": "no-store"})

    async def _sitemap(self) -> WebResponse:
        rows: list[dict[str, Any]] = []
        after = 0
        while True:
            batch = await self.catalogue.sitemap_batch(after_id=after, limit=5000)
            if not batch:
                break
            rows.extend(batch)
            after = batch[-1]["id"]
            if len(batch) < 5000:
                break
        urls = "".join(self._sitemap_url(row) for row in rows)
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
            + urls
            + "</urlset>"
        )
        return WebResponse(200, xml.encode(), content_type="application/xml; charset=utf-8")

    def _sitemap_url(self, row: dict[str, Any]) -> str:
        lastmod = f"<lastmod>{escape(row['updated_at'])}</lastmod>" if row.get("updated_at") else ""
        return f"<url><loc>{escape(self.renderer.base_url + row['path'])}</loc>{lastmod}</url>"

    def _static(self, relative: str) -> WebResponse:
        candidate = (self.static_dir / relative).resolve()
        try:
            candidate.relative_to(self.static_dir)
        except ValueError:
            return self._error(404, "Recurso não encontrado")
        if not candidate.is_file():
            return self._error(404, "Recurso não encontrado")
        media = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        content_type = f"{media}; charset=utf-8" if media.startswith("text/") else media
        return WebResponse(
            200,
            candidate.read_bytes(),
            content_type=content_type,
            headers={"Cache-Control": "public, max-age=86400"},
        )

    async def _internal(
        self,
        method: str,
        path: str,
        query: str,
        headers: dict[str, str],
        body: bytes,
    ) -> WebResponse:
        if headers.get("authorization", "") != f"Bearer {self.internal_token}":
            return self._error(401, "Não autorizado")
        actor = headers.get("x-telegram-actor", "")
        if not actor or len(actor) > 255 or any(char in actor for char in "\r\n"):
            return self._error(403, "Ator não autorizado")
        try:
            if method == "POST" and re.fullmatch(r"/internal/jobs/[1-9][0-9]*/publication-preview", path):
                job_id = int(path.split("/")[3])
                data = self._json(body)
                preview = await self.publications.preview(
                    job_id,
                    actor=actor,
                    destination_type=str(data["destination_type"]),
                    summary=str(data["summary"]),
                )
                destination = preview.snapshot["destination"]
                return WebResponse.json(
                    200,
                    {
                        "token": preview.token,
                        "job_id": preview.job_id,
                        "expected_version": preview.expected_version,
                        "public": preview.snapshot["public"],
                        "destination_type": destination["type"],
                        "destination_url": destination["url"],
                        "expires_at": preview.expires_at.isoformat(),
                    },
                )
            if method == "POST" and re.fullmatch(r"/internal/site-previews/[a-f0-9]{24}/confirm", path):
                token = path.rsplit("/", 2)[1]
                result = await self.publications.confirm(token, actor=actor)
                return WebResponse.json(200, await self.publications.status(result.job_id, actor=actor))
            status_match = _ID_PATH.fullmatch(path)
            if method == "GET" and status_match:
                return WebResponse.json(200, await self.publications.status(int(status_match.group(1)), actor=actor))
            if method == "GET" and path == "/internal/jobs":
                params = parse_qs(query, keep_blank_values=True)
                status = params.get("site_status", ["NAO_PUBLICADA"])[0]
                page = int(params.get("page", ["1"])[0])
                return WebResponse.json(200, {"items": await self.publications.listing(status=status, page=page, actor=actor)})
            if method == "POST" and re.fullmatch(r"/internal/jobs/[1-9][0-9]*/unpublish", path):
                job_id = int(path.split("/")[3])
                data = self._json(body)
                result = await self.publications.unpublish(
                    job_id,
                    actor=actor,
                    expected_version=int(data["expected_version"]),
                    event_id=str(data["event_id"]),
                    reason=str(data["reason"]),
                )
                return WebResponse.json(200, await self.publications.status(result.job_id, actor=actor))
            if method == "POST" and re.fullmatch(r"/internal/jobs/[1-9][0-9]*/requirements", path):
                job_id = int(path.split("/")[3])
                data = self._json(body)
                requirements = JobRequirements.model_validate(data["requirements"])
                return WebResponse.json(
                    200,
                    await self.publications.set_requirements(job_id, actor=actor, requirements=requirements),
                )
        except PublicationConflict as error:
            return self._error(409, str(error))
        except PublicationRejected as error:
            return self._error(422, str(error))
        except (KeyError, TypeError, ValueError, ValidationError, json.JSONDecodeError):
            return self._error(400, "Dados inválidos")
        return self._error(404, "Rota não encontrada")

    @staticmethod
    def _json(body: bytes) -> dict[str, Any]:
        value = json.loads(body or b"{}")
        if not isinstance(value, dict):
            raise ValueError("Objeto JSON obrigatório")
        return value

    @staticmethod
    def _filters(query: str) -> CatalogueFilters:
        values = {key: entries[-1] for key, entries in parse_qs(query, keep_blank_values=True).items()}
        if "salary_available" in values:
            values["salary_available"] = values["salary_available"].lower() in {"1", "true", "on"}
        return CatalogueFilters(**values)

    @staticmethod
    def _query_job_id(query: str) -> int | None:
        value = parse_qs(query).get("vaga", [None])[0]
        return int(value) if value and value.isdigit() else None

    @staticmethod
    def _error(status: int, message: str, *, headers: dict[str, str] | None = None) -> WebResponse:
        response = WebResponse.json(status, {"error": message})
        if headers:
            return WebResponse(response.status, response.body, response.content_type, headers)
        return response


async def serve(app: PortalApplication, *, host: str = "127.0.0.1", port: int = 8080) -> None:
    server = await asyncio.start_server(
        lambda reader, writer: _serve_connection(app, reader, writer), host, port
    )
    async with server:
        await server.serve_forever()


async def _serve_connection(
    app: PortalApplication, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
) -> None:
    try:
        header_bytes = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), timeout=15)
        if len(header_bytes) > MAX_REQUEST_BYTES:
            response = app._error(413, "Requisição muito grande")
        else:
            lines = header_bytes.decode("latin-1").split("\r\n")
            request = lines[0].split(" ", 2)
            if len(request) != 3:
                response = app._error(400, "Requisição inválida")
            else:
                headers: dict[str, str] = {}
                for line in lines[1:-2]:
                    if ":" in line:
                        key, value = line.split(":", 1)
                        key = key.strip().lower()
                        if key in headers:
                            raise ValueError("Cabeçalho duplicado")
                        headers[key] = value.strip()
                if "transfer-encoding" in headers:
                    raise ValueError("Transfer-Encoding não suportado")
                content_length = int(headers.get("content-length", "0"))
                if content_length < 0 or content_length > MAX_BODY_BYTES:
                    response = app._error(413, "Corpo da requisição muito grande")
                else:
                    body = await asyncio.wait_for(reader.readexactly(content_length), timeout=15)
                    response = await app.handle(request[0], request[1], headers=headers, body=body)
    except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, UnicodeError, ValueError, TimeoutError):
        response = app._error(400, "Requisição inválida")
    except Exception:
        response = app._error(500, "Erro interno")
    response_headers = {
        "Content-Type": response.content_type,
        "Content-Length": str(len(response.body)),
        "Connection": "close",
        "Cache-Control": (
            "public, max-age=60"
            if response.content_type.startswith(("text/html", "application/xml"))
            else "no-store"
        ),
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Content-Security-Policy": "default-src 'self'; img-src 'self'; style-src 'self'; script-src 'self'",
    }
    response_headers.update(response.headers or {})
    status_text = {
        200: "OK", 301: "Moved Permanently", 303: "See Other", 400: "Bad Request",
        401: "Unauthorized", 403: "Forbidden", 404: "Not Found", 405: "Method Not Allowed",
        409: "Conflict", 410: "Gone", 413: "Payload Too Large", 415: "Unsupported Media Type", 422: "Unprocessable Entity", 429: "Too Many Requests",
        500: "Internal Server Error",
    }.get(response.status, "Error")
    writer.write(
        (
            f"HTTP/1.1 {response.status} {status_text}\r\n"
            + "".join(f"{key}: {value}\r\n" for key, value in response_headers.items())
            + "\r\n"
        ).encode()
        + response.body
    )
    await writer.drain()
    writer.close()
    await writer.wait_closed()
