# Instagram Unified login no Postiz próprio

A imagem `buscadin-postiz-unified:1e376ff2-v2` deriva do digest fixo da imagem
oficial. Ela altera somente o provedor `instagram-standalone` do backend e do
orquestrador, com verificação SHA-256 do arquivo de origem durante o build.
O patch fica inerte enquanto `INSTAGRAM_UNIFIED_CONFIG_ID` estiver vazio.
O código e os testes estão em `deploy/postiz-unified/`.

## Fluxo

O login passa `config_id`, `response_type=code` e o callback
`/integrations/social/instagram-standalone` à Meta. O backend troca o código
pela credencial de sistema, lista as contas de Instagram atribuídas à credencial
em `/me/assigned_instagram_accounts` e exige exatamente uma conta, a menos
que `INSTAGRAM_UNIFIED_ACCOUNT_ID` selecione uma das contas retornadas. A
publicação do canal usa `graph.facebook.com`; o refresh legado do Instagram
fica desativado para esse provedor. O estado OAuth continua sob o controle do
Postiz.

## Configuração pendente na Meta

Na tela **Instagram → API setup with Unified login**, crie uma configuração
de Login do Facebook para Empresas com acesso à conta do Instagram,
`instagram_basic` e `instagram_content_publish`. Registre como callback:

```text
https://rodrigodesktop.tail88c0f5.ts.net/integrations/social/instagram-standalone
```

Salve o ID do aplicativo, o App Secret e o ID da configuração no `.env` privado
do Postiz no homelab, sem colocá-los no Git nem na conversa:

```ini
INSTAGRAM_UNIFIED_APP_ID=<Meta App ID>
INSTAGRAM_UNIFIED_APP_SECRET=<Meta App Secret>
INSTAGRAM_UNIFIED_CONFIG_ID=<Facebook Login for Business configuration ID>
```

Depois de reiniciar apenas o contêiner `postiz`, conecte **Instagram
(Standalone)** no Postiz. Se a credencial listar mais de uma conta, adicione
`INSTAGRAM_UNIFIED_ACCOUNT_ID=<ID da conta>` ao `.env` e reinicie. O worker do
Buscadin só retira carrosséis da fila quando `POSTIZ_INTEGRATION_ID` apontar
para esse canal ativo.

## Estado e limites

Os testes locais cobrem a URL OAuth, a troca simulada do código, a seleção da
conta e o domínio Graph usado para publicação. Ainda não houve autenticação
real na Meta. A plataforma pode não expor contas ao token gerado para um app e
uma conta no mesmo portfólio; isso precisa ser verificado com a autorização
real antes de dizer que a integração funciona. A URL de mídia do Postiz ainda
é privada na Tailscale: criar o rascunho independe disso, mas publicar no
Instagram exigirá imagens acessíveis pela Meta em HTTPS público.

Para voltar à imagem original, restaure o `buscadin.override.yaml` anterior
no homelab e execute `docker compose -f docker-compose.yaml -f
buscadin.override.yaml --env-file .env up -d --no-deps postiz`. Os dados
permanecem nos volumes do Postiz.
