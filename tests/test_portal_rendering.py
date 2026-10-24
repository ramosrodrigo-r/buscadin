from html.parser import HTMLParser

from buscadin_bot.services.catalogue import CatalogueFilters, CataloguePage
from buscadin_bot.web.rendering import PortalRenderer


def example_job(**overrides):
    return {
        "id": 1, "title": "Anotação de vídeos", "company": "Empresa Exemplo",
        "path": "/vagas/anotacao-de-videos-1", "category": "data_labeling", "remote_type": "remote",
        "summary": "Resumo revisado.\n\nInformações da fonte.", "eligibility_status": "unknown",
        "requirements": {"education": "unknown", "experience": "not_required"},
        "salary_disclosed": False, "language_requirements": ["Português"], "updated_at": "2026-10-23T15:00:00+00:00",
        "application_available": True, "destination_host": "jobs.example", "source": "Fonte exemplo",
        "source_url": "https://jobs.example/1", **overrides,
    }


class Markup(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.elements = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


def test_public_pages_contain_indexable_content_before_client_enhancement():
    renderer = PortalRenderer()
    page = CataloguePage([example_job()], 1, 1, 20)
    for html in (renderer.home(page), renderer.catalogue(page, CatalogueFilters()), renderer.detail(example_job())):
        markup = Markup(html)
        assert "Anotação de vídeos" in html
        assert 'lang="pt-BR"' in html
        assert all(attrs.get("src") == "/static/portal.js" for tag, attrs in markup.elements if tag == "script")
        assert sum(tag == "h1" for tag, _ in markup.elements) == 1
        assert any(tag == "link" and attrs.get("rel") == "canonical" for tag, attrs in markup.elements)


def test_job_text_cannot_inject_html_or_javascript_links():
    html = PortalRenderer().detail(example_job(
        title='<script>alert("x")</script>', company='<img src=x onerror=alert(1)>',
        summary='<a href="javascript:alert(1)">Click</a>', source_url="javascript:alert(1)",
    ))
    markup = Markup(html)
    assert all(attrs.get("src") == "/static/portal.js" for tag, attrs in markup.elements if tag == "script")
    assert all(not attrs.get("href", "").startswith("javascript:") for _, attrs in markup.elements)
    assert all("onerror" not in attrs for _, attrs in markup.elements)
    assert "&lt;script&gt;" in html


def test_unknown_is_not_rendered_as_requirement_waiver():
    html = PortalRenderer().detail(example_job())
    assert "<dt>Graduação</dt><dd>Não informada</dd>" in html
    assert "<dt>Experiência</dt><dd>Não exigida</dd>" in html
    assert "elegibilidade para residentes no Brasil ainda não foi confirmada" in html
    assert "Remuneração não informada" in html


def test_suspended_application_has_no_outbound_action():
    html = PortalRenderer().detail(example_job(application_available=False))
    assert 'href="/go/' not in html
    assert "Candidatura em revisão" in html
    assert any(tag == "button" and "disabled" in attrs for tag, attrs in Markup(html).elements)


def test_referral_disclosure_is_visible_without_private_url():
    html = PortalRenderer().detail(example_job(commercial_disclosure="Este link pode gerar remuneração para o Buscadin."))
    assert "Este link pode gerar remuneração" in html
    assert 'rel="nofollow sponsored"' in html
    assert 'href="/go/1"' in html


def test_filter_query_is_shareable_and_noindex_with_accessible_labels():
    html = PortalRenderer().catalogue(CataloguePage([example_job()], 22, 1, 20), CatalogueFilters(q="vídeo", education="not_required"))
    markup = Markup(html)
    assert 'content="noindex,follow"' in html
    ids = {attrs.get("id") for _, attrs in markup.elements if attrs.get("id")}
    assert all(attrs["for"] in ids for tag, attrs in markup.elements if tag == "label" and "for" in attrs)
    assert 'method="get"' in html
    next_link = next(attrs["href"] for tag, attrs in markup.elements if tag == "a" and attrs.get("rel") == "next")
    assert "education=not_required" in next_link and "page=2" in next_link
    assert CatalogueFilters(category="", language="", education="").education is None


def test_removed_page_does_not_offer_candidature_and_has_noindex():
    html = PortalRenderer().unavailable(removed=True)
    assert "saiu do catálogo" in html
    assert 'content="noindex,follow"' in html
    assert 'href="/go/' not in html


def test_contact_uses_existing_brand_address():
    html = PortalRenderer().contact(1)
    assert "contato@buscadin.app" in html
    assert "mailto:contato@buscadin.app?" in html
