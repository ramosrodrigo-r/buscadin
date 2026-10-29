# VPS: restrições de acesso e preservação do WireGuard

Aplicado em 29/10/2026. Não executar estes scripts em outro host sem revisar
interface, portas e topologia. O script de firewall pressupõe `eth0` e Docker.

## Configuração aplicada

- SSH por chave; senha e autenticação interativa desativadas. Root ainda aceita
  chave para preservar o acesso operacional existente. Túnel SSH preservado.
- A cadeia `BUSCADIN-EDGE` filtra somente INPUT vindo de `eth0`, em IPv4/IPv6.
  Aceita conexões estabelecidas, ICMP, TCP 22/80/443 e UDP 443/51820.
  Outras entradas são descartadas, incluindo portas administrativas do Swarm.
- A porta pública original TCP 3000 é bloqueada também em `DOCKER-USER`,
  pois portas publicadas pelo Docker podem atravessar FORWARD em vez de INPUT.
- As restrições anteriores de origem Cloudflare permanecem em `DOCKER-USER`.
- O serviço `buscadin-edge-firewall` reaplica as regras no boot. O drop-in
  `docker.service.d/90-buscadin-edge.conf` reaplica após iniciar o Docker.

Não foi alterada a política global de INPUT, nem foram descarregadas tabelas.
As cadeias preexistentes são preservadas; a restrição pública acontece pelo
hook de `eth0` na nova cadeia. Interfaces internas e loopback não são afetadas.

## Homelab

Preservar `wg-dragonwilds`, UDP 51820, peer 10.66.66.2/32, rede 172.19.0.0/16,
rota para o peer, encaminhamento IPv4, regras FORWARD e NAT, UDP 7777/8888,
SNAT e masquerade. O WireGuard recria suas regras por PostUp/PostDown.
Nunca substituir o firewall inteiro por um snapshot ou habilitar/resetar UFW
como mecanismo de manutenção desta entrega.

Antes da aplicação, foram guardados snapshots sem chaves privadas em
`/var/backups/buscadin-security-20261029/`: NAT, FORWARD e hash da configuração
WireGuard. A comparação após a aplicação não apresentou diferenças.

## Acesso ao Dokploy

```sh
ssh -N -L 127.0.0.1:13000:127.0.0.1:3000 buscadin-vps
```

Abrir `http://127.0.0.1:13000`. O HTTP fica dentro do túnel SSH.

## Arquivos instalados

| Fonte no repositório | Destino na VPS |
| --- | --- |
| scripts/vps-edge-firewall.sh | /usr/local/sbin/buscadin-edge-firewall |
| scripts/vps-edge-firewall.service | /etc/systemd/system/buscadin-edge-firewall.service |
| scripts/vps-docker-edge.conf | /etc/systemd/system/docker.service.d/90-buscadin-edge.conf |
| scripts/vps-ssh-security.conf | /etc/ssh/sshd_config.d/00-buscadin-security.conf |
| scripts/vps-security-rollback.sh | /usr/local/sbin/buscadin-security-rollback |

O rollback remove exclusivamente os hooks e o drop-in desta entrega e retorna
ao SSH anterior; reabre os acessos anteriores e deve ser reservado à recuperação.
Ele não limpa/restaura tabelas nem reinicia o túnel. O temporizador automático
de rollback usado durante a aplicação foi cancelado após validar uma nova
conexão SSH e o Dokploy pelo túnel.

## Verificação

Testados externamente SSH acessível e TCP 3000 inacessível em IPv4/IPv6.
Dokploy via túnel retornou HTTP 200. Healthcheck do Buscadin retornou OK.
WireGuard manteve handshake e aumento dos contadores de transferência.
Isso valida o túnel, mas não substitui teste funcional do jogo no homelab.

## Atualizações do host

Aplicadas 48 atualizações via APT, preservando arquivos de configuração locais.
Docker passou de 29.6.1 para 29.9.2, containerd para 2.4.2; AppArmor e bibliotecas
também foram atualizados. O reinício do Docker manteve as restrições de borda,
as regras WireGuard e os volumes. Buscadin, Dokploy e Listmonk foram revalidados.
O SSH foi reiniciado e uma nova conexão por chave foi validada.

`cloud-init` já estava em `apt-mark hold` antes desta entrega. O bloqueio foi
preservado por ser parte do provisionamento/rede da máquina. Continua como
atualização pendente, exigindo revisão do motivo desse hold antes de removê-lo.
Não foi executado reboot, nem restart de systemd-networkd/systemd-resolved ou
WireGuard. O needrestart indicou serviços ainda usando bibliotecas anteriores;
os reinícios da rede foram adiados para preservar a conectividade do homelab.
O kernel em execução estava atualizado e não havia pedido de reboot.
