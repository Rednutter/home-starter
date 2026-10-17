#!/bin/sh
# Restrict the upstream plaintext ESPHome API to this installation's HA server.
# Only this named table and TCP port are changed; existing firewall policy stays.
set -eu
test "$(id -u)" -eq 0
: "${HOME_STARTER_HA_IPV4:?Supply the verified HA Green IPv4 address}"
/usr/bin/python3 -c 'import ipaddress,os; a=ipaddress.IPv4Address(os.environ["HOME_STARTER_HA_IPV4"]); assert a.is_private'
install -d -m 0755 /etc/home-starter
cat > /etc/home-starter/voice-firewall.nft <<EOF
table inet home_starter_voice {
    chain input {
        type filter hook input priority -10; policy accept;
        meta nfproto ipv4 tcp dport 6053 ip saddr != { 127.0.0.1, $HOME_STARTER_HA_IPV4 } reject
        meta nfproto ipv6 tcp dport 6053 reject
    }
}
EOF
cat > /etc/systemd/system/home-starter-voice-firewall.service <<'EOF'
[Unit]
Description=Restrict the Home Starter voice API to Home Assistant
Before=user@1000.service

[Service]
Type=oneshot
RemainAfterExit=yes
ExecStartPre=-/usr/sbin/nft delete table inet home_starter_voice
ExecStart=/usr/sbin/nft -f /etc/home-starter/voice-firewall.nft
ExecStartPost=/usr/bin/touch /run/home-starter-voice-firewall-ready
ExecStop=/usr/bin/rm -f /run/home-starter-voice-firewall-ready
ExecStop=/usr/sbin/nft delete table inet home_starter_voice

[Install]
WantedBy=multi-user.target
EOF
/usr/sbin/nft --check -f /etc/home-starter/voice-firewall.nft
systemctl daemon-reload
systemctl enable --now home-starter-voice-firewall.service
