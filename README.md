# Buscadin

Plataforma brasileira de curadoria de vagas remotas, reunindo o bot privado do Telegram, o portal público, o painel administrativo e os crawlers de fontes autorizadas. O sistema classifica a elegibilidade para o Brasil e envia oportunidades ao administrador para revisão antes da publicação. O escopo e as restrições estão em `PRD_Buscadin_Telegram_Bot.md`.

Este repositório contém a aplicação completa do Buscadin em um único serviço Python: coleta, triagem, catálogo, publicação, portal web, painel admin e integração com Telegram.

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

## Portal público

O painel privado é iniciado com `uv run buscadin-admin`, separado do processo
público, em `http://127.0.0.1:8081`. Consulte [operação do painel](docs/ADMIN.md)
para senha, banco compartilhado, acesso via SSH e controles disponíveis.

O portal usa o mesmo domínio de publicação, mas deve ser executado como um serviço separado no Dokploy. Ele lê somente snapshots aprovados e expõe a API privada usada pelo bot:

```bash
uv run alembic upgrade head
uv run buscadin-portal
```

Configure `SITE_API_TOKEN`, `TELEGRAM_ADMIN_USER_ID`, `SITE_BASE_URL` e `SITE_OFFICIAL_DOMAINS` no serviço do portal. O bot usa o mesmo `SITE_API_TOKEN` em `SITE_API_URL`; o token não deve aparecer em logs ou URLs. O proxy deve encaminhar o domínio público para a porta `PORTAL_PORT` e manter a API `/internal/*` inacessível publicamente por firewall ou rota interna.

O roteiro de serviços, variáveis, migration e rollback está em `docs/DEPLOYMENT-MVP.md`.

Para registrar requisitos explícitos encontrados na fonte, sempre informe a evidência. Informação desconhecida deve permanecer `unknown`:

```bash
uv run buscadin requirements set --job-id 42 --actor admin \
  --education-status not_required \
  --education-evidence "A fonte informa que não exige graduação."
uv run buscadin requirements show --job-id 42
```

Alterar requisitos registra um evento de auditoria e exige uma nova prévia para qualquer publicação web atualizada.

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

## Integração com o catálogo (em desenvolvimento)

O cliente, os handlers e o servidor HTTP do portal estão implementados. A
integração só deve ser habilitada depois que o serviço do portal estiver
implantado e o token compartilhado configurado; não aponte o bot para um
endpoint inexistente.
`SITE_API_URL` e `SITE_API_TOKEN` habilitam o cliente privado. Ambos os IDs de
administrador do Telegram são obrigatórios nesse modo. HTTP sem TLS é aceito
somente em loopback. O cliente não segue redirects da API interna.

- `/publicar_site <id> <oficial|indicacao>` solicita resumo editorial e apresenta
  conteúdo/destino antes do botão de confirmação. A prévia não publica.
- `/atualizar_site <id> <oficial|indicacao>` usa o mesmo fluxo com nova versão.
- `/site <id>` consulta o resultado persistido, inclusive após falha de rede.
- `/despublicar_site <id>` pede confirmação para retirada.
- `/pendentes_site [página]` e `/publicadas_site [página]` consultam a plataforma.
- `/requisitos_site <id>` solicita graduação e experiência com evidência textual; estados explícitos exigem prova e não reescrevem uma publicação já aprovada.
- `/cancelar` encerra a coleta do resumo. Prévias já emitidas expiram em 15 minutos.

`/publicar` continua registrando a publicação editorial manual em canais externos.
O cliente não escreve tabelas da plataforma: usa o contrato da API privada.

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
