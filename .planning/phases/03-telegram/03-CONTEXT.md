# Phase 3: Telegram e outbox - Context

**Gathered:** 2026-10-21  
**Status:** Ready for execution

## Phase Boundary

Enviar vagas pendentes ao chat privado e processar comandos/callbacks do administrador por HTTP Bot API oficial, com long polling e offset persistido.

## Implementation Decisions

- Usar `sendMessage`, `getUpdates`, `answerCallbackQuery` e `editMessageReplyMarkup` diretamente via `httpx`; nenhuma biblioteca de bot.
- Todas as strings externas passam por `html.escape` antes de `parse_mode=HTML`.
- `callback_data` é curta e determinística (`approve:<id>`/`discard:<id>`); ações repetidas são no-op.
- O offset só avança depois de o update ser processado, para não perder callbacks em falhas.
- Falhas de envio incrementam tentativas e usam `Retry-After` quando a API fornece essa informação.

## Canonical References

- `PRD_Buscadin_Telegram_Bot.md` §4.5–4.6 — mensagens, botões, comandos e outbox.
- `https://core.telegram.org/bots/api` — métodos oficiais e semântica de `getUpdates`/callbacks.
- `src/buscadin_bot/db/models.py` e `src/buscadin_bot/db/repository.py` — estado persistente.

## Acceptance

- API client rejeita resposta `ok=false` sem vazar token nos logs.
- Mensagem sem referral mostra `Indicação: não configurada`.
- Usuário/chat não autorizados não alteram jobs.
- Offset é persistido em `bot_state` após cada update tratado.
