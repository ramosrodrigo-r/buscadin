# Pipeline de carrossel editorial

O operador seleciona de uma a oito vagas em **Carrosséis**, pede um rascunho,
revisa o texto, baixa os PNGs e registra a publicação manual. Cada pedido congela
os fatos das vagas. Vagas em pedidos ativos ou postados não voltam à seleção;
descartar um pedido libera sua seleção. Depois de quatro falhas automáticas, uma
nova tentativa manual reinicia o orçamento e registra o contador anterior na auditoria.

Depois da revisão, o operador também pode aprovar o carrossel para envio como
rascunho ao Postiz. O fluxo e suas condições de ativação estão em
`docs/POSTIZ-BRIDGE.md`; aprovar não agenda nem publica o post.

## Execução isolada

O worker do homelab consulta a fila por HTTPS de saída, usando Service Auth do
Cloudflare e um token backend independente. A senha humana e os tokens de máquina
não chegam ao navegador. Nenhuma porta do homelab é publicada para esta integração.

`scripts/hermes-sandbox` inicia um contêiner novo por geração, com usuário 1000,
rootfs somente leitura, capabilities removidas, no-new-privileges e limites de
memória, CPU, processos e tempo. O contêiner não recebe home, chaves SSH, socket
Docker, socket de gateway ou tokens Cloudflare/backend. O perfil OAuth dedicado
é o único diretório persistente montado; /tmp e o home interno são temporários.

O runner usa a biblioteca `AIAgent` do Hermes diretamente, com
`enabled_toolsets=[]`, configuração congelada em safe mode, sem MCP, plugins,
memória, arquivos de contexto, revisão em segundo plano ou fallback. Ele verifica
que a lista efetiva de ferramentas está vazia antes da inferência e rejeita
respostas contendo chamadas de ferramentas. Não usa o CLI legado nem um gateway.
O provedor é `openai-codex`, modelo `gpt-6-luna`, com OAuth do perfil dedicado.

A imagem contém uma cópia do código, Python e dependências do Hermes, sem OAuth.
A revisão auditada é `f0d94882e89ab8d4098b5bb2f166adfb9ee0a0ab`.
`build_carousel_sandbox.py` recusa revisões diferentes e produz o manifesto de
runtime selado do Hermes. Atualizar esse runtime exige nova revisão e rebuild.

## Instalação no homelab

Copie os scripts para `~/.local/share/buscadin-carousel/` e execute o builder
nesse diretório com Python 3. Crie um perfil dedicado em
`~/.local/state/buscadin-hermes/profile` (0700), provisionando seu OAuth em
`auth.json` (0600) sem incluí-lo na imagem ou no Git.

O arquivo `~/.config/buscadin-carousel/worker.env` (0600) contém:

```ini
BUSCADIN_CAROUSEL_ADMIN_URL=https://gerentin.buscadin.app
BUSCADIN_CAROUSEL_WORKER_TOKEN=<segredo backend>
CF_ACCESS_CLIENT_ID=<client id>
CF_ACCESS_CLIENT_SECRET=<client secret>
```

O segredo backend está no Docker Secret `buscadin_carousel_worker_20261102`,
montado no admin como `/run/secrets/carousel_worker_token`, referenciado por
`CAROUSEL_WORKER_TOKEN_FILE`. O token Cloudflare vence em novembro de 2027;
rotacione antes do vencimento. O OAuth do perfil dedicado pode exigir nova
autenticação quando revogado ou expirado; não há fallback para outro provedor.

Instale a unit de usuário, execute `systemctl --user daemon-reload` e
`systemctl --user enable --now buscadin-carousel-worker.service`. O linger permite
iniciar sem sessão SSH ativa. O worker tem o home oculto, exceto seus scripts
montados somente leitura; somente o daemon Docker abre o perfil de inferência.

## Verificação

`hermes-sandbox --check` inicializa o agente sem inferência e exige zero
ferramentas. Uma geração sintética deve retornar JSON e passar pelo esquema do
admin antes de usar vagas reais. Os logs do worker registram IDs/estados, sem
prompts, credenciais ou respostas do modelo.

A API valida capa, uma lâmina por vaga em ordem e encerramento. Os títulos de
vagas são substituídos pelos títulos curados. Textos são escapados na interface
e desenhados como texto no canvas. A publicação continua manual.
