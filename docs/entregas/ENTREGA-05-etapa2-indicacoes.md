# Entrega 05 — Etapa 2: indicações e preparação editorial

**Data:** 2026-10-21  
**Status:** concluída

## O que foi entregue

- Migrations `0002_indications_editorial` e `0003_referral_domains`, compatíveis com o banco da Etapa 1 e sem apagar dados existentes.
- Entidades separadas para `ReferralProgram`, `ReferralLink`, `EditorialPublication` e `AuditEvent`.
- Três estados comerciais exclusivos: `LINK_VALIDADO`, `AGUARDANDO_LINK` e `SEM_PROGRAMA`.
- Resolução com precedência vaga > projeto/campanha > global, validade, permissão pública e URL oficial preservada.
- Domínios esperados opcionais por programa; host fora da regra não vira link validado.
- Reclassificação auditável e reenvio controlado quando um estado comercial muda; link expirado reabre conteúdo `PRONTA` para revisão.
- Estados editoriais independentes: `NOVA`, `SELECIONADA`, `PRONTA`, `PUBLICADA` e `DESCARTADA`.
- Texto editorial copiável, com `application_url` separado de `referral_url` e transparência de possível comissão.
- Comandos Telegram: `/programas`, `/vincular`, `/confirmar_link`, `/selecionadas`, `/publicadas`, `/vaga` e `/publicar`, além dos comandos existentes.
- Fluxo temporário e autorizado para vincular URL manual, com confirmação de origem/permissão e expiração opcional.
- CLI para programas e links: `buscadin program add/list` e `buscadin link add/list`.

## Regras de segurança preservadas

O bot nunca cria `?ref=...`, nunca transforma candidatura em afiliado e nunca envia conteúdo a Instagram, TikTok, Kwai ou Telegram público. Um programa sem permissão pública explícita não produz `LINK_VALIDADO`.

## Verificação

```text
uv run pytest                   27 passed
uv run alembic upgrade head     OK (0003_referral_domains)
uv run alembic downgrade 0001_initial / upgrade head  OK
```

## Operação resumida

Cadastre o programa com `--public-sharing-allowed`, associe o link obtido oficialmente e, no Telegram, use `/pendentes` para vagas que ainda precisam de link. Use `/selecionadas` e `/publicar` somente para registrar decisões manuais.

## Próximos passos

Revalidar a operação com dados reais do administrador, confirmar regras de cada programa externo e, se necessário, criar um job dedicado para avisos de expiração antes de ampliar os canais manuais.
