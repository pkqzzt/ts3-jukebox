#!/usr/bin/env bash
# Deploy ts3-jukebox from a git checkout into /opt/jukebox.
# Usage: sudo bash deploy/install.sh [target-dir]
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DST="${1:-/opt/jukebox}"

echo "==> installing to $DST"
mkdir -p "$DST/data/media"
cp -r "$SRC/jukebox" "$SRC/web" "$SRC/scripts" "$SRC/config.example.toml" "$DST/"

if [ ! -f "$DST/config.toml" ]; then
  cp "$DST/config.example.toml" "$DST/config.toml"
  echo "==> created $DST/config.toml - edit the password and plugin paths"
fi

chmod 600 "$DST/data" 2>/dev/null || true
cp "$SRC/deploy/ts3-jukebox.service" /etc/systemd/system/ts3-jukebox.service
systemctl daemon-reload
systemctl enable --now ts3-jukebox
echo "==> done. status: systemctl status ts3-jukebox"
