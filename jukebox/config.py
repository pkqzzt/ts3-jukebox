"""Configuration loading for ts3-jukebox (TOML, stdlib tomllib)."""
from __future__ import annotations

import os
import tomllib


class Config:
    """Thin wrapper around a parsed TOML file with path helpers."""

    def __init__(self, data: dict, base_dir: str):
        self.data = data
        self.base_dir = base_dir

    @classmethod
    def load(cls, path: str) -> "Config":
        path = os.path.abspath(os.path.expanduser(path))
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
        return cls(data, os.path.dirname(path))

    def section(self, name: str) -> dict:
        value = self.data.get(name)
        return value if isinstance(value, dict) else {}

    def get(self, section: str, key: str, default=None):
        return self.section(section).get(key, default)

    def plugin(self, name: str) -> dict:
        plugins = self.section("plugins")
        value = plugins.get(name)
        return value if isinstance(value, dict) else {}

    def path(self, value: str | None, default: str) -> str:
        value = value or default
        value = os.path.expanduser(str(value))
        if not os.path.isabs(value):
            value = os.path.join(self.base_dir, value)
        return os.path.normpath(value)
