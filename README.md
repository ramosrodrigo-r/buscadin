# Buscadin Jobs Bot

Bot privado do Telegram para coletar vagas remotas de fontes autorizadas, classificar a elegibilidade para o Brasil e enviar oportunidades ao administrador para revisão. O escopo e as restrições estão em `PRD_Buscadin_Telegram_Bot.md`.

Consulte `docs/entregas/` para o processo e o resultado de cada entrega e `.planning/` para roadmap, requisitos e estado do projeto.

## Requisitos

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Token de bot criado via [@BotFather](https://t.me/BotFather)

## Setup local

```bash
uv sync
cp .env.example .env
uv run alembic upgrade head
uv run pytest
```

Preencha no `.env`:

```dotenv
TELEGRAM_BOT_TOKEN=token_do_bot
TELEGRAM_ADMIN_CHAT_ID=123456789
TELEGRAM_ADMIN_USER_ID=123456789
```

Para obter o `chat_id`, inicie voluntariamente uma conversa com o bot e consulte um update recebido por `getUpdates`. O token nunca deve aparecer em commits, logs ou URLs.

## Executar

```bash
uv run python -m buscadin_bot.main
# ou
uv run buscadin
```

O processo faz coleta da Himalayas, enfileira vagas novas, envia a outbox ao chat privado e consulta updates por long polling. A API pública da Himalayas não exige chave; `HIMALAYAS_API_KEY` é opcional para limites maiores. A atribuição da fonte deve ser preservada.

## Referrals oficiais

Links são cadastrados somente quando obtidos em programa oficial e autorizados para compartilhamento:

```bash
uv run buscadin referral add \
  --company "Example" \
  --url "https://official.example/referral" \
  --scope company \
  --approved-for-public-sharing
uv run buscadin referral list
```

O CLI armazena a URL exatamente como fornecida. Não concatene `?ref=...` nem use links não verificados. Para uma vaga específica, inclua `--scope job --source-job-id ID`.

### Etapa 2: programas e links

Programas e links novos usam entidades separadas. Cadastre primeiro o programa com permissão pública explicitamente confirmada:

```bash
uv run buscadin program add \
  --company "Example" \
  --name "Programa oficial" \
  --scope GLOBAL \
  --public-sharing-allowed \
  --allowed-domain official.example \
  --evidence-url "https://official.example/terms"
uv run buscadin link add \
  --program-id 1 \
  --url "https://official.example/referral" \
  --verified-by admin
```

Escopos disponíveis: `GLOBAL`, `POR_VAGA` e `POR_PROJETO`. `--allowed-domain` é opcional e pode ser repetido. A resolução segue vaga > projeto/campanha > global. O bot classifica cada vaga como `LINK_VALIDADO`, `AGUARDANDO_LINK` ou `SEM_PROGRAMA`, mantendo `application_url` separado do destino editorial.

No Telegram, use `/indicacoes`, `/pendentes`, `/programas`, `/vaga <id>` e `/vincular <id_vaga> <id_programa>`. O fluxo `/vincular` pede a URL, confirmação manual da origem oficial e validade opcional. Nenhuma plataforma externa é chamada.

## Fila editorial

O estado comercial da indicação é independente do estado editorial: `NOVA`, `SELECIONADA`, `PRONTA`, `PUBLICADA` ou `DESCARTADA`. Use `/selecionadas`, os botões de seleção/preparação ou `/publicar <id> <canal> [url]`. A preparação gera texto copiável, com transparência de possível comissão quando houver link validado; a publicação é apenas registrada manualmente.

## Migrations e backup

```bash
uv run alembic upgrade head
uv run alembic downgrade -1
sqlite3 data/buscadin.db ".backup 'data/buscadin-$(date +%Y%m%d).db'"
```

Faça o backup com o processo parado ou usando o mecanismo `.backup` do SQLite. O diretório `data/` não é versionado.

## Estrutura

```text
src/buscadin_bot/{config.py,main.py,cli.py}
src/buscadin_bot/db/          # SQLAlchemy e persistência
src/buscadin_bot/sources/     # conectores autorizados
src/buscadin_bot/services/    # coleta, classificação, referrals, outbox
src/buscadin_bot/telegram/    # Bot API HTTP, polling e handlers
migrations/                   # Alembic
tests/                        # pytest com APIs mockadas
```

Não são usados `python-telegram-bot`, `aiogram`, Redis, Celery, scraping autenticado ou links afiliados inferidos.
