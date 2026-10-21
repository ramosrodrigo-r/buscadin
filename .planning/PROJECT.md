# Buscadin Jobs Bot

## What This Is

Serviço privado que coleta oportunidades remotas de fontes autorizadas, normaliza e classifica vagas para residentes no Brasil e as envia para um chat privado do Telegram. O administrador revisa as oportunidades por comandos e botões, sem painel público, usuários externos ou publicação automática.

## Core Value

Entregar ao administrador vagas remotas verificáveis, sem inventar elegibilidade, salário ou links de indicação.

## Requirements

### Validated

- [x] PRD, limites de escopo e stack obrigatória documentados.
- [x] Fundação, persistência e migrations — Entrega 01.
- [x] Coleta Himalayas, normalização, elegibilidade e idempotência — Entrega 02.
- [x] Telegram HTTP, polling, revisão e outbox — Entrega 03.
- [x] Referrals, CLI e operação documentada — Entrega 04.
- [x] Gestão de programas/links e fila editorial manual — Entrega 05.

### Active

Nenhuma — Etapa 2 implementada e verificada localmente.

### Out of Scope

- Frontend, signup, múltiplos usuários e API pública — não fazem parte do MVP.
- Scraping autenticado, LinkedIn, LLM, analytics de conversão e publicação social — proibidos ou adiados pelo PRD.

## Context

O repositório começou apenas com `PRD_Buscadin_Telegram_Bot.md` e `AGENTS.md`. O PRD exige Python 3.12+, `uv`, `httpx` assíncrono, SQLAlchemy 2, Alembic, SQLite, Pydantic Settings, pytest e Bot API HTTP oficial.

## Constraints

- **Fontes**: somente APIs públicas/oficiais autorizadas; respeitar limites e atribuição.
- **Acesso**: somente `TELEGRAM_ADMIN_CHAT_ID` e, se configurado, `TELEGRAM_ADMIN_USER_ID`.
- **Segurança**: tokens e URLs de indicação nunca são inferidos ou registrados em logs.
- **Operação**: SQLite no MVP, preparado para PostgreSQL via `DATABASE_URL`; sem Redis/Celery.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Himalayas como primeiro conector | API pública documentada e sem chave obrigatória | ✓ Good |
| Long polling com `getUpdates` | Caminho mais simples para o MVP privado | ✓ Good |
| Jobs e notificações idempotentes | Reinícios não podem duplicar alertas | ✓ Good |

---
*Last updated: 2026-10-21 after Etapa 2 verification*
