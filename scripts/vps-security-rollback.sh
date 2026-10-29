#!/bin/sh
# Remove only this delivery's restrictions; never restore/flush whole tables.
set -eu
for fw in iptables ip6tables; do
    "$fw" -w -D INPUT -i eth0 -j BUSCADIN-EDGE 2>/dev/null || true
    "$fw" -w -D DOCKER-USER -i eth0 -p tcp -m conntrack --ctorigdstport 3000 -j DROP 2>/dev/null || true
done
systemctl disable buscadin-edge-firewall.service || true
rm -f /etc/systemd/system/docker.service.d/90-buscadin-edge.conf
systemctl daemon-reload
rm -f /etc/ssh/sshd_config.d/00-buscadin-security.conf
/usr/sbin/sshd -t && systemctl reload ssh
