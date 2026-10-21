# Roadmap: Buscadin Jobs Bot

## Overview

Quatro entregas formam um vertical slice operacional: fundação persistente, coleta/classificação, Telegram administrativo e endurecimento/documentação. Cada entrega deixa código executável, testes e um relatório Markdown em `docs/entregas/`.

## Phases

- [x] **Phase 1: Fundação executável** - Configuração, banco, migrations e contratos base.
- [x] **Phase 2: Coleta e elegibilidade** - Himalayas, normalização, deduplicação e classificação.
- [x] **Phase 3: Telegram e outbox** - Bot API HTTP, polling, comandos e revisão idempotente.
- [x] **Phase 4: Operação e aceite** - Referrals, CLI, documentação, backup e verificação final.
- [x] **Phase 5: Etapa 2 — indicações e editorial** - Programas, links, auditoria e fila editorial manual.

## Phase Details

### Phase 1: Fundação executável
**Goal**: Instalar o projeto e persistir o domínio principal com SQLite.
**Depends on**: Nothing
**Requirements**: [FND-01, FND-02]
**Success Criteria**:
  1. `uv sync` e `uv run pytest` funcionam em ambiente limpo.
  2. Modelos de Job, Referral, Notification e estado de update existem com constraints idempotentes.
  3. `alembic upgrade head` cria o schema local.
**Plans**: 1 plan

Plans:
- [ ] 01-01: Bootstrap Python, configuração, persistência, migrations e testes base

### Phase 2: Coleta e elegibilidade
**Goal**: Buscar uma fonte autorizada e transformar dados brutos em vagas elegíveis.
**Depends on**: Phase 1
**Requirements**: [COL-01, COL-02, COL-03]
**Success Criteria**:
  1. Himalayas é consultado por `httpx` com retries e limite configurável.
  2. Dados são normalizados sem inventar salário ou elegibilidade.
  3. Upsert e outbox são idempotentes.
**Plans**: 1 plan

Plans:
- [ ] 02-01: Conector Himalayas, pipeline de coleta e classificação

### Phase 3: Telegram e outbox
**Goal**: Notificar e permitir revisão exclusivamente pelo administrador.
**Depends on**: Phase 2
**Requirements**: [TEL-01, TEL-02, TEL-03]
**Success Criteria**:
  1. Mensagens HTML escapadas têm dados da vaga, fonte e teclado inline.
  2. `getUpdates` persiste offset e callbacks aprovam/descartam sem repetir efeitos.
  3. Falhas Telegram ficam na outbox e podem ser tentadas novamente.
**Plans**: 1 plan

Plans:
- [ ] 03-01: Cliente Bot API, formatadores, poller e handlers

### Phase 4: Operação e aceite
**Goal**: Fechar referrals, comandos operacionais, documentação e critérios de aceite.
**Depends on**: Phase 3
**Requirements**: [REF-01, OPS-01]
**Success Criteria**:
  1. Referral inválido, expirado ou não aprovado nunca aparece.
  2. README documenta `.env`, BotFather, migrations, coleta e backup.
  3. Suite final cobre critérios do PRD sem APIs reais.
**Plans**: 1 plan

Plans:
- [ ] 04-01: Resolver de referrals, CLI, README e verificação final

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Fundação executável | 1/1 | Complete | 2026-10-21 |
| 2. Coleta e elegibilidade | 1/1 | Complete | 2026-10-21 |
| 3. Telegram e outbox | 1/1 | Complete | 2026-10-21 |
| 4. Operação e aceite | 1/1 | Complete | 2026-10-21 |
| 5. Etapa 2 — indicações e editorial | 1/1 | Complete | 2026-10-21 |
