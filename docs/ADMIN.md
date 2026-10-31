# Painel administrativo privado

O comando `uv run buscadin-admin` inicia uma interface para operador único em
`http://127.0.0.1:8081`. O painel e o catálogo devem usar o mesmo `DATABASE_URL`.
O processo público `buscadin-portal` não recebe rotas administrativas.

## Operação local

```sh
mkdir -p data
export DATABASE_URL=sqlite+aiosqlite:///./data/buscadin-admin.db
uv run alembic upgrade head
uv run buscadin-admin
```

No primeiro início, se `ADMIN_PASSWORD` não estiver configurada, o processo cria
`data/admin-password`, aleatória, com permissões 0600 e ignorada pelo Git. Para
copiar no macOS sem imprimir a senha:

```sh
pbcopy < data/admin-password
```

Cole no formulário. Também é possível fornecer `ADMIN_PASSWORD` por um mecanismo
de secrets; mínimo de 20 caracteres. Ao trocar a senha, reinicie o processo para
invalidar as sessões anteriores. A senha não é enviada em URLs nem registrada
em logs. O arquivo local contém a credencial em texto e deve permanecer privado.

O portal público usa o mesmo banco. Inicie em outro terminal, com `DATABASE_URL`,
`SITE_API_TOKEN`, `TELEGRAM_ADMIN_USER_ID`, `SITE_BASE_URL` e
`SITE_OFFICIAL_DOMAINS` configurados conforme `DEPLOYMENT-MVP.md`.

## Controles disponíveis

- Busca e paginação da fila, com filtros de etapa e publicação.
- Cadastro manual e edição de título, empresa, fonte, candidatura, categoria,
  requisitos com evidência, elegibilidade, idiomas, remuneração e disponibilidade.
- Prévia do snapshot público e do destino; confirmação, atualização e retirada
  versionadas pelos mesmos serviços usados na integração Telegram.
- Coleta manual da Himalayas, com resultado e histórico. Não envia notificações
  Telegram por si só; a outbox é consumida pelo bot quando executado.
- Coleta manual de micro1, Turing, Mercor e Alignerr, individual ou conjunta,
  com progresso em segundo plano e entrada somente de vagas inéditas.
- Cadastro de programas oficiais e links de indicação, validação de domínio,
  escopo e validade, desativação e reconciliação das publicações afetadas.
- Histórico das últimas 100 ações gerais e 100 ações de publicação.

Salvar é diferente de republicar. Edições manuais marcam a vaga como
`admin_curated`: coletas posteriores atualizam a data de observação, mas não
sobrescrevem os campos. Atualizações e encerramento na fonte passam a exigir
revisão manual dessas vagas. A publicação continua sujeita à política existente.

Edições verificam a revisão lida pelo navegador e rejeitam conteúdo obsoleto.
PostgreSQL também bloqueia a linha durante a edição. Para produção com vários
processos escrevendo, use PostgreSQL; SQLite é a configuração local.

## Acesso remoto

Em produção, o hostname planejado é `https://gerentin.buscadin.app`. O nome
menos óbvio não é uma barreira de segurança. Antes de publicar o DNS/roteamento,
ative Cloudflare Access e crie uma aplicação Self-hosted que permita somente o
e-mail do operador. A senha do próprio painel permanece como segunda barreira.
O acesso deve passar pelo proxy Cloudflare; não publique a porta do serviço no
host nem crie um registro DNS sem proxy.

O serviço administrativo usa a mesma imagem, banco PostgreSQL e rede overlay do
portal, mas roda em um processo/serviço separado. O backend não ganha uma porta
pública. `ADMIN_ORIGIN` deve coincidir exatamente com o endereço HTTPS aberto no
navegador; `ADMIN_BIND_HOST=0.0.0.0` só é adequado dentro da rede privada do
container e `ADMIN_PORT` define a porta interna. O cookie de sessão recebe
`Secure` automaticamente para origens HTTPS.

O entrypoint de produção `scripts/entrypoint-admin.sh` lê `database_url` e
`admin_password` de secrets Docker montados em `/run/secrets/`. Não use valores
literais em argumentos de deploy, labels, URLs ou logs. Não configure uma rota
Traefik nem DNS para esse hostname antes de a aplicação Access e sua política
Allow por e-mail estarem ativas.

Para operação local, mantenha `ADMIN_ORIGIN=http://127.0.0.1:8081` e o bind
loopback padrão. Sessões ficam na memória, duram oito horas e são invalidadas no
reinício/logout. Cada escrita exige origem exata, JSON, sessão e token CSRF.
Cinco falhas de login bloqueiam tentativas por cinco minutos. A senha é
comparada usando scrypt.

## Limites explícitos

O painel administra o catálogo, não a infraestrutura da VPS. Domínios oficiais,
segredos, frequência do bot, backups e deployment continuam na configuração de
operação. O painel não tem agendador independente. Há um conector Himalayas com
limite de 20 registros e sem paginação desse provedor.
Os quatro crawlers empresariais são acionados exclusivamente no painel e não
entram na agenda do bot. Veja `CRAWLERS.md` para instalação, limites e diagnóstico.
Programas e links podem ser cadastrados/desativados; para corrigir um registro,
desative-o e cadastre o substituto. Listagem limitada aos 200 mais recentes.

## Verificação

`uv run pytest` inclui autenticação, origem, CSRF, expiração, logout, rate limit,
edição obsoleta, publicação completa, indicação, coleta simulada e preservação
da curadoria. Testes não consultam APIs externas.

`node scripts/verify-admin.mjs /caminho/playwright/index.mjs` usa banco temporário
isolado e portas 8082/8083 para login, cadastro, prévia, publicação, consulta
pública, retirada e logout reais no navegador. Confere cinco telas em
1440, 390 e 320 pixels. Screenshots ficam em `.preview/admin/`.
