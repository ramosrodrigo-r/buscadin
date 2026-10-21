# PRD — Buscadin Jobs Bot | Etapa 2: Gestão de indicações e preparação editorial

**Status:** Proposto para implementação incremental  
**Produto:** Bot privado do Telegram, de uso exclusivo do administrador do Buscadin  
**Escopo:** Evolução do bot existente; **não** é o PRD da plataforma buscadin.app  
**Stack existente/prioritária:** Python, `uv`, Telegram Bot API oficial via HTTP. Reutilizar banco, scheduler, coletores e arquitetura já implementados; não reescrever componentes sem necessidade.

## 1. Contexto e objetivo

O bot existente coleta e entrega vagas ao administrador no Telegram. O objetivo desta etapa é qualificar cada vaga quanto à possibilidade de comissão por indicação e transformá-la em um item editorial que o administrador possa selecionar e divulgar **manualmente** nos canais do Buscadin (Instagram, TikTok, Kwai e outros).

O Telegram **não é um canal público de distribuição de vagas** e o bot **não realiza candidaturas, publica automaticamente em redes sociais nem gera links de afiliado sem integração oficial autorizada**.

### Resultado esperado

Para cada vaga coletada, o bot deve indicar claramente um dos três estados de referência:

1. `LINK_VALIDADO`: existe URL de indicação oficialmente obtida, vinculada à vaga ou ao escopo correto de um programa, com uso permitido para divulgação pública e verificação ainda válida.
2. `AGUARDANDO_LINK`: existe um programa potencialmente aplicável, porém falta cadastrar, confirmar ou renovar um link válido; **não** tratar o link de candidatura como afiliado.
3. `SEM_PROGRAMA`: nenhum programa de indicação aplicável foi identificado com evidência suficiente; exibir apenas a candidatura oficial.

**Importante:** Esses estados descrevem o vínculo comercial, **não** o estado de publicação do conteúdo. Manter ambos separadamente.

## 2. Público e responsabilidades

- **Usuário único:** administrador do Buscadin, autorizado por `TELEGRAM_ADMIN_CHAT_ID` e, para callbacks/mensagens, também por `TELEGRAM_ADMIN_USER_ID` quando disponível.
- **Bot:** coleta, normaliza, deduplica, classifica, avisa, recebe comandos e registra decisões.
- **Administrador:** obtém links nos painéis oficiais, confirma as permissões, decide o que divulgar e publica externamente.

## 3. Fora do escopo

- Desenvolvimento do site/agregador Buscadin.
- Publicação automática em Instagram, TikTok, Kwai ou Telegram público.
- Geração automática de links por engenharia reversa, scraping autenticado ou manipulação especulativa de parâmetros de URL.
- Automação de candidatura, promessas de contratação ou medição de comissões sem dados oficiais.
- Criação obrigatória de arte/vídeo por IA; nesta etapa, apenas dados e texto editorial reutilizável.
- Sistema multiusuário, autenticação pública e assinaturas.

## 4. Regras de negócio

### RN-01 — Estado comercial exclusivo

Cada vaga deve ter exatamente um dos três estados comerciais. O estado é derivado das evidências disponíveis e pode mudar com novas verificações.

### RN-02 — Programa de indicação e vaga são entidades distintas

Cadastrar programas por empresa/campanha com: identificador, nome, tipo (`GLOBAL`, `POR_VAGA`, `POR_PROJETO`), escopo de elegibilidade, regras de compartilhamento público, fonte da regra, validade e status ativo/inativo. Um programa pode existir sem se aplicar a todas as vagas da empresa.

### RN-03 — Nunca fabricar links

Não adicionar `?ref=`, trocar IDs ou montar URLs por suposição. Um link só pode ser considerado validado se tiver sido obtido pelo mecanismo oficial e associado ao escopo correto. Um link global somente poderá ser reaproveitado quando o programa permitir explicitamente esse uso.

### RN-04 — Hierarquia de resolução

1. Procurar link **específico da vaga** (preferência máxima), compatível e vigente.
2. Na ausência, procurar link **de campanha/projeto** comprovadamente aplicável.
3. Na ausência, procurar link **global** comprovadamente aplicável a essa vaga e autorizado para divulgação.
4. Havendo programa possivelmente aplicável, mas sem link apto, atribuir `AGUARDANDO_LINK`.
5. Sem programa identificado ou com programa comprovadamente inaplicável, atribuir `SEM_PROGRAMA`.

Se regras de publicidade, validade ou compatibilidade estiverem ausentes/incertas, não marcar `LINK_VALIDADO`. Registrar motivo e orientar revisão manual.

### RN-05 — Links e divulgação

- Guardar `application_url` oficial separadamente de `referral_url`.
- `destination_url` editorial: usar `referral_url` **somente** quando `LINK_VALIDADO`; caso contrário, usar `application_url` com rótulo explícito “candidatura oficial — sem indicação validada”.
- Não afirmar que existe remuneração garantida: recompensas dependem de requisitos da empresa.
- Texto pronto para postagem com indicação deve conter transparência de possível remuneração: exemplo “O Buscadin pode receber uma comissão se você se candidatar por este link e cumprir os critérios do programa.”
- Não inventar salários, elegibilidade para brasileiros, nível de inglês ou prazos.

### RN-06 — Estados editoriais independentes

Cada vaga tem `editorial_status` separado:

- `NOVA`: ainda não avaliada.
- `SELECIONADA`: escolhida para divulgação futura.
- `PRONTA`: texto e destino conferidos; pode ser publicada manualmente.
- `PUBLICADA`: administrador confirma publicação externa e informa canal opcional.
- `DESCARTADA`: não será divulgada por enquanto.

**Transição recomendada:** `NOVA -> SELECIONADA -> PRONTA -> PUBLICADA`, com descarte a partir de qualquer estado anterior. Não marcar `PUBLICADA` automaticamente por gerar/copiar texto. Se o link vencer após `PRONTA`, retornar para revisão e impedir uso editorial do link expirado.

### RN-07 — Alertas úteis, sem ruído

Notificar quando surgir vaga nova elegível, quando houver mudança de estado de indicação, quando link cadastrado expirar e quando vaga marcada como pronta deixar de estar ativa. Evitar reenviar a mesma notificação sem mudança relevante.

## 5. Histórias de usuário e critérios de aceite

### HU-01 — Visualizar estado de indicação

**Como** administrador, **quero** receber cada nova vaga com selo de indicação **para** decidir sua prioridade de divulgação.

**Aceite:** mensagem mostra título, empresa, país/escopo remoto (ou “não confirmado”), remuneração (somente se publicada), URL oficial, estado de indicação e motivo resumido. Exibir URL remunerada somente com `LINK_VALIDADO`.

### HU-02 — Cadastrar link manualmente

**Como** administrador, **quero** vincular um link oficial à vaga, campanha ou programa global **para** reutilizá-lo nas vagas corretas.

**Aceite:** fluxo `/vincular <id_vaga>` ou botão equivalente conduz à entrada da URL e seleção/validação do escopo; solicita confirmação da origem oficial, permissão de divulgação pública e eventual validade. Não aceitar links genéricos como links por vaga sem revisão de escopo. Mudança fica registrada com data e operador.

### HU-03 — Resolver estado automaticamente

**Como** administrador, **quero** que o bot associe links previamente validados quando aplicáveis **para** não repetir trabalho manual.

**Aceite:** associação idempotente; precedência vaga > campanha > global; link vencido, restrito ou fora do escopo nunca gera `LINK_VALIDADO`; atualização de programa recalcula vagas afetadas.

### HU-04 — Fila de pendências

**Como** administrador, **quero** consultar vagas com `AGUARDANDO_LINK` **para** completar a monetização antes da publicação.

**Aceite:** `/pendentes` lista vagas com ID, título, empresa e motivo; possui paginação e filtros simples por empresa; nunca apresenta uma indicação não verificada como confirmada.

### HU-05 — Selecionar e preparar postagem

**Como** administrador, **quero** marcar uma vaga como selecionada e gerar uma legenda-base **para** divulgar manualmente nas redes.

**Aceite:** ações “Selecionar”, “Preparar texto”, “Marcar pronta”, “Descartar” e “Marcar publicada” persistem; geração de texto utiliza apenas campos disponíveis; mostra URL de destino e aviso de indicação quando cabível. Formato copiável para Instagram/TikTok/Kwai sem envio a essas plataformas.

### HU-06 — Revisar publicação

**Como** administrador, **quero** registrar em qual canal publiquei **para** acompanhar a fila editorial.

**Aceite:** `/publicadas` ou botão “Marcar publicada” aceita canal opcional (`instagram`, `tiktok`, `kwai`, `outro`) e registra horário. Não cria postagem real.

## 6. UX do Telegram — exemplos de mensagens

### Exemplo A — LINK_VALIDADO

> 🟢 **AI Trainer — Empresa X**  
> Remoto: Brasil confirmado  
> Remuneração: não informada  
> Indicação: **LINK_VALIDADO** — link oficial associado a esta vaga  
> Candidatura: [URL de indicação oficial]  
> Nota editorial: o Buscadin pode receber comissão, conforme regras do programa.

Botões: `[Selecionar] [Preparar texto] [Detalhes]`.

### Exemplo B — AGUARDANDO_LINK

> 🟡 **Data Annotator — Empresa Y**  
> Indicação: **AGUARDANDO_LINK** — programa identificado, URL específica ainda não cadastrada  
> Candidatura oficial: [URL da empresa]  
> Ação: obtenha e vincule o link no painel oficial.

Botões: `[Vincular link] [Selecionar] [Descartar]`.

### Exemplo C — SEM_PROGRAMA

> ⚪ **Search Quality Rater — Empresa Z**  
> Indicação: **SEM_PROGRAMA** — não foi identificado programa aplicável  
> Candidatura oficial: [URL da empresa]

Botões: `[Selecionar] [Descartar] [Detalhes]`.

As três vagas acima são fictícias.

## 7. Modelo de dados mínimo (adaptar às tabelas existentes)

### `referral_programs`

- `id`, `company_id`, `name`, `scope_type` (`GLOBAL|POR_VAGA|POR_PROJETO`), `campaign_key` opcional
- `is_active`, `public_sharing_allowed` (`true|false|null`), `evidence_url`, `rules_notes`, `valid_from`, `valid_until`, `created_at`, `updated_at`

### `referral_links`

- `id`, `program_id`, `job_id` opcional, `campaign_key` opcional, `url`, `source` (`MANUAL|OFICIAL_API`), `verified_at`, `expires_at`, `is_active`, `verified_by`, `notes`

### `jobs` (novos campos na tabela já existente)

- `referral_status` (`LINK_VALIDADO|AGUARDANDO_LINK|SEM_PROGRAMA`)
- `referral_status_reason`, `resolved_referral_link_id` nullable
- `editorial_status` (`NOVA|SELECIONADA|PRONTA|PUBLICADA|DESCARTADA`)
- preservar `application_url`, `source_job_id`, `source`, `last_seen_at` e estado de validade da vaga

### `editorial_publications` (registro editorial opcional)

- `id`, `job_id`, `channel`, `published_at`, `post_url` opcional, `notes`

### `audit_events`

- `id`, `job_id`, `event_type`, `before_json`, `after_json`, `actor`, `created_at`

**Migração:** usar a ferramenta de migrações existente (Alembic se já adotado), com defaults seguros (`SEM_PROGRAMA` ou estado calculado por backfill; `NOVA`) e sem apagar dados coletados. Caso a distinção entre “programa desconhecido” e “comprovadamente inexistente” seja relevante, manter `referral_status_reason` explícito: `NAO_IDENTIFICADO` não equivale a prova de inexistência.

## 8. Interface do Telegram

Implementar com a **Telegram Bot API oficial via HTTP**, reutilizando o cliente HTTP atual; **não introduzir grammY/Telegraf**.

- Comandos propostos: `/novas`, `/pendentes`, `/indicacoes`, `/selecionadas`, `/publicadas`, `/vaga <id>`, `/vincular <id>`, `/ajuda`.
- Inline keyboards com `callback_data` curta e identificadores internos; nunca incluir URL sensível ou tokens nos callbacks.
- Usar `answerCallbackQuery` para encerrar estado de carregamento, `editMessageText` ou `editMessageReplyMarkup` quando necessário e enviar mensagens novas apenas se relevante.
- Registrar sessão simples/estado temporário para o fluxo de entrada de URL, com timeout e cancelamento `/cancelar`.
- Todas as ações de escrita devem exigir ID autorizado; ignorar chamadas de outros chats/usuários.
- Tratar duplicação de updates por `update_id`, reentrega e callback repetido de modo idempotente.

## 9. Componentes sugeridos (sem refatoração ampla)

- `referral_resolver.py`: aplicação das regras de precedência, compatibilidade, validade e permissão.
- `referral_repository.py`: persistência de programas e links.
- `editorial_service.py`: seleção, rascunhos, estado editorial e histórico.
- `telegram_handlers.py`: comandos e callbacks novos, integrados ao router já existente.
- `formatters.py`: textos de alerta e de postagem com transparência comercial.
- `referral_recheck_job.py`: reavaliação agendada de links e vagas impactadas.

Os nomes são orientativos: priorizar organização atual do projeto e minimizar alterações.

## 10. Requisitos não funcionais

- **Segurança:** token do Telegram e dados sensíveis apenas em variáveis de ambiente, nunca em logs; comandos e callbacks restritos ao administrador; validar URL (`https://` preferencialmente) e domínio esperado para o programa antes de ativar; não abrir automaticamente links arbitrários.
- **Confiabilidade:** deduplicação por identificador externo da vaga, atualização idempotente e log dos erros de rede; retry com backoff para respostas transitórias da Bot API; respeitar HTTP 429 e `retry_after`.
- **Rastreabilidade:** todo link deve ter fonte e data de verificação; toda mudança manual auditável.
- **Qualidade de conteúdo:** nunca alegar que uma vaga aceita brasileiros sem evidência; não inferir remuneração; avisar quando a vaga é potencialmente expirada.
- **Reuso futuro:** deixar programa, vaga, indicação e publicação como entidades distintas para posterior integração ao site, sem exigir que o site exista agora.
- **Dependências:** gerenciadas exclusivamente com `uv`; atualizar `pyproject.toml`/`uv.lock`; executar testes com `uv run pytest`.

## 11. Fluxos de exceção

1. **Link expirado ou programa desativado:** reclassificar como `AGUARDANDO_LINK` se programa ainda aplicável, ou `SEM_PROGRAMA` se não houver programa aplicável; notificar se houver conteúdo marcado `PRONTA`.
2. **Vaga encerrada:** manter histórico, não recomendar nova publicação e sinalizar materiais já preparados.
3. **URL digitada incorretamente:** não validar; manter `AGUARDANDO_LINK` e informar motivo.
4. **Programa permite apenas indicações privadas:** não validar o link para divulgação pública; manter pendente ou sem programa aplicável conforme a regra do programa.
5. **Vaga já publicada:** atualizações não apagam registro editorial; alertar mudanças relevantes sem repostar automaticamente.
6. **Sem certeza sobre regras de afiliado:** o bot não marca `LINK_VALIDADO` até que a evidência e o escopo sejam confirmados.

## 12. Testes e critérios de aceite gerais

Testes automatizados mínimos:

- Resolução dos três estados; precedência vaga > campanha > global.
- Link inválido, vencido, desativado, sem permissão pública ou fora de escopo não se torna validado.
- Reutilização de link global somente sob regra explicitamente autorizada.
- Ações repetidas do Telegram não criam múltiplos vínculos/publicações.
- Usuário não autorizado não modifica o banco.
- `destination_url` usa referência somente em `LINK_VALIDADO`.
- Vaga sem link ainda pode ser selecionada/divulgada por candidatura oficial, com aviso claro.
- Geração de legenda não inventa salário, país ou requisitos.
- Vaga inativa ou link vencido bloqueia `PRONTA` até nova revisão.
- Banco existente permanece íntegro após migração.

**Definition of Done:** bot recebe novas vagas com estado comercial fundamentado; administrador cadastra links verificados, administra pendências e organiza uma fila de divulgação; gera texto copiável e registra publicações manuais; nenhuma ação envia conteúdo diretamente às redes sociais.

## 13. Ordem de implementação

1. Inspecionar código existente, fluxos do bot, tabelas, migrations e testes; preservar compatibilidade.
2. Adicionar entidades/campos e migração com dados existentes intactos.
3. Implementar `ReferralResolver` e testes unitários.
4. Adicionar cadastro manual de programas e links, verificação de escopo, validade e permissões.
5. Atualizar mensagens Telegram, comandos e botões; autenticação do administrador.
6. Implementar fila editorial e preparação de texto para publicação manual.
7. Reprocessamento agendado, observabilidade e testes de integração.
8. Documentar comandos e procedimento para obter/validar links oficiais por empresa.

## 14. Orientações ao agente de implementação

- Este é um **incremento no projeto existente**: antes de codificar, ler estrutura e adaptar o plano ao que já funciona.
- Não criar outro bot, outro coletor ou um frontend novo.
- Não substituir SQLite/PostgreSQL, scheduler, ORM nem biblioteca HTTP sem necessidade comprovada.
- Não adicionar integrações externas ou bibliotecas pesadas quando a biblioteca padrão/cliente HTTP existente resolver.
- Utilizar `uv` para dependências e execução; manter `uv.lock` versionado.
- Entregar alterações incrementais, testes, migração e README resumido dos novos fluxos.
- Se a estrutura atual impedir algum requisito, reportar bloqueio e propor menor alteração necessária, sem assumir detalhes inexistentes.
