#!/usr/bin/env bash
# Deploy ts3-jukebox from a git checkout into /opt/jukebox.
# Usage: sudo bash deploy/install.sh [target-dir]
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DST="${1:-/opt/jukebox}"

echo "==> installing to $DST"
mkdir -p "$DST/data/media"
cp -r "$SRC/jukebox" "$SRC/web" "$SRC/scripts" "$SRC/docs" "$SRC/config.example.toml" "$DST/"
find "$DST" -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

if [ ! -f "$DST/config.toml" ]; then
  cp "$DST/config.example.toml" "$DST/config.toml"
  echo "==> created $DST/config.toml - edit the password and plugin paths"
fi

chmod 700 "$DST/data" 2>/dev/null || true
cp "$SRC/deploy/ts3-jukebox.service" /etc/systemd/system/ts3-jukebox.service
systemctl daemon-reload
systemctl enable --now ts3-jukebox

if [ "${WITH_MEDIA_SERVICE:-0}" = "1" ]; then
  cp "$SRC/deploy/ts3-jukebox-media.service" /etc/systemd/system/ts3-jukebox-media.service
  systemctl daemon-reload
  systemctl enable --now ts3-jukebox-media
  echo "==> media service enabled; set [media] embedded = false in config.toml"
fi

echo "==> done. status: systemctl status ts3-jukebox"
