# Phase 2: Coleta e elegibilidade - Context

**Gathered:** 2026-10-21  
**Status:** Ready for execution

## Phase Boundary

Buscar vagas na API pública da Himalayas, converter o payload em um modelo interno estável, classificar categoria e elegibilidade Brasil e persistir novos itens sem duplicação.

## Implementation Decisions

- O endpoint padrão é `https://himalayas.app/jobs/api`, com `limit` no máximo 20 e paginação por `cursor`.
- `applicationLink` da fonte é preservado como URL de candidatura; a URL da vaga segue o formato público baseado no `companySlug` e `guid` quando disponível.
- Apenas evidência explícita de Brasil gera `confirmed_br`; restrição excludente gera `excluded_br`; restante é `unknown`.
- O conector não faz scraping de páginas HTML e não inventa salários, países ou referrals.

## Canonical References

- `PRD_Buscadin_Telegram_Bot.md` §4.1–4.3 — conectores, campos e classificação.
- `https://himalayas.app/api` — endpoint, paginação e atribuição da API pública.
- `src/buscadin_bot/db/models.py` — schema persistente da Entrega 01.

## Acceptance

- Resposta HTTP válida vira `RawJob`.
- 429/5xx respeita retry/backoff limitado.
- A mesma vaga atualizada mantém o mesmo `Job.id` e uma única `Notification`.
- Vaga sem salário permanece com `salary_disclosed=False`.
