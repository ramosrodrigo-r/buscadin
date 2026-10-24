# Deploy do catálogo no Dokploy

## Serviços

Use a mesma imagem do repositório em dois serviços novos ou em um serviço novo e no bot existente:

| Serviço | Comando | Função |
| --- | --- | --- |
| buscadin-portal | buscadin-portal | HTML público, redirect e API privada |
| buscadin-bot | python -m buscadin_bot.main | coleta, outbox e Telegram |

Os dois processos precisam usar o mesmo DATABASE_URL do banco novo do catálogo. Não apontar para o banco legado de campanhas sem uma migração deliberada.

## Migration e variáveis

Antes de iniciar o portal, executar no serviço ou em um job de release:

    uv run alembic upgrade head

Para levar o banco local do bot ao banco novo, faça um backup dos dois arquivos e execute o importador com o destino já migrado:

    export DESTINATION_DATABASE_URL='postgresql+asyncpg://USUARIO:SENHA@HOST:5432/NOME'
    uv run python scripts/migrate_catalogue.py --source-url 'sqlite+aiosqlite:///./data/buscadin.db' --destination-url "$DESTINATION_DATABASE_URL" --dry-run

Revise as contagens do dry-run e repita sem `--dry-run`. O importador preserva IDs e é idempotente, mas não copia snapshots de publicação web nem tokens de confirmação; toda publicação precisa continuar passando pela prévia do Telegram.

Variáveis mínimas nos dois serviços:

    DATABASE_URL=postgresql+asyncpg://USUARIO:SENHA@HOST:5432/NOME
    TELEGRAM_ADMIN_CHAT_ID=...
    TELEGRAM_ADMIN_USER_ID=...
    SITE_API_TOKEN=...
    SITE_OFFICIAL_DOMAINS=dominio-oficial.example

No bot:

    SITE_API_URL=https://buscadin.app

No portal:

    SITE_BASE_URL=https://buscadin.app
    SITE_CONTACT_EMAIL=contato@buscadin.app
    PORTAL_HOST=0.0.0.0
    PORTAL_PORT=8080

O SITE_API_TOKEN deve ser um segredo novo e igual nos dois serviços. Não colocá-lo em URLs, logs ou variáveis expostas no frontend.

## Traefik

Encaminhe buscadin.app para a porta 8080 do buscadin-portal. O serviço deve responder /healthz. A rota /internal/* exige Bearer token e ator Telegram; a opção preferível é deixá-la acessível somente pela rede interna do projeto. Se o Dokploy não permitir rota interna entre serviços, use HTTPS no domínio com o token e aplique uma regra de rede adicional antes do lançamento.

## Rollback

Não remover os serviços antigos no primeiro deploy. Fazer backup do banco novo e testar:

1. migration em banco vazio;
2. publicação, retirada e restauração em ambiente isolado;
3. healthcheck e rota pública;
4. fluxo Telegram com uma vaga fictícia;
5. só então trocar o domínio.

O Listmonk e seu banco permanecem fora da migração do catálogo.

## Backup e restauração PostgreSQL

Use uma máquina ou volume de backup fora da VPS. Configure a autenticação por `.pgpass` ou `PGSERVICE`; não coloque senha na linha de comando:

    pg_dump --format=custom --no-owner --file=/backup/buscadin-$(date +%Y%m%d-%H%M%S).dump "$PGDATABASE"
    sha256sum /backup/buscadin-*.dump > /backup/buscadin-$(date +%Y%m%d-%H%M%S).sha256

Antes do lançamento, restaure uma cópia em um banco isolado, valide a migration e conte as relações principais:

    createdb buscadin_restore_check
    pg_restore --clean --if-exists --no-owner --dbname=buscadin_restore_check /backup/ARQUIVO.dump
    DATABASE_URL=postgresql+asyncpg://.../buscadin_restore_check uv run alembic check

O dump deve ser criptografado no destino externo e ter a restauração verificada. O banco do Listmonk deve possuir backup e restauração independentes; não misture os arquivos nem os ciclos de retenção.

### Persistência do Listmonk confirmada por SSH em 2026-10-24

Consulta limitada a nomes, imagens, status e mounts (sem variáveis de ambiente):

- `listmonk_db`: PostgreSQL 17, volume `listmonk-app-al9hes_listmonk-data`,
  montado em `/var/lib/postgresql/data`.
- `listmonk_app`: uploads em
  `/etc/dokploy/compose/listmonk-app-al9hes/code/uploads`, montados em
  `/listmonk/uploads`.

Preservar e restaurar tanto o dump lógico do banco quanto os uploads.
Não copiar diretamente os arquivos do volume de um PostgreSQL em execução
como substituto de `pg_dump`. Os mounts não comprovam a configuração de
conexão da aplicação nem que já existe backup externo. O destino externo
ainda precisa ser definido pelo operador.

## Carga fora de produção

Depois de subir um ambiente de staging, execute a verificação limitada e registre o resultado:

    uv run python scripts/load_test_portal.py https://staging.example/healthz --requests 200 --concurrency 10

Não executar esse script contra o domínio de produção sem definir antes uma janela e um limite aprovados.
