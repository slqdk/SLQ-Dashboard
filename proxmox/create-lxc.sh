#!/bin/bash
# Creates the Proxmox LXC for SLQ Dashboard and installs it. Run on the Proxmox
# host as root. Set the values below first, or pass them in the environment:
#
#   CTID=109 IP=30.11.0.109 GATEWAY=30.11.0.1 bash create-lxc.sh
#
# Debian 12, unprivileged, nesting + keyctl (Docker needs them), as FamilyLog's.
set -euo pipefail

CTID="${CTID:?Set CTID, the container number, e.g. CTID=109}"
IP="${IP:?Set IP, e.g. IP=30.11.0.109}"
GATEWAY="${GATEWAY:?Set GATEWAY, your router}"
PREFIX="${PREFIX:-20}"                  # the home LAN is a /20
HOSTNAME="${HOSTNAME_LXC:-slq-dashboard}"
STORAGE="${STORAGE:-local-lvm}"
BRIDGE="${BRIDGE:-vmbr0}"
CORES="${CORES:-2}"
MEMORY="${MEMORY:-1024}"
SWAP="${SWAP:-512}"
DISK="${DISK:-16}"
REPO="${REPO:-https://github.com/slqdk/SLQ-Dashboard.git}"

pveam update >/dev/null
TEMPLATE="$(pveam available --section system | awk '/debian-12-standard/ {print $2}' | sort -V | tail -1)"
[ -n "$TEMPLATE" ] || { echo "No Debian 12 template found"; exit 1; }
pveam list local | grep -q "$TEMPLATE" || pveam download local "$TEMPLATE"

pct create "$CTID" "local:vztmpl/$TEMPLATE" \
  --hostname "$HOSTNAME" --cores "$CORES" --memory "$MEMORY" --swap "$SWAP" \
  --rootfs "$STORAGE:$DISK" --unprivileged 1 --features nesting=1,keyctl=1 \
  --net0 "name=eth0,bridge=$BRIDGE,ip=$IP/$PREFIX,gw=$GATEWAY" --onboot 1
pct start "$CTID"
sleep 5

pct exec "$CTID" -- bash -c "
  set -e
  apt-get update -qq
  apt-get install -y -qq curl git python3 ca-certificates
  curl -fsSL https://get.docker.com | sh
  git clone '$REPO' /opt/slq-dashboard
  cd /opt/slq-dashboard
  bash update.sh compose up -d --build
"
echo
echo "SLQ Dashboard kører på http://$IP:8090"
echo "Åbn adressen og opret administratoren. Resten sættes op under Admin."
