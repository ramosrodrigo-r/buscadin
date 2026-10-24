"""Portal process entry point used by a dedicated Dokploy service."""

import asyncio

from buscadin_bot.config import get_settings
from buscadin_bot.db.session import close_engine, create_engine, create_session_factory
from buscadin_bot.services.catalogue import PublicCatalogue
from buscadin_bot.services.site_publications import SitePublicationService
from buscadin_bot.web.rendering import PortalRenderer
from buscadin_bot.web.server import PortalApplication, serve


def _domains(value: str) -> list[str]:
    return [item.strip().lower() for item in value.split(",") if item.strip()]


async def run() -> None:
    settings = get_settings()
    if settings.site_api_token is None or not settings.site_api_token.get_secret_value():
        raise ValueError("SITE_API_TOKEN deve ser configurado para iniciar o portal")
    if settings.telegram_admin_user_id is None:
        raise ValueError("TELEGRAM_ADMIN_USER_ID deve ser configurado para autorizar o portal")
    engine = create_engine(settings)
    sessions = create_session_factory(engine)
    publications = SitePublicationService(
        sessions,
        admin_actor=str(settings.telegram_admin_user_id),
        official_domains=_domains(settings.site_official_domains),
    )
    portal = PortalApplication(
        PublicCatalogue(sessions, publications),
        publications,
        renderer=PortalRenderer(base_url=settings.site_base_url, contact_email=settings.site_contact_email),
        internal_token=settings.site_api_token.get_secret_value(),
    )
    try:
        await serve(portal, host=settings.portal_host, port=settings.portal_port)
    finally:
        await close_engine(engine)


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
