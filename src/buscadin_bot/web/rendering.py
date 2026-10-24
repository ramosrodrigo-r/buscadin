"""Server-rendered public pages. No client framework or hosting choice required."""

from datetime import datetime
from html import escape
import re
from typing import Any
from urllib.parse import urlencode, urlsplit

from buscadin_bot.services.catalogue import CatalogueFilters, CataloguePage


CATEGORIES = {
    "data_labeling": "Anotação de dados", "ai_training": "Treinamento de IA",
    "ai_evaluation": "Avaliação de IA", "search_quality": "Qualidade de busca",
    "development": "Programação", "qa": "Qualidade e testes", "data": "Dados", "other": "Outras áreas",
}
REQUIREMENTS = {"unknown": "Não informada", "required": "Exigida", "not_required": "Não exigida"}


def _e(value: Any) -> str:
    return escape(str(value) if value is not None else "", quote=True)


def _date(value: Any) -> str:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).strftime("%d/%m/%Y")
    except (ValueError, TypeError):
        return "Data não informada"


def _safe_source(value: Any) -> str | None:
    try:
        parsed = urlsplit(str(value))
        if parsed.scheme == "https" and parsed.hostname and not parsed.username and not parsed.password:
            return str(value)
    except ValueError:
        pass
    return None


def _job_path(job: dict[str, Any]) -> str:
    path = str(job.get("path", ""))
    return path if re.fullmatch(r"/vagas/[a-z0-9-]+-\d+", path) else "/vagas"


def _salary(job: dict[str, Any]) -> str:
    if not job.get("salary_disclosed") or (job.get("salary_min") is None and job.get("salary_max") is None):
        return "Remuneração não informada"
    def amount(value):
        return f"{float(value):g}".replace(".", ",")
    lower, upper = job.get("salary_min"), job.get("salary_max")
    if lower is not None and upper is not None:
        value = amount(lower) if lower == upper else f"{amount(lower)}–{amount(upper)}"
    else:
        value = f"A partir de {amount(lower)}" if lower is not None else f"Até {amount(upper)}"
    period = {"hour": "hora", "hourly": "hora", "day": "dia", "daily": "dia", "month": "mês", "monthly": "mês", "year": "ano", "yearly": "ano", "annual": "ano"}.get(job.get("salary_period"), job.get("salary_period"))
    return f"{job.get('currency') or 'Moeda não informada'} {value}" + (f" / {period}" if period else " · período não informado")


class PortalRenderer:
    def __init__(self, *, base_url: str = "https://buscadin.app", contact_email: str = "contato@buscadin.app") -> None:
        parsed = urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
            raise ValueError("Base pública deve conter somente origem HTTP(S)")
        if not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+", contact_email):
            raise ValueError("E-mail de contato inválido")
        self.base_url, self.contact_email = base_url.rstrip("/"), contact_email

    def _page(self, title: str, body: str, *, path: str, description: str, noindex: bool = False, active: str = "") -> str:
        canonical = self.base_url + path
        current = ' aria-current="page"' if active == "vagas" else ""
        robots = "noindex,follow" if noindex else "index,follow"
        return f'''<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_e(title)} · Buscadin</title><meta name="description" content="{_e(description)}">
<meta name="robots" content="{robots}"><link rel="canonical" href="{_e(canonical)}">
<meta property="og:type" content="website"><meta property="og:locale" content="pt_BR">
<meta property="og:title" content="{_e(title)} · Buscadin"><meta property="og:description" content="{_e(description)}"><meta property="og:url" content="{_e(canonical)}">
<meta property="og:image" content="{_e(self.base_url)}/static/logo.jpg"><meta property="og:image:alt" content="Buscadin">
<link rel="icon" href="/static/favicon.svg" type="image/svg+xml">
<link rel="preload" href="/static/fonts/InterVariable.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="/static/portal.css"><script src="/static/portal.js" defer></script></head><body>
<a class="skip" href="#conteudo">Pular para o conteúdo</a>
<header class="header"><div class="container nav"><a class="brand" href="/" aria-label="Buscadin, início"><img src="/static/favicon.svg" width="30" height="30" alt="">Buscadin</a>
<nav class="nav-links" aria-label="Principal"><a href="/vagas"{current}>Explorar vagas</a><a href="/sobre" class="optional">Sobre</a></nav></div></header>
<main id="conteudo">{body}</main>
<footer class="footer"><div class="container footer-inner"><div><a class="brand" href="/">Buscadin</a><p>Vagas selecionadas, informações com fonte. A candidatura acontece no site da empresa ou da plataforma responsável.</p></div>
<nav aria-label="Institucional"><a href="/sobre">Sobre</a><a href="/contato">Contato e correções</a><a href="/privacidade">Privacidade</a><a href="/termos">Termos</a></nav></div></footer></body></html>'''

    @staticmethod
    def _search(value: str = "", *, hidden: dict[str, Any] | None = None, css: str = "") -> str:
        fields = "".join(f'<input type="hidden" name="{_e(key)}" value="{_e(value)}">' for key, value in (hidden or {}).items())
        return f'''<form class="search {css}" action="/vagas" method="get" role="search">{fields}<div class="field"><label for="busca">Cargo, empresa ou habilidade</label><input type="search" id="busca" name="q" maxlength="120" value="{_e(value)}" placeholder="Ex.: anotação de vídeos" autocomplete="off"></div><button class="button" type="submit">Buscar vagas</button></form>'''

    @staticmethod
    def _jobs(jobs: list[dict[str, Any]], *, filtered: bool = False) -> str:
        if not jobs:
            heading = "Nenhuma vaga com esses filtros." if filtered else "Novas oportunidades estão a caminho."
            message = "Tente outra palavra ou remova um filtro para ampliar a busca." if filtered else "As vagas aparecem aqui depois de uma revisão. Volte em breve para conferir as próximas oportunidades."
            return f'<div class="empty"><h2>{heading}</h2><p>{message}</p><a class="button secondary" href="/vagas">Ver todas as vagas</a></div>'
        rows = []
        for job in jobs:
            confirmed = job.get("eligibility_status") == "confirmed_br"
            label = "Brasil confirmado" if confirmed else "Brasil a confirmar"
            meta = [CATEGORIES.get(job.get("category"), "Outras áreas")]
            if job.get("remote_type") == "remote":
                meta.append("Remoto")
            requirements = job.get("requirements") or {}
            if requirements.get("education") == "not_required":
                meta.append("Sem exigência de graduação")
            if requirements.get("experience") == "not_required":
                meta.append("Sem exigência de experiência")
            if not job.get("application_available", False):
                meta.append("Candidatura em revisão")
            metadata = "".join(f"<span>{_e(value)}</span>" for value in meta)
            rows.append(f'''<article class="job"><div><p class="company">{_e(job.get('company'))}</p><h3><a href="{_e(_job_path(job))}">{_e(job.get('title'))}</a></h3><div class="job-meta">{metadata}</div></div><div class="job-tail"><span class="salary">{_e(_salary(job))}</span><span class="eligibility {'' if confirmed else 'unknown'}">{label}</span><span class="muted">Revisada em {_date(job.get('updated_at'))}</span></div></article>''')
        return '<div class="job-list">' + "".join(rows) + "</div>"

    def home(self, recent: CataloguePage) -> str:
        body = f'''<div class="container"><section class="hero"><h1>Vagas remotas, com os detalhes que importam.</h1><p>Explore oportunidades selecionadas para quem está no Brasil. Veja o que a vaga exige e o que ainda precisa ser confirmado antes de se candidatar.</p>{self._search()}<ul class="shortcuts"><li><a href="/vagas?category=data_labeling">Anotação de dados</a></li><li><a href="/vagas?education=not_required">Sem exigência de graduação</a></li><li><a href="/vagas?experience=not_required">Sem exigência de experiência</a></li></ul></section>
<section class="recent" aria-labelledby="recentes"><div class="section-head"><h2 id="recentes">Oportunidades recentes</h2><a class="text-link" href="/vagas">Ver todas as vagas</a></div>{self._jobs(recent.items)}</section></div>
<section class="how"><div class="container how-grid"><div><h2>Mais contexto para escolher onde tentar.</h2><p>Começamos por oportunidades como anotação de vídeos e treinamento de IA. O catálogo também reúne outras áreas de trabalho remoto.</p></div><ol><li><strong>Encontre uma oportunidade</strong><p>Use os filtros de área, idioma e requisitos para ajustar a busca.</p></li><li><strong>Confira os detalhes</strong><p>Informação ausente aparece como não informada. Brasil não confirmado fica sinalizado.</p></li><li><strong>Candidate-se na fonte</strong><p>O botão leva ao destino revisado. O Buscadin não recebe currículos.</p></li></ol></div></section>'''
        return self._page("Vagas remotas para quem está no Brasil", body, path="/", description="Oportunidades remotas selecionadas: anotação de dados, treinamento de IA e outras áreas. Confira requisitos e elegibilidade para o Brasil.")

    def catalogue(self, page: CataloguePage, filters: CatalogueFilters) -> str:
        params = self._filter_params(filters)
        hidden = {key: value for key, value in params.items() if key not in {"q", "page", "page_size"}}
        count = f"{page.total} oportunidade" + ("s" if page.total != 1 else "")
        body = f'''<div class="container"><header class="page-heading"><h1>Explore as vagas</h1><p>Encontre oportunidades que façam sentido para você. Requisitos não informados nunca significam que foram dispensados.</p></header><div class="catalogue-layout">{self._filters(filters)}<section aria-label="Resultados">{self._search(filters.q, hidden=hidden, css='results-search')}<p class="results-count">{count} · mais recentes primeiro</p>{self._jobs(page.items, filtered=bool(params))}{self._pagination(page, params)}</section></div></div>'''
        return self._page("Vagas remotas", body, path="/vagas", description="Busque vagas remotas por área, idioma, remuneração e requisitos. Confira a elegibilidade para residentes no Brasil.", noindex=bool(params), active="vagas")

    @staticmethod
    def _filter_params(filters: CatalogueFilters) -> dict[str, Any]:
        defaults = CatalogueFilters().model_dump()
        return {key: ("true" if value is True else value) for key, value in filters.model_dump().items() if value != defaults[key] and value is not None}

    @staticmethod
    def _select(name: str, label: str, options: dict[str, str], selected: str | None) -> str:
        choices = '<option value="">Todas as opções</option>' + "".join(
            f'<option value="{_e(value)}"{" selected" if value == selected else ""}>{_e(text)}</option>' for value, text in options.items()
        )
        return f'<div class="field"><label for="f-{name}">{label}</label><select id="f-{name}" name="{name}">{choices}</select></div>'

    def _filters(self, filters: CatalogueFilters) -> str:
        fields = self._select("category", "Área de trabalho", CATEGORIES, filters.category)
        fields += self._select("language", "Idioma exigido", {"pt": "Português", "en": "Inglês", "es": "Espanhol", "fr": "Francês", "de": "Alemão"}, filters.language)
        fields += self._select("country", "País informado na vaga", {"BR": "Brasil"}, filters.country)
        fields += self._select("eligibility", "Elegibilidade para o Brasil", {"confirmed_br": "Confirmada na fonte", "unknown": "Ainda não confirmada"}, filters.eligibility)
        fields += self._select("education", "Graduação", REQUIREMENTS, filters.education)
        fields += self._select("experience", "Experiência", REQUIREMENTS, filters.experience)
        hidden = f'<input type="hidden" name="q" value="{_e(filters.q)}">' if filters.q else ""
        return f'''<details class="filters" open><summary>Filtrar oportunidades</summary><form action="/vagas" method="get">{hidden}{fields}<label class="check"><input type="checkbox" name="salary_available" value="true"{' checked' if filters.salary_available else ''}>Com remuneração informada</label><div class="filter-actions"><button class="button" type="submit">Aplicar filtros</button><a href="/vagas">Limpar filtros</a></div></form></details>'''

    @staticmethod
    def _pagination(page: CataloguePage, params: dict[str, Any]) -> str:
        previous = f'<a rel="prev" href="/vagas?{_e(urlencode(params | {"page": page.page - 1}))}">← Anterior</a>' if page.page > 1 else "<span></span>"
        following = f'<a rel="next" href="/vagas?{_e(urlencode(params | {"page": page.page + 1}))}">Próxima →</a>' if page.has_next else "<span></span>"
        return f'<nav class="pagination" aria-label="Paginação">{previous}<span>Página {page.page}</span>{following}</nav>'

    def detail(self, job: dict[str, Any]) -> str:
        requirements = job.get("requirements") or {}
        facts = {
            "Área": CATEGORIES.get(job.get("category"), "Outras áreas"),
            "Remuneração": _salary(job),
            "Graduação": REQUIREMENTS.get(requirements.get("education"), "Não informada"),
            "Experiência": REQUIREMENTS.get(requirements.get("experience"), "Não informada"),
            "Idiomas exigidos": ", ".join(job.get("language_requirements") or []) or "Não informados",
            "Modalidade": "Remoto" if job.get("remote_type") == "remote" else "Não informada",
        }
        facts_html = "".join(f"<div><dt>{label}</dt><dd>{_e(value)}</dd></div>" for label, value in facts.items())
        notice = '' if job.get("eligibility_status") == "confirmed_br" else '<p class="notice">A elegibilidade para residentes no Brasil ainda não foi confirmada pela fonte. Confira essa condição no anúncio antes de iniciar a candidatura.</p>'
        confirmed = '<p class="eligibility">Elegibilidade para o Brasil confirmada na fonte.</p>' if not notice else ""
        if job.get("application_available"):
            relation = "nofollow sponsored" if job.get("commercial_disclosure") else "nofollow"
            cta = f'<a class="button" href="/go/{int(job["id"])}" rel="{relation}">Candidatar-se ↗</a>'
        else:
            cta = '<button class="button" type="button" disabled>Candidatura em revisão</button>'
        disclosure = f'<p class="disclosure">{_e(job["commercial_disclosure"])}</p>' if job.get("commercial_disclosure") else ""
        source = _safe_source(job.get("source_url"))
        source_link = f'<a href="{_e(source)}" rel="nofollow noopener noreferrer">Ver anúncio na fonte</a>' if source else ""
        paragraphs = "".join(f"<p>{_e(paragraph)}</p>" for paragraph in str(job.get("summary", "")).split("\n\n") if paragraph.strip())
        body = f'''<div class="container"><nav class="breadcrumb" aria-label="Caminho"><a href="/vagas">Todas as vagas</a> / {_e(CATEGORIES.get(job.get('category'), 'Outras áreas'))}</nav><header class="detail-heading"><p class="company">{_e(job.get('company'))}</p><h1>{_e(job.get('title'))}</h1>{confirmed}{notice}</header><div class="detail-layout"><section aria-label="Detalhes da vaga"><dl class="facts">{facts_html}</dl><div class="description"><h2>Sobre a oportunidade</h2>{paragraphs}</div><div class="source"><p>Fonte: {_e(job.get('source'))}. Revisada em {_date(job.get('updated_at'))}.</p>{source_link} · <a href="/contato?vaga={int(job['id'])}">Informar um problema</a></div></section><aside class="apply" aria-label="Candidatura"><h2>Próximo passo</h2><p>Confira os requisitos e siga para a candidatura no site responsável.</p>{cta}<p class="host">{_e(job.get('destination_host') or 'Destino externo')}</p><p>Você continuará fora do Buscadin. Não recebemos seu currículo nem participamos da seleção.</p>{disclosure}</aside></div></div>'''
        return self._page(str(job.get("title", "Vaga")), body, path=_job_path(job), description=str(job.get("summary", ""))[:180], active="vagas")

    def unavailable(self, *, removed: bool = False) -> str:
        title = "Esta vaga saiu do catálogo." if removed else "Não encontramos esta página."
        body = f'<div class="container prose"><h1>{title}</h1><p>Explore as oportunidades disponíveis agora.</p><a class="button" href="/vagas">Ver vagas</a></div>'
        return self._page(title, body, path="/vagas", description=title, noindex=True)

    def about(self) -> str:
        body = '''<div class="container"><article class="prose"><h1>Uma busca com mais contexto.</h1><p>O Buscadin reúne oportunidades de trabalho remoto para quem está no Brasil. Cada vaga passa por seleção antes de aparecer no catálogo.</p><h2>O que você encontra aqui</h2><p>Anotação de dados, treinamento e avaliação de IA, programação e outras áreas. Quando graduação ou experiência não são exigidas, essa informação precisa estar explícita na fonte. O que não foi informado continua sinalizado como desconhecido.</p><h2>Como as vagas chegam ao site</h2><p>A coleta ajuda a encontrar oportunidades. A publicação depende de revisão editorial. Remuneração e elegibilidade são apresentadas conforme as informações disponíveis na fonte.</p><h2>Candidatura e indicações</h2><p>A candidatura acontece fora do Buscadin. Algumas vagas usam links de indicação que podem gerar remuneração para o Buscadin; essa relação é informada na página da oportunidade.</p><p>Encontrou uma informação incorreta? <a href="/contato">Avise para que possamos revisar.</a></p></article></div>'''
        return self._page("Sobre o Buscadin", body, path="/sobre", description="Conheça a curadoria de vagas remotas do Buscadin e como apresentamos requisitos, elegibilidade e indicações.")

    def contact(self, job_id: int | None = None) -> str:
        subject = f"Correção de vaga {job_id}" if job_id is not None else "Contato Buscadin"
        mailto = "mailto:" + self.contact_email + "?" + urlencode({"subject": subject})
        body = f'''<div class="container"><article class="prose"><h1>Contato e correções</h1><p>Vaga encerrada, link com problema ou informação incorreta? Envie o endereço da página e descreva o que precisa de revisão.</p><p>Para falar com o Buscadin: <a href="{_e(mailto)}">{_e(self.contact_email)}</a>.</p><p>Não é necessário enviar documentos pessoais ou currículo para informar um problema.</p></article></div>'''
        return self._page("Contato e correções", body, path="/contato", description="Fale com o Buscadin e informe problemas em vagas, links ou informações do catálogo.")

    def privacy(self) -> str:
        body = '''<div class="container"><article class="prose"><h1>Privacidade</h1><p>O catálogo público mostra somente informações editoriais sobre as vagas e links para as páginas responsáveis pela candidatura.</p><h2>Dados de candidatura</h2><p>O Buscadin não recebe currículos nem conduz a seleção. Ao seguir para uma candidatura, você passa a interagir com o site indicado, sujeito às regras desse operador.</p><h2>Contato</h2><p>Mensagens enviadas ao contato do Buscadin são usadas para responder e revisar informações do catálogo. Não envie documentos pessoais para comunicar um erro.</p><p>Para dúvidas sobre esta página, escreva para <a href="mailto:%s">%s</a>.</p></article></div>''' % (self.contact_email, self.contact_email)
        return self._page("Privacidade", body, path="/privacidade", description="Como o Buscadin apresenta vagas e trata mensagens de contato.")

    def terms(self) -> str:
        body = '''<div class="container"><article class="prose"><h1>Termos de uso</h1><p>O Buscadin oferece um catálogo curado de oportunidades remotas. As informações são apresentadas conforme a fonte e podem mudar depois da revisão.</p><h2>Antes de se candidatar</h2><p>Confira os requisitos, a elegibilidade para o Brasil e as condições no anúncio original. A candidatura é feita fora do Buscadin e a decisão pertence à empresa ou plataforma responsável.</p><h2>Links de indicação</h2><p>Alguns destinos podem gerar remuneração para o Buscadin. Quando isso ocorrer, a página informa essa relação de forma visível.</p><h2>Correções</h2><p>Se uma informação estiver desatualizada, envie a página para revisão pelo contato indicado.</p></article></div>'''
        return self._page("Termos de uso", body, path="/termos", description="Termos de uso do catálogo de vagas remotas do Buscadin.")
