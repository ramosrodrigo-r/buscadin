# PRD — Buscadin Jobs Bot (MVP)

**Versão:** 1.0  
**Status:** Planejamento  
**Escopo:** Bot privado do Telegram e pipeline autônomo de coleta de vagas. **Não inclui o site Buscadin nem publicação nas redes sociais.**

## 1. Objetivo

Construir um serviço independente que coleta oportunidades de trabalho remoto em fontes autorizadas, normaliza e deduplica registros, identifica vagas potencialmente acessíveis a residentes no Brasil e as envia a um chat privado do Telegram. O bot permite revisar e classificar vagas e associar manualmente links de indicação válidos, sem depender do futuro buscadin.app.

**Princípio:** coleta automatizada, indicação verificável e distribuição controlada. Nunca inventar parâmetros de afiliado nem afirmar elegibilidade ou remuneração sem evidência.

## 2. Stack obrigatória

- **Linguagem:** Python 3.12+.
- **Gerenciamento de projeto e dependências:** **uv**; manter `pyproject.toml` e `uv.lock` versionados. Executar com `uv run`, adicionar pacotes com `uv add`, testes com `uv run pytest`.
- **Telegram:** **Bot API oficial via HTTP**, usando `httpx` assíncrono. **Não usar** `python-telegram-bot`, `aiogram`, grammY ou Telegraf.
- **Persistência MVP:** SQLite por padrão com SQLAlchemy 2 + Alembic; arquitetura preparada para PostgreSQL via configuração de `DATABASE_URL`.
- **Coleta HTTP:** `httpx` com timeouts, retries com backoff e respeito aos limites das fontes.
- **Validação/configuração:** Pydantic Settings.
- **Agendamento:** loop simples com intervalo configurável ou execução separada via cron; sem Redis/Celery/BullMQ no MVP.
- **Testes:** pytest, pytest-asyncio e mocks de HTTP.
- **Deploy:** Dockerfile opcional + execução local; configuração por variáveis de ambiente.

## 3. Público e acesso

- Um administrador (dono do Buscadin) usando **chat privado do Telegram**.
- Permitir somente `TELEGRAM_ADMIN_CHAT_ID` e, se aplicável, `TELEGRAM_ADMIN_USER_ID`; ignorar mensagens de outros usuários.
- Não expor painel público, signup ou gestão de múltiplos usuários.

## 4. Escopo funcional do MVP

### 4.1 Coleta automática

Criar interface `JobSource` com método `fetch_jobs()` e conectores isolados.

1. **Primeiro conector:** API pública da Himalayas, sujeito à verificação dos termos aplicáveis e atribuição exigida.
2. **Conectores seguintes:** páginas públicas de vagas via APIs oficiais de ATS (Greenhouse, Lever e Ashby), cadastrando *company board IDs* explicitamente; adicionar somente após validar termos e endpoints.
3. Para empresas de AI Training (Mercor, micro1, Outlier, Alignerr, Appen, OneForma etc.), **não presumir existência de API pública**. Permitir cadastrar vagas/URLs e indicações manualmente até haver integração autorizada.
4. Fonte individualmente habilitável/desabilitável por configuração; registrar último sucesso, erro e quantidade coletada.
5. Recoleta configurável, inicialmente a cada 12 horas; não tentar fazer scraping autenticado nem contornar proteção anti-bot.

### 4.2 Normalização e deduplicação

Modelo `Job` mínimo:

- `id`, `source`, `source_job_id`, `source_url`, `application_url`;
- `company`, `title`, `description`, `category`, `employment_type`;
- `remote_type`, `eligible_countries`, `eligibility_status` (`confirmed_br`, `unknown`, `excluded_br`);
- `salary_min`, `salary_max`, `currency`, `salary_period`, `salary_disclosed`;
- `language_requirements`, `posted_at`, `first_seen_at`, `last_seen_at`, `last_checked_at`;
- `status` (`active`, `stale`, `inactive`), `review_status` (`pending`, `approved`, `discarded`).

Preservar `source_job_id` único por fonte e detectar possíveis duplicações interfontes por empresa, título e URL canônica. Nunca eliminar registros com baixa confiança de duplicação sem sinalizar. Usar dados estruturados quando disponíveis; ausência de salário permanece `não informado`. Não converter vagas 'Remote US only' em 'aceita Brasil'.

### 4.3 Classificação e filtro

- Priorizar categorias: Data Labeling, AI Training, AI Evaluation, Search Quality, Annotation, QA e desenvolvimento remoto.
- Heurísticas determinísticas para títulos/descrições e localização; sem LLM obrigatório no MVP.
- `confirmed_br` apenas quando o anúncio explicitamente aceita Brasil; `unknown` para LATAM/global sem confirmação; `excluded_br` quando há restrição excludente.
- Enviar por padrão `confirmed_br` e `unknown`, **rotulando claramente os casos não confirmados**. Não enviar `excluded_br`.
- Persistir texto/evidência que fundamenta a classificação quando possível.

### 4.4 Links de referência

Modelo `Referral` mínimo:

- `id`, `company`, `source_job_id` (opcional), `referral_url`, `scope` (`job`, `company`, `campaign`);
- `approved_for_public_sharing` (bool), `verified_at`, `expires_at`, `notes`, `enabled`.

Regras:

- Links **somente** obtidos pelo administrador nos programas oficiais ou por API autorizada.
- `ReferralResolver` aplica apenas associações válidas para aquela vaga/campanha e não expiradas.
- **Não** concatenar `?ref=...` ou construir URLs de indicação por inferência.
- Se não houver link validado, usar `application_url` oficial e marcar 'Indicação: não configurada'.
- Rastrear cliques/conversões **não faz parte do MVP**; nenhuma comissão é presumida.

### 4.5 Notificações pelo Telegram

Enviar mensagens formatadas por `sendMessage` com `parse_mode=HTML` (escape de conteúdo externo), contendo:

- Cargo e empresa;
- categoria, local elegível e status de confirmação Brasil;
- remuneração somente quando divulgada pela fonte;
- fonte, data de captura e link da vaga;
- link de indicação **apenas se validado** e sinalização de relação de indicação remunerada;
- botões inline: `Aprovar`, `Descartar` e `Ver vaga`.

Usar `inline_keyboard` e `callback_query` pela **Bot API HTTP oficial**. Consultar updates com `getUpdates` (long polling) para a primeira versão; garantir offset persistido ou estratégia idempotente para não reaplicar callbacks. Confirmar callbacks com `answerCallbackQuery`. Caso migre a webhook, tratar como evolução futura.

Implementar fila/outbox de notificações com status (`pending`, `sent`, `failed`) e tentativas com backoff; nunca reenviar uma vaga repetida por falha de reinicialização. Agrupar lotes de mensagens e limitar volume por execução para evitar spam.

### 4.6 Comandos administrativos

- `/start` — orientação inicial (somente admin).
- `/novas` — últimas vagas ainda não revisadas.
- `/pendentes` — vagas aguardando avaliação.
- `/indicacoes` — resumo das vagas com links de indicação ativos.
- `/resumo` — métricas das últimas 24 horas: encontradas, duplicadas, enviadas, aprovadas, descartadas e falhas.
- `/ajuda` — comandos disponíveis.

No MVP, o cadastro/edição de links de indicação pode ocorrer por arquivo de configuração ou script CLI seguro (`uv run python -m app.cli ...`). **Não** é obrigatório editar links diretamente por mensagens do Telegram.

## 5. Fluxo principal

1. Scheduler aciona cada conector habilitado.
2. Conector busca somente dados permitidos, registra erros e normaliza resultados.
3. Serviço de persistência executa upsert e identifica novos itens.
4. Classificador determina categoria e elegibilidade geográfica.
5. Resolver encontra link de referência oficialmente cadastrado e válido, quando houver.
6. Notificações de vagas novas que passam pelo filtro entram na outbox.
7. Worker envia mensagens ao chat privado e salva `message_id`.
8. Admin aprova/descarta via botão; callback atualiza `review_status` e edita/responde à mensagem sem duplicar ação.
9. Vagas aprovadas ficam armazenadas para uso futuro, **sem publicação automática**.

## 6. Estrutura sugerida

```text
buscadin-jobs-bot/
├── pyproject.toml
├── uv.lock
├── .env.example
├── README.md
├── src/buscadin_bot/
│   ├── main.py
│   ├── config.py
│   ├── db/{models.py,session.py}
│   ├── sources/{base.py,himalayas.py,greenhouse.py,lever.py,ashby.py}
│   ├── services/{collector.py,normalizer.py,classifier.py,referrals.py,notifications.py}
│   ├── telegram/{api.py,poller.py,handlers.py,formatters.py}
│   └── cli.py
├── migrations/
└── tests/
```

Estrutura sugerida, não exigência de gerar módulos vazios. Implementar apenas o que o MVP usa.

## 7. Variáveis de ambiente

```dotenv
TELEGRAM_BOT_TOKEN=
TELEGRAM_ADMIN_CHAT_ID=
TELEGRAM_ADMIN_USER_ID=
DATABASE_URL=sqlite+aiosqlite:///./data/buscadin.db
COLLECT_INTERVAL_HOURS=12
MAX_NOTIFICATIONS_PER_RUN=20
LOG_LEVEL=INFO
```

Token é segredo: não registrar nos logs nem versionar `.env`. Documentar como criar o bot via BotFather e capturar o `chat_id` em conversa iniciada voluntariamente pelo administrador.

## 8. Requisitos não funcionais

- Jobs e callbacks idempotentes, de forma que reinícios não gerem duplicações.
- Backoff exponencial para HTTP 429/5xx, observando `retry_after` quando enviado pelo Telegram.
- Logs estruturados de coleta, deduplicação e envio, sem tokens nem dados sensíveis.
- Timeouts e falhas por fonte isolados: erro em uma API não interrompe as demais.
- SQLite persiste em volume em produção; backups periódicos simples documentados.
- Atribuição exigida por fontes, armazenamento moderado de dados e respeito às condições de redistribuição.
- Interface de persistência preparada para futuro consumo externo, **sem construir API pública agora**.

## 9. Fora de escopo

- Frontend, autenticação de usuários, pagamentos, Premium ou banco da plataforma Buscadin.
- Instagram, TikTok, Kwai, newsletter, edição de vídeo, publicação ou agendamento de posts.
- Scraping de LinkedIn, dashboards logados ou geração automática não autorizada de links afiliados.
- LLM, RAG, busca semântica, matching de currículo, analytics de conversão e infraestrutura distribuída.
- Envio de mensagens a candidatos e coleta de dados pessoais de candidatos.

## 10. Critérios de aceite

1. `uv sync` instala o projeto e `uv run pytest` executa os testes.
2. `uv run python -m buscadin_bot.main` inicia poller e scheduler sem frameworks de bot.
3. Uma execução de coleta obtém vagas de pelo menos **uma API permitida** e as salva no banco.
4. A mesma coleta executada duas vezes não cria vagas ou notificações duplicadas.
5. Uma nova vaga compatível produz mensagem no chat privado com os dados disponíveis e fonte.
6. Comandos e botões funcionam só para administrador e as decisões persistem.
7. Falha temporária da API ou Telegram é registrada e reprocessada sem perder vagas.
8. Link de indicação só aparece quando cadastrado, validado e aplicável à vaga.
9. Uma vaga sem salário mostra 'Não informado', nunca valor inventado.
10. README ensina configuração, execução local, bot do BotFather, migrations e backup.

## 11. Fases de implementação

- **Fase A (mínimo funcional):** uv, config, banco, API HTTP Telegram, long polling, um conector, normalização, upsert e alertas.
- **Fase B (operação):** botões/comandos, fila confiável, classificação geográfica e deduplicação.
- **Fase C (indicações):** registro de links, resolver, validade, métricas e novos conectores oficiais.

## 12. Decisões em aberto (não bloqueantes)

- Lista inicial de company board IDs a monitorar.
- Critério exato de envio: vagas `unknown` imediatamente ou em resumo separado.
- Qual frequência de coleta respeita cada fonte.
- Quais programas autorizam divulgação pública de links de indicação.

**Nota de separação arquitetural:** o PRD posterior do buscadin.app poderá consumir uma API/exportação da base do bot, mas nenhuma implementação do site é exigida por este documento.
