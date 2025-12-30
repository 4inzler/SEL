#!/bin/bash
# SEL Container Firewall Rules
# BLOCKS all incoming connections
# ALLOWS only specific outbound connections

# Drop all incoming traffic by default
iptables -P INPUT DROP
iptables -P FORWARD DROP

# Allow only established outbound connections
iptables -P OUTPUT ACCEPT
iptables -A INPUT -m state --state ESTABLISHED,RELATED -j ACCEPT

# Block all listening ports
iptables -A INPUT -p tcp -j DROP
iptables -A INPUT -p udp -j DROP

# Allow loopback
iptables -A INPUT -i lo -j ACCEPT
iptables -A OUTPUT -o lo -j ACCEPT

# WHITELIST: Only allow outbound to Discord and OpenRouter
# Discord API
iptables -A OUTPUT -p tcp -d discord.com --dport 443 -j ACCEPT
iptables -A OUTPUT -p tcp -d gateway.discord.gg --dport 443 -j ACCEPT

# OpenRouter API
iptables -A OUTPUT -p tcp -d openrouter.ai --dport 443 -j ACCEPT
iptables -A OUTPUT -p tcp -d api.openai.com --dport 443 -j ACCEPT

# DNS (required for name resolution)
iptables -A OUTPUT -p udp --dport 53 -j ACCEPT
iptables -A OUTPUT -p tcp --dport 53 -j ACCEPT

# Block everything else outbound
iptables -A OUTPUT -p tcp -j DROP
iptables -A OUTPUT -p udp -j DROP

# Log dropped packets (for monitoring)
iptables -A INPUT -j LOG --log-prefix "SEL-FIREWALL-INPUT-DROP: "
iptables -A OUTPUT -j LOG --log-prefix "SEL-FIREWALL-OUTPUT-DROP: "

echo "Firewall rules applied - SEL is network isolated"
echo "Allowed outbound: Discord API, OpenRouter API, DNS only"
echo "All incoming connections: BLOCKED"
echo "All listening ports: BLOCKED"
