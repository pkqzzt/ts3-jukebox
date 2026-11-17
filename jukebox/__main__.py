"""CLI entry point: python -m jukebox -c config.toml"""
from __future__ import annotations

import argparse
import os

from .config import Config
from .media import MediaClient, MediaServer
from .web import serve


def main():
    parser = argparse.ArgumentParser(prog="ts3-jukebox", description="TeamSpeak 3 点歌台")
    parser.add_argument("-c", "--config", default="config.toml", help="path to config.toml")
    args = parser.parse_args()

    config = Config.load(args.config)
    media_dir = config.path(config.get("media", "dir"), "data/media")
    media_host = str(config.get("media", "host", "127.0.0.1"))
    media_port = int(config.get("media", "port", 8081))
    if bool(config.get("media", "embedded", True)):
        media = MediaServer(media_dir, host=media_host, port=media_port).start()
    else:
        media = MediaClient(media_host, media_port, roots=[media_dir])
    web_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")
    serve(config, media, web_dir)


if __name__ == "__main__":
    main()
