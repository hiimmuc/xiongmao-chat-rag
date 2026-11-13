#!/usr/bin/env bash
# One-time setup of the staging VM (Ubuntu 24.04 LTS). Run it on the VM as root:
#   sudo bash setup-vm.sh staging_deploy.pub
# Installs Docker, adds swap, creates the `deploy` user that GitHub Actions logs in as
# (with only the given public key), and creates /opt/xiongmao (app) and /data (database, uploads, certificates).
set -euo pipefail
KEY_FILE="$1"
[ -s "$KEY_FILE" ] || { echo "Usage: sudo bash setup-vm.sh <deploy-public-key-file>" >&2; exit 1; }

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y docker.io docker-compose-v2 openssl
systemctl enable --now docker

# 2 GiB swap, so migrations and indexing never run out of memory on a small VM.
if [ ! -f /swapfile ]; then
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
swapon -a

# The deploy user may run Docker (needed to deploy) but has no sudo and no password.
id deploy >/dev/null 2>&1 || useradd --create-home --shell /bin/bash deploy
usermod -aG docker deploy
install -d -m 700 -o deploy -g deploy /home/deploy/.ssh
tr -d '\r' < "$KEY_FILE" > /home/deploy/.ssh/authorized_keys
chown deploy:deploy /home/deploy/.ssh/authorized_keys
chmod 600 /home/deploy/.ssh/authorized_keys

install -d -o deploy -g deploy /opt/xiongmao /data
install -d -o 10001 -g 10001 /data/storage # uploads; the API image runs as uid 10001
echo "Ready. GitHub Actions can now deploy as deploy@$(hostname)."
