#!/bin/sh
# Container entrypoint: make sure /data/config.toml exists, then run the panel.
set -e

if [ ! -f /data/config.toml ]; then
  cp /opt/jukebox/config.example.toml /data/config.toml
  echo "==> created /data/config.toml from the example - edit it and restart"
fi

exec python -m jukebox -c /data/config.toml
