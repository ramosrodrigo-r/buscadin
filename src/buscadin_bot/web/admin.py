"""Single-operator administration, served only on loopback behind an SSH tunnel.

Browser sessions never receive the internal API token or database credentials.
Run one process; sessions expire after eight hours and on process restart.
"""

import asyncio
from dataclasses import asdict
from datetime import datetime, timedelta
import hashlib
from http.cookies import SimpleCookie
import json
import os
from pathlib import Path
import secrets
import time
from typing import Literal
from urllib.parse import parse_qs, urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, model_validator
from sqlalchemy import and_, func, or_, select

from buscadin_bot.config import get_settings
from buscadin_bot.db.models import AuditEvent, CarouselDraft, Job, ReferralProgram, ReferralLink, SitePublication, SitePublicationEvent, utcnow
from buscadin_bot.db.session import create_engine, create_session_factory
from buscadin_bot.services.catalogue import PublicCatalogue
from buscadin_bot.services.collector import Collector
from buscadin_bot.services.crawl_runs import CrawlRuns
from buscadin_bot.services.publication_policy import PublicationRejected, validate_destination
from buscadin_bot.services.requirements import JobRequirements
from buscadin_bot.services.referrals import ReferralResolver
from buscadin_bot.services.site_publications import PublicationConflict, SitePublicationService
from buscadin_bot.sources.himalayas import HimalayasSource
from buscadin_bot.web.server import MAX_BODY_BYTES, PortalApplication, WebResponse, serve


class JobDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=500)
    company: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=50000)
    source_url: str = Field(max_length=2048)
    application_url: str = Field(max_length=2048)
    category: str = Field(default="other", min_length=1, max_length=100)
    eligibility_status: Literal["unknown", "confirmed_br", "excluded_br"] = "unknown"
    evidence: str = Field(default="", max_length=4000)
    status: Literal["active", "closed"] = "active"
    editorial_status: Literal["NOVA", "SELECIONADA", "PRONTA", "PUBLICADA", "DESCARTADA"] = "NOVA"
    requirements: JobRequirements = Field(default_factory=JobRequirements)
    salary_min: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    salary_max: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    currency: str | None = Field(default=None, max_length=16)
    salary_period: str | None = Field(default=None, max_length=32)
    language_requirements: list[str] = Field(default_factory=list, max_length=20)
    employment_type: str | None = Field(default=None, max_length=100)
    remote_type: str = Field(default="remote", max_length=100)

    @model_validator(mode="after")
    def validate_facts(self):
        for url in (self.source_url, self.application_url):
            validate_destination(url, [urlsplit(url).hostname or ""])
        if self.eligibility_status != "unknown" and not self.evidence:
            raise ValueError("Informe a evidência da elegibilidade para o Brasil")
        if self.salary_min is not None and self.salary_max is not None and self.salary_max < self.salary_min:
            raise ValueError("O salário máximo deve ser maior ou igual ao mínimo")
        if any(len(language) > 100 for language in self.language_requirements):
            raise ValueError("Idioma muito extenso")
        return self


class ProgramDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    company: str = Field(min_length=1, max_length=255)
    name: str = Field(min_length=1, max_length=255)
    scope_type: Literal["GLOBAL", "POR_VAGA", "POR_PROJETO"] = "GLOBAL"
    campaign_key: str | None = Field(default=None, max_length=255)
    allowed_domains: list[str] = Field(min_length=1, max_length=30)
    public_sharing_allowed: bool = False
    evidence_url: str = Field(max_length=2048)
    rules_notes: str = Field(default="", max_length=10000)

    @model_validator(mode="after")
    def validate_rules(self):
        validate_destination(self.evidence_url, [urlsplit(self.evidence_url).hostname or ""])
        for domain in self.allowed_domains:
            validate_destination("https://" + domain + "/", [domain])
        if self.scope_type == "POR_PROJETO" and not self.campaign_key:
            raise ValueError("Informe a campanha do programa por projeto")
        return self


class LinkDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    program_id: int = Field(gt=0)
    job_id: int | None = Field(default=None, gt=0)
    campaign_key: str | None = Field(default=None, max_length=255)
    url: str = Field(max_length=2048)
    expires_at: datetime | None = None
    official_confirmed: Literal[True]


class CarouselRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    job_ids: list[int] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def unique_ids(self):
        if len(set(self.job_ids)) != len(self.job_ids):
            raise ValueError("Selecione cada vaga apenas uma vez")
        return self


class CarouselSlideDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    type: Literal["cover", "job", "closing"]
    job_id: int | None = None
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=320)


class CarouselResultDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    caption: str = Field(min_length=1, max_length=2200)
    slides: list[CarouselSlideDraft] = Field(min_length=3, max_length=10)


class CarouselCompletion(BaseModel):
    model_config = ConfigDict(extra="forbid")
    draft_id: int = Field(gt=0)
    result: CarouselResultDraft


class CarouselWorkerFailure(BaseModel):
    model_config = ConfigDict(extra="forbid")
    draft_id: int = Field(gt=0)
    code: Literal["generation_failed", "invalid_output", "timeout"]


class CarouselPostedRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    draft_id: int = Field(gt=0)
    post_url: str | None = Field(default=None, max_length=2048)

    @model_validator(mode="after")
    def validate_post_url(self):
        if self.post_url:
            parsed = urlsplit(self.post_url)
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError("O link do post precisa ser HTTPS")
        return self


def validate_carousel_result(result: CarouselResultDraft, job_snapshot: list[dict]) -> dict:
    slides = result.slides
    expected_ids = [item["id"] for item in job_snapshot]
    if slides[0].type != "cover" or slides[-1].type != "closing":
        raise ValueError("O carrossel precisa começar com capa e terminar com encerramento")
    job_slides = slides[1:-1]
    if any(slide.type != "job" for slide in job_slides):
        raise ValueError("O carrossel precisa ter uma lâmina por vaga")
    if [slide.job_id for slide in job_slides] != expected_ids:
        raise ValueError("As lâminas geradas não correspondem às vagas selecionadas")
    canonical_titles = {job["id"]: job["title"] for job in job_snapshot}
    for slide in job_slides:
        slide.title = canonical_titles[slide.job_id]
    return result.model_dump()


def serialize(model):
    return {column.name: (value.isoformat() if isinstance(value := getattr(model, column.name), datetime) else value)
            for column in model.__table__.columns}


def revision(job):
    return hashlib.sha256(json.dumps(serialize(job), sort_keys=True).encode()).hexdigest()


class AdminApplication:
    _error = staticmethod(PortalApplication._error)

    def __init__(self, sessions, settings, password: str, *, origin="http://127.0.0.1:8081"):
        if len(password) < 20:
            raise ValueError("Senha administrativa deve ter pelo menos 20 caracteres")
        parsed = urlsplit(origin)
        loopback_http = parsed.scheme == "http" and parsed.hostname in {"127.0.0.1", "localhost"}
        protected_https = parsed.scheme == "https" and bool(parsed.hostname and "." in parsed.hostname)
        if (
            not (loopback_http or protected_https)
            or parsed.path
            or parsed.query
            or parsed.fragment
            or parsed.username
            or parsed.password
            or (parsed.scheme == "https" and parsed.port not in {None, 443})
        ):
            raise ValueError("Use origem HTTP loopback ou HTTPS com hostname completo")
        self.origin = origin
        self.host = parsed.netloc
        self.secure_cookies = parsed.scheme == "https"
        self.sessions = sessions
        self.settings = settings
        self.worker_token = (settings.carousel_worker_token.get_secret_value()
                             if settings.carousel_worker_token else "")
        if self.worker_token and len(self.worker_token) < 40:
            raise ValueError("CAROUSEL_WORKER_TOKEN precisa ter pelo menos 40 caracteres")
        self.salt = secrets.token_bytes(16)
        self.password_hash = self._hash(password)
        self.tokens = {}
        self.failures = []
        self.collect_lock = asyncio.Lock()
        self.crawls = CrawlRuns(sessions)
        self.publications = SitePublicationService(sessions, admin_actor="admin:web", official_domains=[
            item.strip() for item in settings.site_official_domains.split(",") if item.strip()
        ])
        self.portal = PortalApplication(PublicCatalogue(sessions, self.publications), self.publications,
                                        internal_token=secrets.token_urlsafe(32))

    def _hash(self, password):
        return hashlib.scrypt(password.encode(), salt=self.salt, n=16384, r=8, p=1)

    async def handle(self, method, target, *, headers=None, body=b""):
        headers = {key.lower(): value for key, value in (headers or {}).items()}
        response = await self._handle(method, target, headers, body)
        return WebResponse(response.status, response.body, response.content_type, {
            **(response.headers or {}), "Cache-Control": "no-store", "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer", "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
        })

    async def _handle(self, method, target, headers, body):
        if headers.get("host") != self.host:
            return self._error(403, "Origem de acesso não autorizada")
        if len(body) > MAX_BODY_BYTES:
            return self._error(413, "Requisição muito grande")
        if method not in {"GET", "POST"}:
            return self._error(405, "Método não permitido")
        try:
            url = urlsplit(target)
            if url.scheme or url.netloc:
                raise ValueError("URL inválida")
            path = url.path
            if path.startswith("/api/worker/carousels/"):
                expected = "Bearer " + self.worker_token if self.worker_token else ""
                if not expected or not secrets.compare_digest(headers.get("authorization", ""), expected):
                    return self._error(404, "Rota não encontrada")
                if method != "POST" or headers.get("content-type", "").split(";")[0] != "application/json":
                    return self._error(405, "Método não permitido")
                return await self._worker_api(path, body)
            if method == "GET" and path in {"/", "/login"}:
                return WebResponse.html(200, (Path(__file__).parent / "admin_static/index.html").read_text())
            if method == "GET" and path.startswith("/assets/"):
                name = path.removeprefix("/assets/")
                if name not in {"admin.css", "admin.js"}:
                    return self._error(404, "Recurso não encontrado")
                return WebResponse(200, (Path(__file__).parent / "admin_static" / name).read_bytes(),
                                   "text/css" if name.endswith("css") else "text/javascript")
            if method == "GET" and path in {"/static/portal.css", "/static/logo.jpg", "/static/fonts/InterVariable.woff2"}:
                return self.portal._static(path.removeprefix("/static/"))
            if method == "POST" and headers.get("origin") != self.origin:
                return self._error(403, "Origem da ação não autorizada")
            if method == "POST" and headers.get("content-type", "").split(";")[0] != "application/json":
                return self._error(415, "Envie JSON")
            now = time.monotonic()
            self.tokens = {key: value for key, value in self.tokens.items() if value[1] > now}
            if path == "/api/login" and method == "POST":
                self.failures = [stamp for stamp in self.failures if stamp > now - 300]
                if len(self.failures) >= 5:
                    return self._error(429, "Muitas tentativas. Aguarde cinco minutos.")
                data = self.portal._json(body)
                password = data.get("password", "")
                if not isinstance(password, str) or len(password) > 1024:
                    raise ValueError("Senha inválida")
                self.failures.append(now)
                digest = await asyncio.to_thread(self._hash, password)
                if not secrets.compare_digest(digest, self.password_hash):
                    return self._error(401, "Senha incorreta")
                self.failures.clear()
                token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
                if len(self.tokens) >= 10:
                    self.tokens.pop(next(iter(self.tokens)))
                self.tokens[token] = (csrf, now + 28800)
                secure = "; Secure" if self.secure_cookies else ""
                return WebResponse(200, json.dumps({"csrf": csrf}).encode(), "application/json", {
                    "Set-Cookie": f"buscadin_admin={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800{secure}"
                })
            cookie = SimpleCookie()
            cookie.load(headers.get("cookie", ""))
            token = cookie["buscadin_admin"].value if "buscadin_admin" in cookie else ""
            session = self.tokens.get(token)
            if not session:
                return self._error(401, "Entre para continuar")
            if method == "POST" and not secrets.compare_digest(headers.get("x-csrf-token", ""), session[0]):
                return self._error(403, "Sessão inválida. Atualize a página.")
            if path == "/api/session" and method == "GET":
                return WebResponse.json(200, {"csrf": session[0]})
            if path == "/api/logout" and method == "POST":
                self.tokens.pop(token, None)
                secure = "; Secure" if self.secure_cookies else ""
                return WebResponse(200, b"{}", "application/json", {
                    "Set-Cookie": f"buscadin_admin=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0{secure}"
                })
            return await self._api(method, path, url.query, body)
        except PublicationConflict as error:
            return self._error(409, str(error))
        except ValidationError as error:
            return self._error(422, "; ".join(f"{'.'.join(map(str, entry['loc']))}: {entry['msg']}" for entry in error.errors()))
        except (ValueError, KeyError, TypeError) as error:
            return self._error(422, str(error)[:500])

    async def _api(self, method, path, query, body):
        if path == "/api/carousel/jobs" and method == "GET":
            async with self.sessions() as session:
                used = (await session.scalars(select(CarouselDraft.job_ids).where(
                    CarouselDraft.status.in_(["queued", "generating", "draft", "posted"])
                ))).all()
                used_ids = {job_id for group in used for job_id in group}
                rows = (await session.scalars(
                    select(Job).where(
                        Job.status == "active",
                        Job.eligibility_status != "excluded_br",
                        Job.editorial_status != "DESCARTADA",
                        Job.id.not_in(used_ids) if used_ids else True,
                    ).order_by(Job.id.desc()).limit(200)
                )).all()
                return WebResponse.json(200, {"items": [self._carousel_job_snapshot(job) for job in rows]})
        if path == "/api/carousels" and method == "GET":
            async with self.sessions() as session:
                drafts = (await session.scalars(
                    select(CarouselDraft).order_by(CarouselDraft.id.desc()).limit(30)
                )).all()
                return WebResponse.json(200, {"items": [serialize(draft) for draft in drafts]})
        if path == "/api/carousels" and method == "POST":
            request = CarouselRequest.model_validate(self.portal._json(body))
            async with self.sessions.begin() as session:
                jobs = (await session.scalars(
                    select(Job).where(Job.id.in_(request.job_ids)).order_by(Job.id).with_for_update()
                )).all()
                by_id = {job.id: job for job in jobs}
                if set(by_id) != set(request.job_ids):
                    raise ValueError("Uma ou mais vagas não existem mais")
                if any(job.status != "active" or job.eligibility_status == "excluded_br"
                       or job.editorial_status == "DESCARTADA" for job in jobs):
                    raise ValueError("Remova vagas encerradas, incompatíveis com o Brasil ou descartadas")
                used = (await session.scalars(select(CarouselDraft.job_ids).where(
                    CarouselDraft.status.in_(["queued", "generating", "draft", "posted"])
                ))).all()
                used_ids = {job_id for group in used for job_id in group}
                if used_ids.intersection(request.job_ids):
                    raise ValueError("Uma vaga selecionada já faz parte de outro carrossel não descartado")
                snapshot = [self._carousel_job_snapshot(by_id[job_id]) for job_id in request.job_ids]
                draft = CarouselDraft(
                    job_ids=request.job_ids, job_snapshot=snapshot, requested_by="admin:web",
                    status="queued", created_at=utcnow(), updated_at=utcnow(),
                )
                session.add(draft)
                await session.flush()
                session.add(AuditEvent(event_type="admin_carousel_request", actor="admin:web",
                                       after_json={"carousel_id": draft.id, "job_ids": request.job_ids}))
                return WebResponse.json(200, serialize(draft))
        if path == "/api/carousels/posted" and method == "POST":
            request = CarouselPostedRequest.model_validate(self.portal._json(body))
            async with self.sessions.begin() as session:
                draft = await session.get(CarouselDraft, request.draft_id, with_for_update=True)
                if not draft or draft.status != "draft":
                    return self._error(409, "Somente um rascunho revisado pode ser marcado como postado")
                draft.status, draft.posted_at = "posted", utcnow()
                draft.post_url, draft.updated_at = request.post_url, utcnow()
                session.add(AuditEvent(event_type="admin_carousel_posted", actor="admin:web",
                                       after_json={"carousel_id": draft.id, "post_url": request.post_url,
                                                   "job_ids": draft.job_ids}))
                return WebResponse.json(200, serialize(draft))
        if path == "/api/carousels/edit" and method == "POST":
            data = self.portal._json(body)
            draft_id = int(data.get("draft_id", 0))
            async with self.sessions.begin() as session:
                draft = await session.get(CarouselDraft, draft_id, with_for_update=True)
                if not draft or draft.status != "draft":
                    return self._error(409, "O rascunho não está disponível para edição")
                result = CarouselResultDraft.model_validate(data.get("result"))
                draft.result = validate_carousel_result(result, draft.job_snapshot)
                draft.updated_at = utcnow()
                session.add(AuditEvent(event_type="admin_carousel_edit", actor="admin:web",
                                       after_json={"carousel_id": draft.id}))
                return WebResponse.json(200, serialize(draft))
        if path == "/api/carousels/retry" and method == "POST":
            draft_id = int(self.portal._json(body).get("draft_id", 0))
            async with self.sessions.begin() as session:
                draft = await session.get(CarouselDraft, draft_id, with_for_update=True)
                if not draft or draft.status != "failed":
                    return self._error(409, "Somente uma geração com falha pode ser tentada novamente")
                draft.status, draft.error_message = "queued", None
                draft.claimed_at, draft.updated_at = None, utcnow()
                session.add(AuditEvent(event_type="admin_carousel_retry", actor="admin:web",
                                       after_json={"carousel_id": draft.id}))
                return WebResponse.json(200, serialize(draft))
        if path == "/api/carousels/discard" and method == "POST":
            draft_id = int(self.portal._json(body).get("draft_id", 0))
            async with self.sessions.begin() as session:
                draft = await session.get(CarouselDraft, draft_id, with_for_update=True)
                if not draft or draft.status not in {"queued", "draft", "failed"}:
                    return self._error(409, "Este pedido não pode ser descartado neste estado")
                draft.status, draft.updated_at = "discarded", utcnow()
                session.add(AuditEvent(event_type="admin_carousel_discard", actor="admin:web",
                                       after_json={"carousel_id": draft.id, "job_ids": draft.job_ids}))
                return WebResponse.json(200, serialize(draft))
        if path == "/api/crawl" and method == "GET":
            return WebResponse.json(200, await self.crawls.status())
        if path == "/api/crawl" and method == "POST":
            data = self.portal._json(body)
            try:
                state = await self.crawls.start(data.get("source", "all"))
            except RuntimeError as error:
                return self._error(409, str(error))
            return WebResponse.json(200, state)
        if path == "/api/referrals" and method == "GET":
            async with self.sessions() as session:
                programs = (await session.scalars(select(ReferralProgram).order_by(ReferralProgram.id.desc()).limit(200))).all()
                links = (await session.scalars(select(ReferralLink).order_by(ReferralLink.id.desc()).limit(200))).all()
                return WebResponse.json(200, {"programs": [serialize(p) for p in programs], "links": [serialize(link) for link in links]})
        if path == "/api/programs" and method == "POST":
            draft = ProgramDraft.model_validate(self.portal._json(body))
            async with self.sessions.begin() as session:
                program = ReferralProgram(**draft.model_dump())
                session.add(program)
                await session.flush()
                session.add(AuditEvent(event_type="admin_program_create", actor="admin:web", after_json=serialize(program)))
                return WebResponse.json(200, {"id": program.id})
        if path == "/api/links" and method == "POST":
            draft = LinkDraft.model_validate(self.portal._json(body))
            async with self.sessions.begin() as session:
                program = await session.get(ReferralProgram, draft.program_id)
                if not program or not program.is_active:
                    raise ValueError("Programa inexistente ou inativo")
                validate_destination(draft.url, program.allowed_domains)
                job = await session.get(Job, draft.job_id) if draft.job_id else None
                if draft.job_id and (not job or job.company != program.company):
                    raise ValueError("A vaga deve existir e pertencer à empresa do programa")
                if program.scope_type == "POR_VAGA" and not job:
                    raise ValueError("Informe a vaga para este programa")
                if program.scope_type == "POR_PROJETO" and draft.campaign_key != program.campaign_key:
                    raise ValueError("Campanha incompatível com o programa")
                if draft.expires_at and (draft.expires_at.tzinfo is None or draft.expires_at <= utcnow()):
                    raise ValueError("Validade deve ser futura e conter fuso horário")
                link = ReferralLink(**draft.model_dump(exclude={"official_confirmed"}), source="MANUAL", verified_at=utcnow(), verified_by="admin:web")
                session.add(link)
                await session.flush()
                if job:
                    await ReferralResolver().apply_resolution(session, job, actor="admin:web")
                session.add(AuditEvent(event_type="admin_link_create", actor="admin:web", after_json=serialize(link)))
                return WebResponse.json(200, {"id": link.id})
        if path == "/api/referrals/disable" and method == "POST":
            data = self.portal._json(body)
            model = {"program": ReferralProgram, "link": ReferralLink}.get(data.get("kind"))
            if model is None:
                raise ValueError("Tipo inválido")
            async with self.sessions.begin() as session:
                row = await session.get(model, int(data["id"]), with_for_update=True)
                if row is None:
                    raise ValueError("Registro não encontrado")
                before = serialize(row)
                row.is_active = False
                session.add(AuditEvent(event_type="admin_referral_disable", actor="admin:web", before_json=before, after_json=serialize(row)))
            await self.publications.reconcile()
            return WebResponse.json(200, {"ok": True})
        if path.startswith("/api/internal/"):
            return await self.portal.handle(method, path.removeprefix("/api") + ("?" + query if query else ""),
                headers={"Authorization": f"Bearer {self.portal.internal_token}", "X-Telegram-Actor": "admin:web"}, body=body)
        if path == "/api/settings" and method == "GET":
            return WebResponse.json(200, {"official_domains": self.publications.official_domains,
                "source": "Himalayas", "batch_size": 20, "interval_hours": self.settings.collect_interval_hours,
                "note": "A agenda automática depende do processo do bot. O painel permite coleta manual."})
        if path == "/api/collect" and method == "POST":
            if self.collect_lock.locked():
                return self._error(409, "Uma coleta já está em andamento")
            async with self.collect_lock:
                async with HimalayasSource(self.settings) as source, self.sessions() as session:
                    result = await Collector().collect_source(session, source)
                payload = asdict(result)
                if result.error:
                    payload["error"] = "A fonte não respondeu como esperado. Consulte os logs do serviço."
                async with self.sessions.begin() as session:
                    session.add(AuditEvent(event_type="admin_collection", actor="admin:web", after_json=payload))
                return WebResponse.json(502 if result.failed else 200, payload)
        if path == "/api/audit" and method == "GET":
            async with self.sessions() as session:
                general = (await session.scalars(select(AuditEvent).order_by(AuditEvent.id.desc()).limit(100))).all()
                publication = (await session.scalars(select(SitePublicationEvent).order_by(SitePublicationEvent.id.desc()).limit(100))).all()
                return WebResponse.json(200, {"events": [serialize(row) for row in general], "publications": [serialize(row) for row in publication]})
        if path == "/api/jobs" and method == "GET":
            params = parse_qs(query)
            page = max(1, min(100000, int(params.get("page", [1])[0])))
            search = params.get("q", [""])[0][:200]
            state = params.get("state", [""])[0]
            statement = select(Job, SitePublication).outerjoin(SitePublication, SitePublication.job_id == Job.id)
            if search:
                statement = statement.where(or_(Job.title.icontains(search, autoescape=True), Job.company.icontains(search, autoescape=True)))
            if state == "PUBLICADA":
                statement = statement.where(SitePublication.status == "PUBLICADA")
            elif state:
                statement = statement.where(Job.editorial_status == state)
            async with self.sessions() as session:
                total = await session.scalar(select(func.count()).select_from(statement.subquery()))
                rows = (await session.execute(statement.order_by(Job.id.desc()).offset((page - 1) * 30).limit(30))).all()
                items = [{**serialize(job), "revision": revision(job), "publication": serialize(pub) if pub else None} for job, pub in rows]
                return WebResponse.json(200, {"items": items, "total": total, "page": page})
        if path == "/api/jobs" and method == "POST":
            draft = JobDraft.model_validate(self.portal._json(body))
            async with self.sessions.begin() as session:
                job = Job(source="manual", source_job_id=secrets.token_hex(16))
                self._apply(job, draft)
                session.add(job)
                await session.flush()
                session.add(AuditEvent(job_id=job.id, event_type="admin_create", actor="admin:web", after_json=serialize(job)))
                return WebResponse.json(200, {"id": job.id})
        parts = path.split("/")
        if len(parts) == 4 and parts[1:3] == ["api", "jobs"] and parts[3].isdigit():
            async with self.sessions.begin() as session:
                job = await session.get(Job, int(parts[3]), with_for_update=method == "POST")
                if job is None:
                    return self._error(404, "Vaga não encontrada")
                if method == "POST":
                    data = self.portal._json(body)
                    expected = data.pop("revision", "")
                    if expected != revision(job):
                        return self._error(409, "A vaga mudou. Reabra antes de salvar.")
                    draft = JobDraft.model_validate(data)
                    before = serialize(job)
                    self._apply(job, draft)
                    session.add(AuditEvent(job_id=job.id, event_type="admin_edit", actor="admin:web", before_json=before, after_json=serialize(job)))
                pub = await session.get(SitePublication, job.id)
                return WebResponse.json(200, {**serialize(job), "revision": revision(job), "publication": serialize(pub) if pub else None})
        return self._error(404, "Rota não encontrada")

    @staticmethod
    def _carousel_job_snapshot(job: Job) -> dict:
        return {
            "id": job.id,
            "title": job.title,
            "company": job.company,
            "category": job.category,
            "eligibility_status": job.eligibility_status,
            "eligibility_evidence": job.evidence or "",
            "remote_type": job.remote_type or "Não informado",
            "employment_type": job.employment_type or "Não informado",
            "salary_min": job.salary_min if job.salary_disclosed else None,
            "salary_max": job.salary_max if job.salary_disclosed else None,
            "currency": job.currency if job.salary_disclosed else None,
            "salary_period": job.salary_period if job.salary_disclosed else None,
            "languages": job.language_requirements or [],
            "requirements": job.requirements or {},
            "source_url": job.source_url,
        }

    async def _worker_api(self, path: str, body: bytes) -> WebResponse:
        now = utcnow()
        if path == "/api/worker/carousels/claim":
            stale_before = now - timedelta(minutes=15)
            async with self.sessions.begin() as session:
                draft = await session.scalar(
                    select(CarouselDraft).where(or_(
                        CarouselDraft.status == "queued",
                        and_(CarouselDraft.status == "generating", CarouselDraft.claimed_at < stale_before),
                    )).order_by(CarouselDraft.id).limit(1).with_for_update(skip_locked=True)
                )
                if draft is None:
                    return WebResponse.json(200, {"draft": None})
                if draft.attempts >= 4:
                    draft.status = "failed"
                    draft.error_message = "Limite de tentativas atingido. Solicite nova tentativa no painel."
                    draft.updated_at = now
                    return WebResponse.json(200, {"draft": None})
                draft.status, draft.claimed_at = "generating", now
                draft.attempts += 1
                draft.updated_at = now
                return WebResponse.json(200, {"draft_id": draft.id, "jobs": draft.job_snapshot})
        if path == "/api/worker/carousels/complete":
            request = CarouselCompletion.model_validate(self.portal._json(body))
            async with self.sessions.begin() as session:
                draft = await session.get(CarouselDraft, request.draft_id, with_for_update=True)
                if not draft or draft.status != "generating":
                    return self._error(409, "Solicitação não está em geração")
                draft.result = validate_carousel_result(request.result, draft.job_snapshot)
                draft.status, draft.error_message = "draft", None
                draft.claimed_at, draft.updated_at = None, now
                session.add(AuditEvent(event_type="carousel_generated", actor="homelab:carousel-worker",
                                       after_json={"carousel_id": draft.id, "attempt": draft.attempts}))
                return WebResponse.json(200, {"ok": True})
        if path == "/api/worker/carousels/fail":
            request = CarouselWorkerFailure.model_validate(self.portal._json(body))
            async with self.sessions.begin() as session:
                draft = await session.get(CarouselDraft, request.draft_id, with_for_update=True)
                if not draft or draft.status != "generating":
                    return self._error(409, "Solicitação não está em geração")
                draft.status = "failed" if draft.attempts >= 4 else "queued"
                draft.error_message = {
                    "generation_failed": "Não foi possível concluir a geração.",
                    "invalid_output": "A resposta da IA não passou pela validação.",
                    "timeout": "A geração excedeu o tempo limite.",
                }[request.code]
                draft.claimed_at, draft.updated_at = None, now
                session.add(AuditEvent(event_type="carousel_generation_failed", actor="homelab:carousel-worker",
                                       after_json={"carousel_id": draft.id, "code": request.code,
                                                   "status": draft.status}))
                return WebResponse.json(200, {"ok": True, "status": draft.status})
        return self._error(404, "Rota não encontrada")

    @staticmethod
    def _apply(job, draft):
        for key, value in draft.model_dump().items():
            setattr(job, key, value)
        job.eligible_countries = ["BR"] if draft.eligibility_status == "confirmed_br" else []
        job.salary_disclosed = draft.salary_min is not None or draft.salary_max is not None
        job.review_status = "admin_curated"


async def run():
    settings = get_settings()
    worker_token_file = os.environ.get("CAROUSEL_WORKER_TOKEN_FILE")
    if worker_token_file:
        token_path = Path(worker_token_file)
        worker_token = token_path.read_text().strip()
        if len(worker_token) < 40:
            raise ValueError("CAROUSEL_WORKER_TOKEN_FILE precisa conter um segredo válido")
        settings.carousel_worker_token = SecretStr(worker_token)
    password = os.environ.get("ADMIN_PASSWORD")
    if not password:
        password_file = Path("data/admin-password")
        password_file.parent.mkdir(parents=True, exist_ok=True)
        if not password_file.exists():
            descriptor = os.open(password_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w") as stream:
                stream.write(secrets.token_urlsafe(32))
        if password_file.stat().st_mode & 0o077:
            raise ValueError("Proteja data/admin-password com chmod 600")
        password = password_file.read_text().strip()
    origin = os.environ.get("ADMIN_ORIGIN", "http://127.0.0.1:8081")
    bind_host = os.environ.get("ADMIN_BIND_HOST", "127.0.0.1")
    if bind_host not in {"127.0.0.1", "0.0.0.0"}:
        raise ValueError("ADMIN_BIND_HOST deve ser 127.0.0.1 ou 0.0.0.0")
    parsed_origin = urlsplit(origin)
    port = int(os.environ.get("ADMIN_PORT", str(parsed_origin.port or 8081)))
    if not 1 <= port <= 65535:
        raise ValueError("ADMIN_PORT inválida")
    engine = create_engine(settings)
    app = AdminApplication(create_session_factory(engine), settings, password, origin=origin)
    print(f"Painel privado: {origin} — senha em ADMIN_PASSWORD ou data/admin-password", flush=True)
    try:
        await serve(app, host=bind_host, port=port)
    finally:
        await app.crawls.close()
        await engine.dispose()


def main():
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
