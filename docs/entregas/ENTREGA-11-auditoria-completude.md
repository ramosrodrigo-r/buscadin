# Entrega 11 — Auditoria de completude do MVP

Data: 2026-10-24. Esta auditoria separa evidência local de verificações que ainda exigem ambiente externo. Ela não declara o MVP em produção.

## Requisitos verificados localmente

| Requisito | Evidência | Estado |
| --- | --- | --- |
| Catálogo público com home, busca, filtros e paginação | `src/buscadin_bot/web/server.py`, `web/rendering.py`, `tests/test_web_server.py`, `tests/test_catalogue.py` | Implementado e testado |
| Páginas individuais indexáveis e sitemap | Rotas `/vagas/{slug}-{id}` e `/sitemap.xml`, testes de detalhe e sitemap | Implementado e testado |
| Candidatura externa segura | Política de domínio/HTTPS, revalidação no redirect e suspensão de destino expirado | Implementado e testado |
| Publicação após prévia e confirmação no Telegram | `SitePublicationService`, API privada e handlers de `/publicar_site`/`/atualizar_site` | Implementado e testado |
| Link oficial sem indicação e indicação com expiração | `publication_policy.py`, `site_publications.py`, alertas persistidos e testes de troca/suspensão | Implementado e testado |
| Elegibilidade Brasil conservadora | `classifier.py`, estados `confirmed_br`, `unknown` e `excluded_br`, testes de regressão | Implementado e testado |
| Requisitos desconhecidos separados de não exigidos | `requirements.py`, migration 0005, CLI e `/requisitos_site` | Implementado e testado |
| Persistência, histórico, versionamento e idempotência | Models 0004/0005, eventos, CAS de confirmação, migration/importador | Implementado em SQLite; PostgreSQL ainda não validado |
| Identidade visual preservada | Assets legados, fonte Inter e renderização das telas públicas | Verificado no preview local |
| Operação HTTP e cache | Healthcheck com consulta ao banco, headers de segurança, cache e teste de carga local | Verificado localmente |

Suíte local atual: `140 passed`. Migrations locais: `alembic check` sem operações pendentes. Teste de carga local: 100 requisições em `/healthz` e 100 em `/vagas`, sem falhas.

## Verificações externas ainda necessárias

| Requisito | Evidência faltante | Próxima ação segura |
| --- | --- | --- |
| Banco PostgreSQL novo compartilhado | A VPS tem bancos legados, mas nenhum banco do catálogo foi criado/validado | Rotacionar credenciais; criar banco isolado no Dokploy; aplicar migrations e importar após dry-run |
| Backup e restauração reais | Só há testes SQLite e procedimento documentado | Gerar dump criptografado fora da VPS, restaurar em banco isolado e executar `uv run alembic check` |
| Deploy do portal | `buscadin.app` ainda serve a aplicação legada | Subir `buscadin-portal` em staging, validar healthcheck e fazer cutover planejado com rollback |
| Fluxo Telegram ponta a ponta | Testes usam adaptadores/mocks | Configurar token novo e API privada em staging; publicar uma vaga fictícia e despublicá-la |
| Segurança das credenciais existentes | A saída acidental de `docker service inspect` expôs segredos | Rotacionar DB, Redis, Google, Stripe, Listmonk e tokens relacionados antes de novo diagnóstico/deploy |
| Capacidade em staging | Só há inventário pontual da VPS e carga local | Executar `scripts/load_test_portal.py` contra staging, nunca produção sem janela aprovada |

## Decisão operacional

Não remover os serviços antigos nem trocar `buscadin.app` enquanto as verificações externas acima não forem concluídas. Listmonk permanece independente. O estado local está versionado no commit `226d186`, com a evidência do domínio legado registrada em `c332d88`.
