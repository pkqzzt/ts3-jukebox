"""Plugin registry."""
from __future__ import annotations

from .base import Plugin, PluginError
from .netease import NeteasePlugin
from .applemusic import AppleMusicPlugin

PLUGIN_CLASSES = {cls.id: cls for cls in (NeteasePlugin, AppleMusicPlugin)}


def available() -> list[str]:
    return list(PLUGIN_CLASSES)


def create(name: str, conf: dict, app_dir: str) -> Plugin:
    try:
        cls = PLUGIN_CLASSES[name]
    except KeyError:
        raise ValueError("unknown plugin: %s" % name) from None
    return cls(conf, app_dir)
