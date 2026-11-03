# Postiz no homelab

Instalação independente do Buscadin, do Jellyfin e do servidor Dragonwilds. O
Compose oficial de `gitroomhq/postiz-docker-compose` está fixado no commit
`dd4969e5e694cd009619a0d53cff14c21104580b`. O arquivo
`deploy/postiz.override.yaml` troca senhas de exemplo por valores aleatórios,
mantém a interface em `127.0.0.1:4007` e deixa as dependências sem portas
públicas. O Postiz, Postgres, Redis, Temporal e Elasticsearch têm volumes próprios.

No homelab, o diretório da instalação é
`~/.local/share/buscadin-postiz/upstream/`; o `.env` ali tem modo `0600` e não
deve ir para o Git. Não execute o Compose oficial sem o override, pois ele
publica a interface em todas as interfaces e usa senhas de exemplo.

```sh
ssh homelab 'cd ~/.local/share/buscadin-postiz/upstream && docker compose -p buscadin-postiz -f docker-compose.yaml -f buscadin.override.yaml ps'
```

O endereço configurado para a interface é
`https://rodrigodesktop.tail88c0f5.ts.net/`. Ele depende de **Tailscale Serve**
estar habilitado na tailnet. A interface só aceita conexão local no homelab;
Serve faz o acesso HTTPS privado da tailnet. O dono criou a conta inicial e
`DISABLE_REGISTRATION` está em `"true"` no override. Mantenha a conta com senha
única e autenticação da tailnet ativa.

## Operação

```sh
ssh homelab 'cd ~/.local/share/buscadin-postiz/upstream && docker compose -p buscadin-postiz -f docker-compose.yaml -f buscadin.override.yaml logs --tail 80 postiz'
ssh homelab 'cd ~/.local/share/buscadin-postiz/upstream && docker compose -p buscadin-postiz -f docker-compose.yaml -f buscadin.override.yaml up -d --no-deps postiz'
```

Para atualizar, leia as notas de migração do Postiz e do Temporal, faça backup
dos volumes antes, atualize o commit do Compose e a imagem juntos e valide
novamente o override. Os volumes a incluir no backup são `postgres-volume`,
`postiz-uploads`, `postiz-config`, `postiz-redis-data`,
`temporal-postgres-data` e `temporal-elasticsearch-data`, todos no projeto
Compose `buscadin-postiz`.

A imagem do Postiz é fixada por digest no override; atualizar exige trocar esse
digest conscientemente depois de testar a nova versão.

## Integração de publicação

O Postiz instalado é o agendador. A geração de carrossel do Buscadin continua
no admin com aprovação humana; nenhuma publicação é disparada automaticamente.
O próximo passo técnico é enviar os PNGs aprovados à API `/public/v1/upload`,
montar o post com a integração de Instagram escolhida, guardar o ID retornado
e reconciliar o estado de publicação. Isso requer conta e chave de API no Postiz.

Para Instagram, o Postiz exige um app Meta, credenciais e permissões de
publicação. O fluxo OAuth exige URL HTTPS alcançável no navegador, e as imagens
do carrossel precisam de URL HTTPS pública que a Meta possa buscar. O endereço
privado do Tailscale não atende ao segundo requisito. Planeje uma rota pública
separada para mídia, idealmente R2, sem expor o painel Postiz inteiro. Conectar
uma conta ou agendar uma postagem real depende dessas credenciais e da revisão
final do conteúdo pelo operador.

Em 2026-11-03, a API da conta Cloudflare respondeu que o R2 ainda precisa ser
habilitado no Dashboard. Uma rota pública de mídia pelo proxy existente na VPS
é outra opção, com acesso somente aos arquivos de mídia.
