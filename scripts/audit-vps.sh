#!/usr/bin/env bash
# Run on the VPS: bash audit-vps.sh > audit-vps.txt
# Read-only inventory. Does not read env files, container secrets or databases.
set -eu

section() { printf '\n## %s\n' "$1"; }
section 'Data UTC'
date -u '+%Y-%m-%dT%H:%M:%SZ'
section 'Sistema'
uname -srm
if [ -r /etc/os-release ]; then
    sed -n '/^PRETTY_NAME=/p' /etc/os-release
fi
section 'CPU disponível'
if command -v nproc >/dev/null 2>&1; then nproc; fi
section 'Memória'
if command -v free >/dev/null 2>&1; then free -m; fi
section 'Disco e inodes'
df -h /
df -i /
section 'Carga atual'
uptime
section 'Portas TCP em escuta (sem processos/argumentos)'
if command -v ss >/dev/null 2>&1; then ss -ltn; fi
section 'Docker'
if command -v docker >/dev/null 2>&1; then
    docker version --format '{{.Server.Version}}' 2>/dev/null || true
    docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}' 2>/dev/null || true
    docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.BlockIO}}\t{{.NetIO}}' 2>/dev/null || true
    docker volume ls --format '{{.Name}}' 2>/dev/null || true
fi
section 'Serviços relacionados em execução'
if command -v systemctl >/dev/null 2>&1; then
    systemctl list-units --type=service --state=running --no-pager --no-legend 2>/dev/null |
        awk '/postgres|redis|nginx|caddy|docker|traefik|dokploy|buscadin/ { print $1, $3, $4 }' || true
fi
section 'Limites desta coleta'
printf '%s\n' 'Inventário pontual; não mede capacidade sustentada nem comprova backups.'
printf '%s\n' 'Banda contratada, proxy/rotas, volumes persistentes e restauração exigem verificação adicional.'
