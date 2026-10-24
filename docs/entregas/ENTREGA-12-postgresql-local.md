# PostgreSQL local — validação parcial

## Publicação e concorrência

Executado `tests/test_site_publications.py` com `BUSCADIN_TEST_POSTGRES_URL`
apontando para o PostgreSQL local: **34 passed** (17 cenários em SQLite e os
mesmos 17 em PostgreSQL). Cada cenário PostgreSQL cria um schema com nome
aleatório e o remove ao terminar.

Inclui confirmações simultâneas, callback duplicado, idempotência, prévia
privada, ator não autorizado, invalidação de prévia, retirada, preservação
do snapshot aprovado, exclusão Brasil, suspensão por indicação expirada e
reconciliação com alerta único. São testes do serviço real com o banco real;
não enviam mensagens ao Telegram nem comprovam configuração da VPS.

Em 2026-10-24, um PostgreSQL 18 descartável foi iniciado no Docker local,
com banco `buscadin_validation` e porta vinculada a `127.0.0.1:55432`.

Evidência executada com `postgresql+asyncpg`:

- `uv run alembic upgrade head`: migrations 0001 a 0005 aplicadas com sucesso.
- `uv run alembic check`: `No new upgrade operations detected`.

Isso comprova a criação do schema e sua correspondência com os modelos no
PostgreSQL, além da validação SQLite anterior. Ainda não comprova importação
de dados, concorrência de publicação, backup/restauração ou operação na VPS.
As referências anteriores a PostgreSQL não validado devem ser interpretadas
com este avanço parcial. O deploy permanece pendente.

## Importação e sequências

Teste executado em um segundo banco descartável (`buscadin_test_import`):
dry-run sem persistir vagas, importação SQLite → PostgreSQL, repetição da
importação e criação de uma vaga com ID automático superior ao maior ID
importado (42). Os dois testes de migração passaram.

O importador agora bloqueia as tabelas de destino durante a transação e
ajusta as sequências com `ALTER SEQUENCE ... RESTART` antes do commit.
Isso evita colisões de chave após importar IDs explícitos; o ajuste é
transacional e não ocorre no dry-run. Executar a importação em janela de
manutenção, com bot e portal parados.

Para reproduzir o teste opcional, definir `BUSCADIN_TEST_POSTGRES_URL`
apontando para um banco PostgreSQL descartável novo e executar
`uv run pytest tests/test_migrate_catalogue.py -q`. O teste grava dados
sintéticos nesse banco; nunca apontar essa variável para produção.

O container `buscadin-pg-validation` usa autenticação trust exclusivamente
para dados sintéticos locais. Não reutilizar essa configuração em produção.

## Ensaio de backup e restauração

O banco sintético de importação foi exportado com `pg_dump -Fc` e restaurado
em `buscadin_test_restore` com `pg_restore --exit-on-error --no-owner`.
Ambos terminaram com código zero. Dumps `--data-only` da origem e do destino
foram comparados com `cmp`, removendo apenas as linhas aleatórias de controle
`\\restrict` e `\\unrestrict`: conteúdo e sequências idênticos.

A restauração usou o dump completo, que inclui constraints; os dumps de
dados foram utilizados somente para comparação. O PostgreSQL alertou sobre
FKs circulares entre jobs e referral_links ao gerar esses dumps de comparação.

Limites: três vagas sintéticas, sem publicações ou eventos reais, mesmo
container e disco local, sem criptografia externa. Ainda é necessário testar
recuperação de publicações, alertas e histórico e o armazenamento externo
criptografado. Este ensaio não comprova recuperação da VPS.
