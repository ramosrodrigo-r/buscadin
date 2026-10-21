# Entrega 04 — Operação e aceite do MVP

**Data:** 2026-10-21  
**Status:** concluída

## O que foi entregue

- `ReferralResolver` com validação de URL absoluta `http(s)`, aprovação pública, verificação, habilitação, expiração e precedência de referral específico da vaga.
- Integração do resolver ao worker da outbox; nenhuma URL é criada, concatenada ou alterada pelo sistema.
- CLI `buscadin referral add/list` para cadastro explícito pelo administrador.
- README com setup, BotFather, `.env`, execução, migrations, backup SQLite e estrutura do projeto.
- Dockerfile opcional e `.dockerignore` para execução isolada.
- Testes finais para referrals aprovados, expirados, inválidos e não aprovados.

## Verificação final

```text
uv run pytest                   19 passed
uv lock --check                 OK
uv run alembic upgrade head     OK
uv run alembic downgrade base  OK
uv run alembic upgrade head     OK
uv run buscadin referral add    OK
uv run buscadin referral list   OK
```

## Estado do MVP

Os critérios funcionais do PRD estão cobertos por código e testes locais. A operação real ainda depende do preenchimento seguro das variáveis Telegram e da validação contínua dos termos de cada fonte antes de habilitá-la em produção.

## Próximos passos fora do MVP

Webhook Telegram, conectores oficiais Greenhouse/Lever/Ashby e métricas de conversão podem ser planejados posteriormente. Frontend, LLM, scraping autenticado e publicação social permanecem fora do escopo.
