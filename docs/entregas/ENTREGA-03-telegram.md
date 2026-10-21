# Entrega 03 — Telegram e outbox

**Data:** 2026-10-21  
**Status:** concluída

## O que foi entregue

- `TelegramClient` assíncrono usando diretamente os métodos HTTP oficiais `sendMessage`, `getUpdates`, `answerCallbackQuery` e `editMessageReplyMarkup`.
- Mensagens HTML com conteúdo externo escapado, salário ausente como `Não informado` e teclado para aprovar, descartar e abrir a vaga.
- Handlers para `/start`, `/ajuda`, `/novas`, `/pendentes`, `/indicacoes` e `/resumo`.
- Autorização por `TELEGRAM_ADMIN_CHAT_ID` e, opcionalmente, `TELEGRAM_ADMIN_USER_ID`.
- Callbacks idempotentes que alteram `review_status`, respondem rapidamente e removem o teclado.
- Long polling com `getUpdates`, offset persistido em `bot_state` e reprocessamento quando o handler falha.
- `NotificationWorker` que atualiza `pending`, `sent`, `failed`/`dead`, tentativas, erro e `next_attempt_at`.
- `main.py` integrado com coleta periódica, outbox e polling.

## Verificação executada

```text
uv run pytest                   17 passed antes da Entrega 04
```

Os testes usam `httpx.MockTransport` e doubles locais; nenhuma chamada real ao Telegram é feita durante a suíte.

## Decisões de segurança

O token é usado somente para montar o endpoint em memória e não aparece em payloads de log. Updates de chats externos são ignorados; callbacks externos recebem resposta de não autorização sem alterar o banco.

## Próxima entrega

Adicionar resolver de referrals oficiais, CLI administrativo, documentação de operação, backup e verificação final do MVP.
