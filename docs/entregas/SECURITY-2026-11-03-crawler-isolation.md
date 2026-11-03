# Correção de segurança — isolamento dos crawlers

Commit de implementação e imagens: `241490d`.

O achado de Chromium sem sandbox no mesmo contêiner dos segredos administrativos
foi corrigido. A conferência independente do auditor confirmou a configuração
ativa na VPS, sem novo bloqueador no escopo revisado.

## Estado implantado

- Admin: `buscadin-catalogue:241490d`, 1/1, UID 10001, rootfs somente leitura,
  `CapDrop=ALL`, `NoNewPrivs=1`, limites de recursos. Imagem sem `/opt/playwright`.
- Browser: `buscadin-crawler:241490d`, saudável, UID 10001, rootfs somente leitura,
  capabilities removidas, no-new-privileges, IPC privado, AppArmor dedicado e
  seccomp. Limites: 1,5 GiB de memória, 256 processos e 1 CPU.
- Browser sem portas publicadas, secrets, volumes de host, socket Docker ou
  variáveis de credenciais do aplicativo.
- Overlay `buscadin-crawler-private`, criptografia habilitada, subnet
  `172.30.240.0/24`. Endpoints: admin, crawler e balanceamento interno Docker.
- Restrição global de user namespaces do AppArmor preservada em `1`.
- Rotas WireGuard `10.66.66.0/24` e `172.19.0.0/16` preservadas.

O admin envia somente a fonte permitida, IDs conhecidos e limites pelo RPC fixo.
O retorno é validado e limitado a 4 MB, com verificação de origem, URL canônica e
identidade. Redirects, compressão e campos extras são rejeitados. Não existe
fallback para browser no admin.

## Evidências

- **57 testes direcionados passaram**, incluindo contratos RPC, fonte/ID/URL,
  resposta excessiva, compressão, redirects, concorrência, indisponibilidade sem
  fallback e falha de sandbox impedindo a inicialização do RPC.
- O probe real observou namespace adicional de PID e filtro seccomp extra em
  processo Chromium com `NoNewPrivs=1` e capabilities efetivas zeradas. Essa
  evidência é exigida a cada inicialização do serviço.
- Coletas pelo cliente real dentro do admin retornaram uma vaga com descrição
  completa de Turing, Mercor e Alignerr. Foram diagnósticos sem gravação no banco.
- A micro1 retornou falha de origem pelo RPC (HTTP 502), mantendo a indisponibilidade
  já observada anteriormente na fonte.
- Admin respondeu HTTP 200 pelo domínio protegido; worker de carrosséis ativo.
- Auditoria final somente leitura confirmou o fechamento do achado na implantação.

O RPC não usa bearer token: sua fronteira é a overlay privada exclusiva, sem
porta publicada, acessível aos dois serviços e aos administradores do Docker.
Manutenção deve preservar essa exclusividade. Detalhes e procedimento de deploy
estão em [CRAWLER-ISOLATION.md](../CRAWLER-ISOLATION.md).
