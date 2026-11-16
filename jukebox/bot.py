"""Minimal client for the TS3AudioBot web API."""
from __future__ import annotations

import json
import urllib.parse
import urllib.request


class BotError(Exception):
    pass


class BotClient:
    """Talks to a TS3AudioBot instance over its local HTTP API.

    The bot exposes everything under /api/bot/use/<id>/(/<command>); the
    default bot id is 0.
    """

    def __init__(self, url: str, context: str = "/api/bot/use/0/(/", timeout: float = 15):
        self.base = url.rstrip("/")
        self.context = context
        self.timeout = timeout

    def _call(self, path: str, timeout: float | None = None) -> bytes:
        url = self.base + self.context + path
        with urllib.request.urlopen(url, timeout=timeout or self.timeout) as resp:
            if not 200 <= resp.status < 300:  # TS3AudioBot answers 204 for commands without body
                raise BotError("bot returned HTTP %s" % resp.status)
            return resp.read()

    def song(self, timeout: float | None = None) -> dict | None:
        try:
            data = self._call("song", timeout=timeout)
            return json.loads(data)
        except Exception:
            return None

    def play(self, link: str | None = None) -> None:
        path = "play" if not link else "play/" + urllib.parse.quote(link, safe="")
        self._call(path)

    def pause(self) -> None:
        self._call("pause")

    def stop(self) -> None:
        self._call("stop")

    def seek(self, position: float) -> None:
        """Jump to an absolute position in seconds."""
        self._call("seek/%d" % max(0, int(round(position))))

    def volume(self, value: int) -> None:
        self._call("volume/%d" % int(value))

    def set_description(self, text: str) -> None:
        try:
            self._call("bot/description/set/" + urllib.parse.quote(text, safe=""))
        except Exception:
            pass
