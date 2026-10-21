# Requirements: Buscadin Jobs Bot

**Defined:** 2026-10-21  
**Core Value:** Entregar ao administrador vagas remotas verificáveis, sem inventar elegibilidade, salário ou links de indicação.

## v1 Requirements

### Foundation

- [x] **FND-01**: O projeto instala com `uv sync` e inicia com configuração validada por variáveis de ambiente. — Entrega 01
- [x] **FND-02**: Jobs, referências, outbox e estado de updates persistem em SQLite via SQLAlchemy 2/Alembic. — Entrega 01

### Collection

- [x] **COL-01**: Uma fonte habilitada busca vagas por HTTP assíncrono com timeout, retry e isolamento de falhas. — Entrega 02
- [x] **COL-02**: Vagas são normalizadas, deduplicadas por fonte e classificadas por categoria e elegibilidade Brasil. — Entrega 02
- [x] **COL-03**: A segunda execução da mesma coleta não cria jobs nem notificações duplicadas. — Entrega 02

### Telegram

- [x] **TEL-01**: O bot envia vagas novas ao chat privado usando somente a Bot API HTTP oficial. — Entrega 03
- [x] **TEL-02**: Comandos, callbacks e long polling são aceitos somente pelo administrador e são idempotentes. — Entrega 03
- [x] **TEL-03**: A outbox registra `pending`, `sent` e `failed`, com tentativas e backoff. — Entrega 03

### Referrals & Operations

- [x] **REF-01**: Referral só aparece quando validado, habilitado, aplicável e não expirado. — Entrega 04
- [x] **OPS-01**: README e documentação de entrega ensinam configuração, execução, migrations e backup. — Entrega 04

## v2 Requirements

- Webhook Telegram, conectores Greenhouse/Lever/Ashby e UI pública.
- Métricas de clique/conversão, matching semântico, LLM e publicação em redes sociais.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Cadastro de múltiplos usuários | O MVP é privado para um administrador. |
| Scraping de páginas protegidas | Respeito a termos, robots e anti-bot. |
| Geração de links afiliados | O PRD exige URLs obtidas em programas oficiais. |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| FND-01, FND-02 | Phase 1 | Complete |
| COL-01, COL-02, COL-03 | Phase 2 | Complete |
| TEL-01, TEL-02, TEL-03 | Phase 3 | Complete |
| REF-01, OPS-01 | Phase 4 | Complete |

**Coverage:** 10 v1 requirements, all mapped to phases.

## Etapa 2 Requirements

- [x] **ET2-01**: Cada vaga possui estado comercial exclusivo, motivo e resolução de link por precedência documentada. — Entrega 05
- [x] **ET2-02**: Programas e links são entidades distintas, auditáveis, vigentes e protegidos contra URL fabricada. — Entrega 05
- [x] **ET2-03**: A fila editorial possui estados independentes, texto copiável e registro manual de canal/publicação. — Entrega 05
- [x] **ET2-04**: Telegram e CLI permitem cadastro/revisão autorizada sem publicar automaticamente em canais externos. — Entrega 05

---
*Requirements defined: 2026-10-21*
