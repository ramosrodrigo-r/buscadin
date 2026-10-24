# Buscadin — MVP do catálogo público

Estado: domínio, portal e auditoria inicial da VPS concluídos localmente; deploy, backup externo e validação PostgreSQL ainda pendentes.
Data: 2026-10-24.

## Fonte de requisitos

PRD: `/Users/RodrigoRR/Downloads/PRD_Buscadin_Plataforma_Integracao_Telegram.md`.
As decisões abaixo, confirmadas na conversa, prevalecem sobre o PRD.

- Catálogo de vagas gerais remotas para residentes no Brasil. Prioridade editorial inicial para video annotation e trabalhos semelhantes acessíveis sem graduação ou experiência especializada; nunca inferir ausência de requisitos.
- Preservar identidade visual existente: Inter local, superfícies claras, tinta escura e laranja. Redesign adiado.
- Publicação exclusivamente após prévia e confirmação explícita no Telegram.
- Permitir link oficial quando indicação estiver ausente, mediante confirmação.
- Indicação vencida suspende candidatura e gera alerta. Troca para oficial exige confirmação.
- Elegibilidade desconhecida pode ser publicada com aprovação e aviso explícito. Elegibilidade excluída para Brasil impede publicação.
- Sem avaliações, relatos, contas de candidatos, planos, cobrança, newsletter ou postagem automática nas redes.

## Evidências da auditoria local

### Bot (`buscadin-bot`)

- Python, uv, SQLAlchemy assíncrono, Alembic, SQLite padrão; 27 testes passaram na inspeção inicial.
- Coletor, normalizador, resolver e handlers separados; preservá-los incrementalmente.
- Himalayas é o único conector e busca um lote de 20 registros. Não existe confirmação de encerramento; ausência no lote não prova encerramento.
- O banco mantém identidade por `(source, source_job_id)`, estados editoriais e programas/links separados. Não há entidade de empresa nem publicação web.
- `/publicar` registra uma publicação editorial manual; preservar e adicionar `/publicar_site`.
- `JobRepository.upsert_job` sobrescreve conteúdo operacional. O site deve ler snapshots aprovados para impedir mudanças públicas silenciosas após coleta.
- `ReferralResolver` permite HTTP e lista de domínios vazia. A publicação web precisa exigir HTTPS e domínio explicitamente validado, sem confiar apenas em `LINK_VALIDADO`.
- Correção inicial aplicada: menção isolada a Brasil não confirma elegibilidade; exclusão explícita tem precedência sobre aceitação estruturada conflitante. Descrições sem localização estruturada ficam para revisão. Seis regressões novas; suíte atual com 33 testes passando. Classificação continua heurística, não prova completa de elegibilidade.
- `main.run_service` processa envio da outbox só no ciclo de coleta e chama `poll_once` sem o tratamento de falhas de `run_forever`. Separar cadências e preservar continuidade após falhas transitórias.
- O poller atual envia respostas antes do commit do lote. Confirmação de publicação web deve ocorrer somente após commit próprio e ser reconciliável.

### Site legado (`/Users/RodrigoRR/prospecTeam`)

- Express, HTML/CSS/JS sem build, PostgreSQL, BullMQ/Redis e cobrança Stripe.
- `public/styles.css`, `public/fonts/InterVariable.woff2` e `public/favicon.svg` são referências reutilizáveis de identidade.
- Campanhas de prospecção, Google Places, créditos e billing não fazem parte do novo domínio.
- `PRODUCT.md` e `docs/DEPLOYMENT.md` ainda descrevem funcionalidades WhatsApp ausentes das rotas atuais. Não utilizar documentação antiga como inventário de produção.
- Dockerfile menciona Dokploy. Não há identificação suficiente do servidor nos documentos examinados.
- Nenhum serviço legado foi iniciado e nenhum dado de produção foi alterado.

## Decisões de arquitetura após a auditoria da VPS

Comparar custo operacional e migração de duas opções: servir páginas renderizadas pelo backend Python ou reutilizar Express para o portal com API Python privada. Não introduzir Next.js apenas por exemplo do PRD.

Preferência de domínio: backend Python como autoridade para vagas, referrals e publicações, reaproveitando regras existentes. O processo Telegram acessa comandos privados; não escreve tabelas do portal por fora. Definir também ingestão, consulta e cadastro de links nesse contrato, além de publicar/despublicar.

PostgreSQL é candidato a banco compartilhado lógico do core, sujeito à capacidade medida. Não reutilizar tabelas de campanhas nem presumir migração de clientes/pagamentos. SQLite continua útil para testes e importação; não implantar múltiplos escritores concorrentes nele como arquitetura de produção.

### Decisão após o inventário

Usar o projeto `Aplicativo / production` existente no Dokploy, mantendo o Listmonk separado, e adicionar um serviço Python de portal ao lado do bot. O portal e o bot compartilharão um PostgreSQL próprio do novo catálogo por `DATABASE_URL`; tabelas da aplicação antiga não serão reutilizadas. O portal ficará atrás do Traefik e o bot usará a API privada autenticada por Bearer token. Os serviços antigos podem ser parados e removidos somente depois de backup e confirmação de que o Listmonk continua apontando para seu banco próprio.

## Sequência de entrega e provas de conclusão

1. **Auditoria e contrato:** inventário real da VPS, processos, proxy, volumes, banco, recursos e domínio; cópia de segurança; decisão de arquitetura e rollback. Registrar contratos de ingestão, prévia, publicação, atualização, retirada e links em OpenAPI.
2. **Domínio:** empresas, identidade conservadora entre fontes, requisitos com estado informado/não exigido/desconhecido e evidência, snapshots públicos, eventos imutáveis, versão e idempotência. Migrations e importação preservam IDs legados; reconciliação por contagem e relações.
3. **Integração Telegram:** autenticar chat e usuário; prévia vinculada a versão/conteúdo/destino; confirmação com commit antes do sucesso; conflito exige nova prévia. Preservar todos os comandos existentes. Testar callbacks repetidos, concorrentes e falha de resposta após commit.
4. **Portal:** home, busca, filtros, paginação, detalhe, candidatura externa e institucionais. HTML indexável, canonical, OG, sitemap e JobPosting somente quando campos e validade sustentarem. Renderizar somente snapshots aprovados; API pública não expõe evidência privada nem dados financeiros.
5. **Validade:** validar destino no clique mesmo com página cacheada; expiração suspende CTA, notifica e não troca URL. Encerramento confirmado retira catálogo/sitemap, invalida cache e desativa candidatura; falha de fonte não implica encerramento. Testes com relógio controlado.
6. **Operação:** deploy isolado, limites e healthchecks, logs sem segredos, backup externo criptografado, restauração em ambiente isolado, teste de carga fora de produção, medições e rollback ensaiado. Só então substituição do portal existente.

## Matriz mínima de aceite

| Invariante | Prova exigida |
| --- | --- |
| Coleta não publica | Teste integrado: ingestão e consulta pública vazia |
| Prévia não publica | Teste sem confirmação final |
| Confirmação publica uma vez | Testes de repetição e concorrência com consulta pública |
| Conteúdo aprovado não muda silenciosamente | Recoleta e troca de link deixam snapshot intacto; atualização exige nova aprovação |
| Versão defasada não publica | Alteração após prévia gera conflito |
| Destino é seguro | HTTPS/domínio, escopo, validade e permissão; sem URL arbitrária no redirect |
| Link vencido não redireciona | Expiração entre página e clique bloqueia CTA e gera alerta |
| Vaga excluída do Brasil não entra | Teste de publicação e consultas públicas |
| Elegibilidade desconhecida é explícita | Prévia, snapshot e página mantêm aviso |
| Ausência de requisito não vira dispensa | Dados e filtros distinguem os três estados |
| Retirada é efetiva | Catálogo, detalhe, redirect, sitemap e cache conferidos |
| Bot legado continua funcionando | Suíte existente e cenários novos passam |
| Interface preserva identidade e funciona no celular | Inspeção de telas reais, teclado, contraste e breakpoints |
| Migração é reversível | Backup restaurado e reconciliação documentada |
| VPS comporta operação | Inventário e teste de carga com resultados reais |

## Pendências externas

- Rotação das credenciais expostas na auditoria; não enviar segredos na conversa.
- Configuração final de domínio/rotas no Dokploy e criação do banco novo do catálogo.
- Permissões de reprodução e divulgação dos programas/fontes concretamente utilizados: conferir antes de publicar conteúdo real.
- Destino de backup fora da VPS e identificação/contato público do operador para páginas institucionais.

## Progresso de implementação

- `services/publication_policy.py`: política pura de elegibilidade/status e destinos HTTPS com domínio exato autorizado. Preserva a URL de indicação original. Fingerprint canônico detecta mudanças entre prévia e confirmação; não é credencial e ainda precisa ser conectado à transação e à prévia persistida.
- `tests/test_publication_policy.py`: URLs inseguras, domínios confundíveis, preservação de parâmetros, estados elegíveis e alterações de conteúdo/destino/versão. Suíte completa: 58 testes passando em 2026-10-23.
- `scripts/audit-vps.sh`: inventário de leitura executado na VPS. Não leu ambientes nem segredos.
- Alias `buscadin-vps` configurado e conexão SSH confirmada em Ubuntu 24.04.4 LTS.
- Núcleo transacional local implementado em `services/site_publications.py`, com prévia persistida, snapshots, eventos, versão, idempotência, retirada e suspensão do CTA. Migration aditiva 0004 testada apenas em banco temporário.
- Estado atual da suíte: 140 testes passando, incluindo concorrência de confirmações e migration/backup/restauração SQLite. Relatório e limites em `docs/entregas/ENTREGA-06-core-publicacao-parcial.md`.
- Cliente e handlers Telegram agora conectados opcionalmente ao runtime via API privada configurável. Testes locais ligam handlers ao serviço real por adaptador, com bancos separados.
- Contrato de publicação privado em `docs/api/publication.openapi.json`; servidor HTTP implementado em `web/server.py` e serviço separado em `web/portal.py`. Estado atual da suíte: 140 testes passando. Relatórios em `docs/entregas/ENTREGA-07-telegram-site-parcial.md` e `ENTREGA-10-servidor-http-parcial.md`.
- Auditoria inicial da VPS e decisão de deploy concluídas; prova no PostgreSQL real, backup externo e implantação permanecem pendentes.
- Domínio de consulta pública e requisitos explícitos implementado: busca/filtros/paginação sobre snapshots aprovados, detalhe seguro e lotes de sitemap. Migration local 0005 e prévia de requisitos no Telegram. Suíte atual: 140 testes passando. Ver `docs/entregas/ENTREGA-08-catalogo-dominio-parcial.md` para limites e pendências.
- Renderização das telas públicas implementada: home, catálogo, detalhe, Sobre, Contato, Privacidade, Termos e estados vazios. Marca/fonte/imagem social preservadas do legado. Suíte atual: 140 testes. Inspeção de 12 combinações de tela/largura com Chromium, sem overflow, contraste mínimo amostrado 5,78:1. Relatórios `ENTREGA-09` e `ENTREGA-10`.
- JobPosting continua pendente de campos verificáveis e revisão de completude da descrição; não ativar automaticamente em resumos. Ingestão central formal, teste PostgreSQL, operação externa, backup e implantação continuam pendentes.

Este documento não declara o MVP entregue. A continuação depende do deploy controlado, backup/restauração fora da VPS, validação PostgreSQL e revisão das credenciais expostas durante a auditoria.

### Ponto de retomada

- Rotacionar as credenciais que apareceram na saída acidental de `docker service inspect`.
- Criar o PostgreSQL novo do catálogo no Dokploy, aplicar migrations e validar restauração em ambiente isolado.
- Criar o serviço `buscadin-portal`, configurar Traefik, domínio e API privada; ligar o bot ao mesmo banco e token.
- Preservar o trabalho local ainda não commitado. Última validação registrada: 140 testes Python passando e 12 combinações de tela/largura no Chromium; não equivale à validação de produção.
- Nenhuma implantação ou modificação de produção foi realizada.

### Auditoria da VPS — primeiro inventário (2026-10-24)

- SSH confirmado na VPS `179.197.74.22`, Ubuntu 24.04.4 LTS, usuário administrativo `root`.
- Capacidade observada: 2 vCPUs, 7.9 GiB de RAM, sem swap, 95.8 GiB de disco; 9.2 GiB usados (9.5%) e carga 0.09/0.08/0.03.
- Portas públicas observadas: 22, 80, 443 e 3000. PostgreSQL exposto somente em `127.0.0.1:5432`.
- Dokploy `v0.29.12` e Traefik `v3.6.7` estão ativos; Docker `29.6.1` está em uso.
- Serviços existentes: `aplicativo-buscadin` e worker, Redis e PostgreSQL associados ao aplicativo, além de `listmonk` e seu banco. Há também o PostgreSQL interno do Dokploy.
- O inventário foi somente leitura e não acessou variáveis de ambiente, segredos ou dados de banco.
- A capacidade parece suficiente para um serviço web Python separado no MVP, mas ainda faltam rotas/domínios, limites persistentes, estratégia de banco compartilhado e backup/restauração.
- O comando complementar de topologia foi quebrado pelo terminal antes de `--format`; o `docker service inspect` acabou emitindo a configuração completa dos serviços, incluindo credenciais. Essas credenciais devem ser consideradas expostas e rotacionadas antes de novo diagnóstico/deploy. Não repetir `inspect` sem filtro.
- Transporte HTTP implementado em `web/server.py`, com páginas públicas, assets, sitemap, healthcheck, redirect revalidado e API privada autenticada; `web/portal.py` inicia o serviço separado no Dokploy. A suíte local passou com 140 testes.
- Smoke/load local executado contra o portal SQLite temporário: 100 requisições concorrentes ao `/healthz` e 100 ao `/vagas`, sem falhas; p50 de 4,8 ms e 8,6 ms, respectivamente. Esse resultado não substitui teste em staging ou na VPS.
- O poller do bot agenda reconciliação das publicações e entrega `SiteAlert` persistidos ao administrador; o driver `asyncpg` foi incluído no lock para PostgreSQL.
- CLI `requirements set/show` permite registrar graduação e experiência como exigida, não exigida ou desconhecida com evidência e evento de auditoria; alterações não reescrevem snapshots públicos.
