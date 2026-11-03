# Ponte de carrosséis para o Postiz

O botão **Aprovar e enviar ao Postiz** na área de Carrosséis salva a revisão,
renderiza as lâminas como PNG 1080 × 1350 no navegador e envia as imagens ao
admin com autenticação e CSRF. Uma transação registra a aprovação e a fila.
As imagens ficam numa coluna privada do PostgreSQL e nunca aparecem na listagem
do painel. O limite é 2 MiB por lâmina e 8 MiB por aprovação.

O worker já existente no homelab consulta a fila por HTTPS com Cloudflare
Service Auth e token interno. Quando houver canal e chave configurados, ele
confere a integração, transfere cada PNG ao Postiz local e cria um post com
`type: draft`. **A ponte não agenda nem publica.** O ID retornado fica no
painel; a decisão de publicar continua no Postiz. Após confirmação, os PNGs
temporários são removidos do banco do Buscadin; o Postiz mantém sua cópia.

## Ativação

Primeiro conecte um canal Instagram ao Postiz e gere uma API key em
**Settings → Developers**. Apps novos da Meta usam Unified login, que a versão
original do Postiz ainda não aceita; a imagem derivada e seu processo de
ativação estão em [POSTIZ-UNIFIED-OAUTH.md](POSTIZ-UNIFIED-OAUTH.md).
O Postiz exige um canal até para um rascunho. A
chave deve existir somente em
`~/.config/buscadin-carousel/worker.env` no homelab (modo 0600):

```ini
POSTIZ_API_KEY=<chave criada no Postiz>
POSTIZ_INTEGRATION_ID=<id do canal retornado por GET /api/public/v1/integrations>
POSTIZ_PLATFORM=instagram-standalone
```

Use `POSTIZ_PLATFORM=instagram` para um canal Instagram conectado via Facebook.
O worker valida se o ID corresponde ao tipo configurado e está ativo antes de
retirar qualquer carrossel da fila. Ele acessa o Postiz em `127.0.0.1:4007`;
a chave não vai ao navegador, à VPS nem ao contêiner de inferência do Hermes.
Depois de preencher o arquivo, reinicie `buscadin-carousel-worker.service`.

Na configuração atual, a chave existe e funciona, mas ainda não há canal.
Aprovações ficam na fila `queued` até a ativação, sem tentativas de envio. O Postiz usa
armazenamento local, cujas URLs de mídia são privadas na Tailscale. O rascunho
pode ser criado e revisto, mas a publicação no Instagram só funcionará quando
as imagens tiverem URL pública HTTPS para a Meta buscar. O R2 da conta
Cloudflare ainda não está habilitado; uma rota pública apenas para mídia no
proxy da VPS é alternativa.

## Falhas e duplicação

Falhas antes da criação do post ficam em `failed` e podem ser reenviadas pelo
painel. Se uma chamada de criação falhar de forma incerta, a ponte registra
`uncertain` e **não tenta criar outro post automaticamente**. Confira os
rascunhos no Postiz antes de qualquer intervenção. Se o Postiz criar o rascunho
mas o painel não receber a confirmação, o estado permanece `creating` pelo
mesmo motivo. O painel permite vincular o ID encontrado; se você confirmar que
nenhum rascunho foi criado, ele libera uma tentativa manual. Marcar como
`posted` continua sendo uma ação humana depois da publicação efetiva no Postiz.
A fila de geração via Hermes não é alterada por essa entrega.
