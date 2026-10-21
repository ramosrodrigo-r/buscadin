# Entrega 01 — Fundação executável

**Data:** 2026-10-21  
**Status:** concluída

## O que foi entregue

- Projeto Python 3.12+ empacotado com `pyproject.toml`, dependências e `uv.lock`.
- Configuração por `.env` via Pydantic Settings, com segredo do Telegram protegido por `SecretStr`.
- Modelos SQLAlchemy 2 para `Job`, `Referral`, `Notification` e `BotState`.
- Session factory assíncrona para SQLite e caminho preparado para PostgreSQL via `DATABASE_URL`.
- Migration Alembic `0001_initial` com constraints de unicidade para jobs e notificações.
- Testes de validação de configuração e persistência do schema.

## Verificação executada

```text
uv sync                         OK
uv run pytest                   3 passed
uv run alembic upgrade head     OK
uv run alembic current          0001_initial (head)
```

## Decisões técnicas

`init_db()` existe para testes e bootstrap local, mas o caminho operacional documentado usa Alembic. Tokens não são exigidos durante testes de coleta, porém `require_telegram()` falha explicitamente quando o processo Telegram não possui credenciais.

## Próxima entrega

Implementar `JobSource`, conector Himalayas com timeout/retry, normalização semântica, classificação determinística de categoria/elegibilidade e repositório idempotente.
