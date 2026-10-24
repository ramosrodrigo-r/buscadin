"""Generate isolated visual fixtures, never production catalogue data.

Run: uv run python scripts/preview_portal.py
"""

from pathlib import Path
import shutil

from buscadin_bot.services.catalogue import CatalogueFilters, CataloguePage
from buscadin_bot.web.rendering import PortalRenderer


def main() -> None:
    sample = {
        "id": 1, "title": "Anotador de vídeos em português", "company": "Empresa Exemplo",
        "path": "/vagas/anotacao-de-videos-1", "category": "data_labeling", "remote_type": "remote",
        "summary": "Dados fictícios para inspeção local. Esta não é uma vaga publicada.\n\nRevise trechos de vídeo e identifique ações conforme as instruções do projeto.",
        "eligibility_status": "confirmed_br", "requirements": {"education": "not_required", "experience": "not_required"},
        "salary_disclosed": False, "language_requirements": ["Português"], "updated_at": "2026-10-23T15:00:00+00:00",
        "application_available": True, "destination_host": "jobs.example", "source": "Fonte exemplo", "source_url": "https://jobs.example/1",
    }
    rows = [sample, sample | {"id": 2, "title": "Avaliador de respostas de IA", "company": "Plataforma Exemplo", "category": "ai_evaluation", "path": "/vagas/avaliador-de-respostas-2", "eligibility_status": "unknown", "salary_disclosed": True, "salary_min": 12, "salary_max": 18, "currency": "USD", "salary_period": "hour"}, sample | {"id": 3, "title": "Desenvolvedor Python", "company": "Equipe Exemplo", "category": "development", "path": "/vagas/desenvolvedor-python-3", "language_requirements": ["English"], "eligibility_status": "unknown", "requirements": {"education": "unknown", "experience": "required"}}]
    page, renderer = CataloguePage(rows, 3, 1, 20), PortalRenderer()
    root = Path(__file__).resolve().parents[1]
    output = root / ".preview" / "portal"
    output.mkdir(parents=True, exist_ok=True)
    pages = {
        "index.html": renderer.home(page), "catalogue.html": renderer.catalogue(page, CatalogueFilters()),
        "detail.html": renderer.detail(rows[0]), "unknown.html": renderer.detail(rows[1]),
        "empty.html": renderer.catalogue(CataloguePage([], 0, 1, 20), CatalogueFilters(q="inexistente")),
        "about.html": renderer.about(), "contact.html": renderer.contact(),
    }
    for name, content in pages.items():
        (output / name).write_text(content)
    shutil.copytree(root / "src/buscadin_bot/web/static", output / "static", dirs_exist_ok=True)
    print(f"Prévias com dados fictícios: {output}")


if __name__ == "__main__":
    main()
