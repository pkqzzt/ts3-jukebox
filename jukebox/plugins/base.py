"""Plugin interface shared by every music source."""
from __future__ import annotations


class PluginError(Exception):
    """Raised when a track cannot be prepared for playback."""


class Plugin:
    """A music source.

    A plugin turns a search query into track dictionaries and later turns one
    of those dictionaries into a URL the bot can play.

    Track dictionaries use a small common shape so the queue and the web UI do
    not care which plugin produced them::

        {
            "source":   "netease",          # plugin id
            "id":       "12345",            # unique inside the plugin
            "name":     "song title",
            "artist":   "artist",
            "album":    "album",
            "cover":    "https://...",      # optional
            "duration": 215000,             # milliseconds, optional
            ...                             # plugin specific extras
        }
    """

    id = ""
    title = ""

    def __init__(self, conf: dict, app_dir: str):
        self.conf = conf or {}
        self.app_dir = app_dir

    # -- lifecycle ---------------------------------------------------------
    def ready(self) -> tuple[bool, str]:
        """Return (usable, reason-when-not-usable)."""
        return True, ""

    def describe(self) -> dict:
        ready, hint = self.ready()
        return {"id": self.id, "title": self.title, "ready": ready, "hint": hint}

    # -- playback ----------------------------------------------------------
    def search(self, query: str, limit: int = 20) -> list[dict]:
        raise NotImplementedError

    def prepare(self, track: dict, media) -> str:
        """Return a playable URL for the track, downloading if necessary."""
        raise NotImplementedError

    def playlist(self, url: str) -> dict:
        """Parse a playlist share link into {"title", "tracks": [...]}."""
        raise NotImplementedError

    def prefetch(self, track: dict, media) -> None:
        """Optional: warm the cache as soon as the track is queued."""
        return None

    def validate(self, track: dict) -> str | None:
        """Optional: reject a track before it is queued."""
        return None
