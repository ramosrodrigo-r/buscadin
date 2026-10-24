"""Pure publication rules shared by previews, confirmation and outbound clicks.

These checks do not publish anything and do not replace transaction-time checks
of the selected referral's scope, permission and lifetime.
"""

import hashlib
import ipaddress
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import unquote, urlsplit


class PublicationRejected(ValueError):
    """A publication or destination needs correction before approval."""


def validate_destination(url: str, allowed_domains: Sequence[str]) -> str:
    """Return the original URL only for an explicitly allowed HTTPS hostname.

    Domains match exactly. Register subdomains explicitly to avoid extending
    permission to an unrelated tenant. Never reconstruct referral query strings.
    No network fetch happens here; this is not an SSRF-safe HTTP fetcher.
    """
    if not url or len(url) > 2048 or url != url.strip():
        raise PublicationRejected("Destino vazio, extenso ou com espaços externos")
    decoded = unquote(url)
    if any(ord(character) <= 32 for character in url) or any(
        ord(character) < 32 or ord(character) == 127 for character in decoded
    ):
        raise PublicationRejected("Destino contém espaços ou caracteres de controle")
    if "\\" in decoded:
        raise PublicationRejected("Destino contém separador ambíguo")
    try:
        parsed = urlsplit(url)
        port = parsed.port
        hostname = parsed.hostname
    except ValueError as error:
        raise PublicationRejected("Destino inválido") from error
    if parsed.scheme != "https" or not hostname or port not in (None, 443):
        raise PublicationRejected("Destino exige HTTPS e porta padrão")
    if parsed.username is not None or parsed.password is not None:
        raise PublicationRejected("Destino não pode conter credenciais")
    host = _domain(hostname)
    allowed = {_domain(domain) for domain in allowed_domains}
    if host not in allowed:
        raise PublicationRejected("Domínio do destino não foi autorizado")
    return url


def _domain(value: str) -> str:
    try:
        domain = value.encode("idna").decode("ascii").lower()
    except UnicodeError as error:
        raise PublicationRejected("Domínio inválido") from error
    if len(domain) > 253 or "." not in domain or domain.endswith("."):
        raise PublicationRejected("Exige domínio público explícito")
    if domain.endswith((".localhost", ".local", ".internal", ".lan")):
        raise PublicationRejected("Domínio local não permitido")
    try:
        ipaddress.ip_address(domain)
    except ValueError:
        pass
    else:
        raise PublicationRejected("Endereço IP não permitido como destino")
    if not all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", part) for part in domain.split(".")):
        raise PublicationRejected("Domínio inválido")
    return domain


def require_publishable_job(*, status: str, eligibility: str) -> None:
    if status != "active":
        raise PublicationRejected("Vaga não está ativa")
    if eligibility not in {"confirmed_br", "unknown"}:
        raise PublicationRejected("Elegibilidade incompatível ou inválida")


def preview_fingerprint(snapshot: Mapping[str, Any]) -> str:
    """Bind confirmation to a canonical JSON snapshot, not a mutable job ID.

    The caller must include public content, selected destination, referral and
    program validation state, and publication version. This digest detects
    changes; it is not an authentication token or an authorization mechanism.
    """
    serialized = json.dumps(
        dict(snapshot), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
