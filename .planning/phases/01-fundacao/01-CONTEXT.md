# Phase 1: Fundação executável - Context

**Gathered:** 2026-10-21  
**Status:** Ready for execution

## Phase Boundary

Entregar um pacote Python instalável, configuração por ambiente, persistência assíncrona e schema versionado para o domínio do bot. Telegram e coleta real ficam para fases seguintes.

## Implementation Decisions

- Usar `src` layout e `pyproject.toml` compatível com `uv`.
- Pydantic Settings valida `TELEGRAM_BOT_TOKEN` apenas quando o processo Telegram for iniciado, permitindo testes de coleta sem segredo.
- SQLAlchemy 2 async com SQLite por padrão; JSON para listas/evidências e constraints para idempotência.
- Alembic é a fonte de migrations; `init_db` continua disponível para testes rápidos.

## Canonical References

- `PRD_Buscadin_Telegram_Bot.md` — stack obrigatória, modelos mínimos e variáveis de ambiente.
- `AGENTS.md` — estrutura e comandos esperados.

## Acceptance

- `uv sync` instala.
- `uv run pytest` executa testes da fundação.
- `uv run alembic upgrade head` cria tabelas.
- `docs/entregas/ENTREGA-01-fundacao.md` descreve o que foi entregue e como verificar.
