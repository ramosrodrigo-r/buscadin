# Phase 4: Operação e aceite - Context

**Gathered:** 2026-10-21  
**Status:** Ready for execution

## Phase Boundary

Permitir que o administrador cadastre referrals oficiais sem alteração de URL, resolver somente links válidos e aplicáveis, documentar a operação local e verificar os critérios de aceite do PRD.

## Implementation Decisions

- CLI é o caminho do MVP para cadastrar referral; Telegram não edita links.
- Resolver exige URL `http(s)`, `enabled`, `approved_for_public_sharing`, `verified_at` e validade temporal.
- Referral específico da vaga vence a associação por empresa; campanhas não são aplicadas automaticamente sem chave explícita.
- README documentará BotFather, `.env`, migrations, execução, testes e backup SQLite.

## Canonical References

- `PRD_Buscadin_Telegram_Bot.md` §4.4, §7, §10 — regras de referral, configuração e aceite.
- `src/buscadin_bot/telegram/formatters.py` — contrato de exibição do referral.
- `src/buscadin_bot/db/models.py` — campos persistidos.

## Acceptance

- Referral não validado, desabilitado, expirado ou não aprovado não aparece.
- CLI adiciona/lista referrals sem concatenar parâmetros.
- README permite reproduzir instalação e execução local.
- Todos os testes e migrations passam em uma verificação limpa.
