# Entrega 10 — servidor HTTP e contrato privado (parcial)

## O que foi entregue

- Transporte HTTP sem framework adicional em web/server.py, adequado para ser servido atrás do Traefik:
  - home, catálogo, detalhe, estados institucionais, assets, robots.txt, sitemap.xml e /healthz;
  - redirecionamento /go/<id> com revalidação transacional do destino e bloqueio quando suspenso;
  - respostas com limite de corpo, HEAD, headers de segurança e sem seguir redirects.
- API privada usada pelo Telegram:
  - prévia, confirmação, consulta, listagem, retirada e atualização de requisitos;
  - Bearer token e ator Telegram verificados antes de mutações e consultas;
  - mensagens de erro sem corpo remoto, token ou snapshot privado.
- Serviço executável separado em web/portal.py, com configuração de domínio, e-mail, domínios oficiais e porta.
- Driver asyncpg incluído no pyproject.toml e uv.lock para PostgreSQL assíncrono.
- Termos e privacidade deixaram de ser links sem destino e passaram a ter páginas iniciais coerentes com o catálogo.
- O processo do bot agora reconcilia publicações em lote e entrega alertas persistidos ao administrador, quando a API do site está configurada.
- `/requisitos_site` permite curadoria de graduação e experiência pelo Telegram com evidência obrigatória para estados explícitos.
- Páginas HTML e sitemap usam cache curto de 60 segundos; API interna, healthcheck e redirects usam `no-store`, e o redirect sempre revalida o destino no banco.

## Verificação

    .venv/bin/python -m pytest -q
    140 passed
    git diff --check

`uv sync --frozen`, `uv run pytest -q` e `uv run alembic upgrade head` seguido de `uv run alembic check` também passaram em ambiente SQLite temporário.

tests/test_web_server.py verifica autenticação, prévia sem publicação, confirmação, projeção pública, detalhe, redirect, sitemap e traversal de assets.

O processo real foi iniciado temporariamente em `127.0.0.1:4180`; `GET /healthz` respondeu `200` com `X-Content-Type-Options`, `Referrer-Policy` e CSP.

## Limites

O servidor ainda não foi implantado na VPS nem conectado ao banco PostgreSQL real. O serviço do Dokploy deve rodar buscadin-portal, aplicar migrations antes de iniciar e receber SITE_API_TOKEN, TELEGRAM_ADMIN_USER_ID, SITE_OFFICIAL_DOMAINS e o DATABASE_URL do banco do novo catálogo. O projeto legado permanece separado até backup e plano de retirada aprovados.
