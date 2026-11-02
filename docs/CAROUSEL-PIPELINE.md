# Pipeline de carrossel editorial

## Fluxo

1. No painel, selecione de uma a oito vagas ativas e peça a geração do texto.
2. O painel congela os fatos curados e cria um pedido persistente na fila.
3. O worker do homelab busca o pedido por HTTPS de saída, chama o Hermes com o provedor `openai-codex` e devolve JSON validado.
4. O painel mostra capa, uma lâmina factual por vaga e encerramento. O operador revisa/edita o texto, baixa cada PNG 1080 × 1350 e publica manualmente.
5. Depois de publicar, marque o carrossel como postado (com URL opcional). As vagas ficam fora de novas seleções. Um pedido descartado libera as vagas novamente.

O modelo só recebe título, empresa, categoria, remuneração divulgada, idioma,
tipo de contrato, modalidade e estado de elegibilidade, sem a descrição original
da vaga. O comando `hermes chat` força o provedor `openai-codex`, usa um arquivo
temporário protegido para a solicitação (sem colocá-la na lista de processos),
desabilita toolsets e limita a uma rodada. A solicitação e a resposta passam por validação de esquema;
os títulos das lâminas de vaga são substituídos pelo título curado no banco.
O Hermes usa `openai-codex/gpt-5.3-codex` por chamada; o modelo padrão Claude do
perfil existente não é alterado. Nenhum endpoint/API do Hermes fica exposto.

O worker usa duas barreiras no endpoint de máquina: um token do Cloudflare Access
Service Auth (na borda HTTPS) e `CAROUSEL_WORKER_TOKEN` (no serviço admin). Os
segredos não chegam ao navegador. O worker só pode reivindicar pedidos de
carrossel e devolver resultado/falha.

## Configuração de produção

### Serviço admin no Docker Swarm/Dokploy

- Criar um token aleatório com pelo menos 40 caracteres.
- Armazená-lo como Docker Secret `carousel_worker_token` e montá-lo no serviço
  admin em `/run/secrets/carousel_worker_token`, somente leitura.
- Definir `CAROUSEL_WORKER_TOKEN_FILE=/run/secrets/carousel_worker_token` no
  serviço admin. Não definir o valor secreto como variável literal nem em uma
  label, URL ou comando de deploy.
- Executar `uv run alembic upgrade head` (ou o job equivalente) antes de iniciar
  a nova imagem; a migração `0006_carousel_drafts` cria a fila persistente.
- Manter o app admin atrás do Cloudflare Access. A política de e-mail continua
  permitindo o acesso humano; uma política Service Auth separada limita o token
  de máquina ao worker do homelab.

### Worker no homelab

O worker roda como serviço do usuário `rodrigo`, com `loginctl` linger, e inicia
somente conexões HTTPS de saída para `gerentin.buscadin.app`. Não abre portas,
não recebe conexões iniciadas pela VPS e não altera WireGuard, firewall ou proxy.

Instale `scripts/carousel_worker.py` em
`~/.local/share/buscadin-carousel/carousel_worker.py` e a unit
`scripts/buscadin-carousel-worker.service` em
`~/.config/systemd/user/buscadin-carousel-worker.service`. Crie
`~/.config/buscadin-carousel/worker.env` com modo `0600`:

```ini
BUSCADIN_CAROUSEL_ADMIN_URL=https://gerentin.buscadin.app
BUSCADIN_CAROUSEL_WORKER_TOKEN=<mesmo segredo do Docker Secret>
CF_ACCESS_CLIENT_ID=<client id do token de serviço Cloudflare>
CF_ACCESS_CLIENT_SECRET=<client secret do token de serviço Cloudflare>
```

O segredo do Cloudflare tem validade de um ano; programe a rotação antes do
vencimento. O perfil Hermes e o arquivo `auth.json` ficam no usuário `rodrigo`.
O systemd limita o serviço ao diretório de dados do Hermes e bloqueia privilégios
adicionais. A unit usa o modelo Codex por chamada e não altera o perfil padrão.

```sh
systemctl --user daemon-reload
systemctl --user enable --now buscadin-carousel-worker.service
systemctl --user status buscadin-carousel-worker.service
journalctl --user -u buscadin-carousel-worker.service -n 50 --no-pager
```

Os logs contêm estado e IDs dos pedidos, sem prompts, tokens ou respostas do
modelo. Se o worker cair depois de reivindicar um pedido, ele volta à fila após
15 minutos. Há no máximo quatro tentativas antes de o painel marcar falha.

## Operação

- `queued`: aguardando o homelab.
- `generating`: reivindicado; pedidos sem atualização por 15 minutos podem ser
  retomados pelo worker.
- `draft`: conteúdo aguardando revisão humana.
- `posted`: operador registrou a publicação; as vagas não voltam à seleção.
- `failed`: quatro tentativas esgotadas; o painel permite tentar novamente.
- `discarded`: pedido descartado; as vagas ficam disponíveis outra vez.

As imagens são renderizadas no navegador com a identidade visual atual do
Buscadin. Não há publicação automática, uso de API paga separada, bot Telegram
ou servidor Hermes acessível pela internet.
