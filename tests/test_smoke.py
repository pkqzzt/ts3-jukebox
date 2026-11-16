"""Smoke tests that do not need TeamSpeak, NetEase or Apple Music."""
import os
import tempfile
import unittest
import urllib.request

from jukebox.config import Config
from jukebox.media import MediaServer
from jukebox.plugins import create
from jukebox.plugins.base import Plugin

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class ConfigTests(unittest.TestCase):
    def test_example_config_loads(self):
        cfg = Config.load(os.path.join(ROOT, "config.example.toml"))
        self.assertEqual(cfg.get("server", "port"), 8080)
        self.assertEqual(cfg.plugin("netease")["level"], "exhigh")
        self.assertTrue(cfg.get("plugins", "enabled"))

    def test_relative_paths_resolve_against_config(self):
        cfg = Config.load(os.path.join(ROOT, "config.example.toml"))
        path = cfg.path("data/media", "data/media")
        self.assertTrue(os.path.isabs(path))


class PluginTests(unittest.TestCase):
    def test_every_plugin_has_identity(self):
        from jukebox.plugins import PLUGIN_CLASSES

        for name, cls in PLUGIN_CLASSES.items():
            self.assertEqual(cls.id, name)
            self.assertTrue(cls.title)

    def test_plugin_describe(self):
        plugin = Plugin({}, ROOT)
        plugin.id = "demo"
        plugin.title = "Demo"
        self.assertEqual(plugin.describe()["id"], "demo")

    def test_unknown_plugin_rejected(self):
        with self.assertRaises(ValueError):
            create("nope", {}, ROOT)


class MediaTests(unittest.TestCase):
    def test_serves_files_and_ranges(self):
        with tempfile.TemporaryDirectory() as tmp:
            name = "track.m4a"
            with open(os.path.join(tmp, name), "wb") as fh:
                fh.write(b"0123456789" * 100)
            # pick a free-ish port
            server = MediaServer(tmp, port=18081).start()
            try:
                with urllib.request.urlopen(server.url(name), timeout=5) as resp:
                    self.assertEqual(resp.status, 200)
                    self.assertEqual(len(resp.read()), 1000)
                req = urllib.request.Request(server.url(name), headers={"Range": "bytes=10-19"})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    self.assertEqual(resp.status, 206)
                    self.assertEqual(resp.read(), b"0123456789")
                with self.assertRaises(Exception):
                    urllib.request.urlopen(server.url("missing.m4a"), timeout=5)
            finally:
                server.stop()

    def test_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            server = MediaServer(tmp, port=18082).start()
            try:
                with self.assertRaises(Exception):
                    urllib.request.urlopen(server.url("..%2Fetc%2Fpasswd"), timeout=5)
            finally:
                server.stop()


if __name__ == "__main__":
    unittest.main()
