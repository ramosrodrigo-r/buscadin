# Entrega 02 — Coleta e elegibilidade

**Data:** 2026-10-21  
**Status:** concluída

## O que foi entregue

- Contrato `JobSource` e modelo `RawJob` para manter conectores isolados.
- Conector `HimalayasSource` usando a API JSON pública, `httpx` assíncrono, timeout, API key opcional e retry de 429/5xx com backoff.
- Parser dos campos de título, empresa, descrição, candidatura, países, categorias, salário e data.
- Normalização do HTML externo e conversão para o modelo persistido.
- Classificação determinística para categorias prioritárias e elegibilidade `confirmed_br`, `unknown` ou `excluded_br`.
- Repositório com upsert por `(source, source_job_id)` e uma única notificação por vaga elegível.
- `Collector` que isola erro da fonte, faz rollback e registra métricas da execução.

## Verificação executada

```text
uv run pytest                   11 passed
```

Os testes usam `httpx.MockTransport`; não acessam a API real. Há cobertura para payload válido, retry após 429, salário ausente, LATAM como `unknown`, US-only como excluído e segunda coleta sem duplicação.

## Regras preservadas

O código não transforma LATAM/global em aceitação confirmada, não inventa salário e não cria URL de indicação. A URL de candidatura retornada pela Himalayas é preservada.

## Próxima entrega

Adicionar a Bot API HTTP oficial, mensagens HTML escapadas, teclado inline, callbacks de aprovação/descarte, long polling com offset persistido e worker da outbox.
