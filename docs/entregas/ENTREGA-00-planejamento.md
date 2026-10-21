# Entrega 00 — Planejamento do MVP

**Data:** 2026-10-21  
**Fonte de verdade:** `PRD_Buscadin_Telegram_Bot.md`

## Objetivo

Transformar o PRD em um projeto executável, dividido em entregas pequenas e verificáveis. O escopo permanece privado: um chat administrativo do Telegram, coleta autorizada de vagas, persistência idempotente e revisão manual.

## Decisões registradas

- Python 3.12+ com `uv` e `uv.lock` versionado.
- Primeiro conector: API pública da Himalayas, com atribuição e respeito aos termos.
- Telegram somente pela Bot API HTTP oficial usando `httpx`; sem `python-telegram-bot` ou `aiogram`.
- SQLite com SQLAlchemy 2/Alembic no MVP e `DATABASE_URL` preparado para PostgreSQL.
- Nenhum link de indicação será montado por inferência.

## Entregas

1. Fundação: configuração, schema, migrations e testes.
2. Coleta: Himalayas, normalização, deduplicação e elegibilidade Brasil.
3. Telegram: mensagens, callbacks, comandos, polling e outbox.
4. Operação: referrals, CLI, README, backup e aceite do PRD.

## Verificação da entrega

O roadmap e a rastreabilidade foram criados em `.planning/ROADMAP.md` e `.planning/REQUIREMENTS.md`. A próxima entrega deve tornar `uv sync` e `uv run pytest` comandos reais.
