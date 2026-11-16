"""Plugin registry with automatic discovery.

Any module inside this package that defines a Plugin subclass with a
non-empty id is registered automatically, so adding a music source means
dropping one file here (plus an optional [plugins.<id>] config section).
"""
from __future__ import annotations

import importlib
import inspect
import os
import pkgutil

from .base import Plugin, PluginError


def _discover() -> dict[str, type[Plugin]]:
    found: dict[str, type[Plugin]] = {}
    package_dir = os.path.dirname(os.path.abspath(__file__))
    for module in pkgutil.iter_modules([package_dir]):
        if module.name.startswith("_") or module.name == "base":
            continue
        try:
            mod = importlib.import_module("." + module.name, __package__)
        except Exception:  # a broken plugin must not break the others
            continue
        for _, obj in inspect.getmembers(mod, inspect.isclass):
            if not issubclass(obj, Plugin) or obj is Plugin:
                continue
            plugin_id = getattr(obj, "id", "")
            if plugin_id:
                found[plugin_id] = obj
    return found


PLUGIN_CLASSES = _discover()


def available() -> list[str]:
    return sorted(PLUGIN_CLASSES)


def create(name: str, conf: dict, app_dir: str) -> Plugin:
    try:
        cls = PLUGIN_CLASSES[name]
    except KeyError:
        raise ValueError("unknown plugin: %s" % name) from None
    return cls(conf, app_dir)
