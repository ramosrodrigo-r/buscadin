#!/bin/sh
# VPS edge only. Never flush Docker, FORWARD, NAT, or WireGuard rules.
set -eu
for fw in iptables ip6tables; do
    "$fw" -w -N BUSCADIN-EDGE 2>/dev/null || true
    "$fw" -w -F BUSCADIN-EDGE
    "$fw" -w -A BUSCADIN-EDGE -p tcp --dport 3000 -j DROP
    "$fw" -w -A BUSCADIN-EDGE -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
    if [ "$fw" = iptables ]; then
        "$fw" -w -A BUSCADIN-EDGE -p icmp -j ACCEPT
    else
        # Includes IPv6 neighbour discovery and path MTU discovery.
        "$fw" -w -A BUSCADIN-EDGE -p ipv6-icmp -j ACCEPT
    fi
    "$fw" -w -A BUSCADIN-EDGE -p tcp -m multiport --dports 22,80,443 -j ACCEPT
    "$fw" -w -A BUSCADIN-EDGE -p udp -m multiport --dports 443,51820 -j ACCEPT
    "$fw" -w -A BUSCADIN-EDGE -j DROP
    "$fw" -w -C INPUT -i eth0 -j BUSCADIN-EDGE 2>/dev/null ||
        "$fw" -w -I INPUT 1 -i eth0 -j BUSCADIN-EDGE
    # Docker-published ports traverse FORWARD, not INPUT. Match the original
    # public port so an internal backend on :3000 behind HTTPS is unaffected.
    "$fw" -w -C DOCKER-USER -i eth0 -p tcp -m conntrack --ctorigdstport 3000 -j DROP 2>/dev/null ||
        "$fw" -w -I DOCKER-USER 1 -i eth0 -p tcp -m conntrack --ctorigdstport 3000 -j DROP
done
