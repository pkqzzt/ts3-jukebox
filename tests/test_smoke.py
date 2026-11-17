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


class NeteaseUrlTests(unittest.TestCase):
    def test_playlist_id_from_share_link(self):
        from jukebox.plugins.netease import playlist_id

        self.assertEqual(playlist_id("https://music.163.com/playlist?id=503017766&uct2=abc%2Bdef"), "503017766")
        self.assertEqual(playlist_id("https://music.163.com/#/playlist?id=12"), "12")
        self.assertEqual(playlist_id("https://y.music.163.com/m/playlist?id=34&userid=1"), "34")
        self.assertEqual(playlist_id("https://music.163.com/playlist/56"), "56")
        self.assertIsNone(playlist_id("https://music.163.com/song?id=78"))


class ApplePlaylistUrlTests(unittest.TestCase):
    def test_shared_library_playlist_url(self):
        import importlib.util
        import os

        path = os.path.join(ROOT, "scripts", "apple", "playlist.py")
        spec = importlib.util.spec_from_file_location("apple_playlist_script", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        match = module.URL_RE.search("https://music.apple.com/cn/playlist/11/pl.u-r2yBDbkFRzBlqkL")
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "cn")
        self.assertEqual(match.group(2), "pl.u-r2yBDbkFRzBlqkL")
        catalog = module.URL_RE.search("https://music.apple.com/hk/playlist/top-hits/pl.f4d106fed2bd41149aaacabb233eb5eb")
        self.assertEqual(catalog.group(2), "pl.f4d106fed2bd41149aaacabb233eb5eb")


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
