"""End-to-end tests for the panel: fake TS3AudioBot + real HTTP server."""
import http.client
import json
import os
import tempfile
import threading
import time
import unittest
import warnings
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from jukebox.config import Config
from jukebox.media import MediaServer
from jukebox.plugins.base import Plugin
from jukebox.web import build_server

warnings.filterwarnings("ignore", category=ResourceWarning)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASSWORD = "test-secret"


class FakePlugin(Plugin):
    id = "fake"
    title = "Fake"

    def __init__(self, conf, app_dir):
        super().__init__(conf, app_dir)
        self.prepared = []
        self.prefetched = []

    def search(self, query, limit=20):
        return [{"source": self.id, "id": str(i), "name": "%s %d" % (query, i)} for i in range(limit)]

    def prepare(self, track, media):
        self.prepared.append(track["id"])
        return "http://fake.local/%s.mp3" % track["id"]

    def prefetch(self, track, media):
        self.prefetched.append(track["id"])

    def playlist(self, url):
        return {"source": self.id, "id": "pl1", "title": "Test List", "artist": "tester", "cover": "",
                "tracks": [{"source": self.id, "id": "p1", "name": "P1", "artist": "a"},
                           {"source": self.id, "id": "p2", "name": "P2", "artist": "b"}]}


class FakeBot:
    """Minimal TS3AudioBot API double that records calls."""

    def __init__(self):
        self.calls = []
        self.song_state = {"Position": 1.0, "Length": 10.0, "Paused": False}
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def do_GET(self):
                outer.calls.append(urllib.parse.unquote(self.path))
                body = json.dumps(outer.song_state).encode() if self.path.endswith("/song") else b'{"ok":true}'
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @property
    def url(self):
        return "http://127.0.0.1:%d" % self.port

    def stop(self):
        self.server.shutdown()


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class PanelTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.bot = FakeBot()
        cfg = os.path.join(self.tmp.name, "config.toml")
        with open(cfg, "w", encoding="utf-8") as fh:
            fh.write(
                '[server]\nhost = "127.0.0.1"\nport = 0\npassword = "%s"\n'
                'state_file = "state.json"\nsecret_file = "secret"\n'
                'worker = false\nlogin_limit = 3\nlogin_window = 60\n'
                '[bot]\nurl = "%s"\ncontext = "/api/bot/use/0/(/"\n'
                '[media]\nhost = "127.0.0.1"\nport = 0\ndir = "media"\n'
                '[plugins]\nenabled = []\n' % (PASSWORD, self.bot.url))
        config = Config.load(cfg)
        media = MediaServer(os.path.join(self.tmp.name, "media"), port=0)
        self.app, self.server = build_server(config, media, os.path.join(ROOT, "web"), start_threads=False)
        self.app.plugins["fake"] = FakePlugin({}, self.tmp.name)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = "http://127.0.0.1:%d" % self.server.server_address[1]
        self.cookie = self.login_cookie()

    def tearDown(self):
        self.server.shutdown()
        self.bot.stop()
        self.tmp.cleanup()

    def login_cookie(self):
        """Perform a real login and return the session cookie."""
        opener = urllib.request.build_opener(NoRedirect)
        data = urllib.parse.urlencode({"password": PASSWORD}).encode()
        try:
            opener.open(self.base + "/login", data=data, timeout=5)
        except urllib.error.HTTPError as exc:
            return (exc.headers.get("Set-Cookie") or "").split(";")[0]
        return ""

    def login(self, password=PASSWORD):
        """Return the redirect target: "/" on success, "/login?err=N" otherwise."""
        opener = urllib.request.build_opener(NoRedirect)
        data = urllib.parse.urlencode({"password": password}).encode()
        try:
            resp = opener.open(self.base + "/login", data=data, timeout=5)
            return resp.headers.get("Location") or "/"
        except urllib.error.HTTPError as exc:
            return exc.headers.get("Location") or ""

    def request(self, path, method="GET", payload=None):
        req = urllib.request.Request(self.base + path, method=method)
        req.add_header("Cookie", self.cookie)
        data = None
        if payload is not None:
            data = json.dumps(payload).encode()
            req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, data=data, timeout=5) as resp:
            return resp.status, json.loads(resp.read() or b"{}")

    def wait_for_call(self, fragment, timeout=2.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if any(fragment in call for call in self.bot.calls):
                return True
            time.sleep(0.05)
        return False

    def wait_playing(self, timeout=3.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            _, state = self.request("/api/state")
            if state.get("current") and state["current"].get("status") == "playing":
                return state
            time.sleep(0.05)
        return self.request("/api/state")[1]


class AuthTests(PanelTestCase):
    def test_wrong_password_redirects_with_error(self):
        self.assertTrue(self.login("nope").endswith("err=1"))

    def test_login_is_throttled(self):
        for _ in range(3):
            self.login("nope")
        self.assertTrue(self.login("nope").endswith("err=2"))

    def test_success_resets_failures(self):
        self.login("nope")
        self.login("nope")
        self.assertEqual(self.login(PASSWORD), "/")
        self.assertTrue(self.login("nope").endswith("err=1"))


class QueueTests(PanelTestCase):
    def test_add_plays_through_plugin(self):
        status, _ = self.request("/api/add", "POST", {"source": "fake", "id": "1", "name": "Song"})
        self.assertEqual(status, 200)
        state = self.wait_playing()
        self.assertEqual(state["current"]["name"], "Song")
        self.assertTrue(self.wait_for_call("/play/"))

    def test_history_records_started_track(self):
        self.request("/api/add", "POST", {"source": "fake", "id": "2", "name": "Track"})
        self.wait_playing()
        _, state = self.request("/api/state")
        self.assertEqual(state["history"][0]["name"], "Track")

    def test_skip_clears_current(self):
        self.request("/api/add", "POST", {"source": "fake", "id": "3", "name": "Skip"})
        self.wait_playing()
        self.request("/api/skip", "POST", {})
        _, state = self.request("/api/state")
        self.assertIsNone(state["current"])

    def test_reorder_moves_item(self):
        for i in range(3):
            self.request("/api/add", "POST", {"source": "fake", "id": str(10 + i), "name": "Q%d" % i})
        _, state = self.request("/api/state")
        names = [x["name"] for x in state["queue"]]
        self.assertGreaterEqual(len(names), 2)
        self.request("/api/reorder", "POST", {"from": 0, "to": len(names) - 1})
        _, state = self.request("/api/state")
        self.assertEqual(state["queue"][-1]["name"], names[0])

    def test_clear_queue_keeps_current(self):
        self.request("/api/add", "POST", {"source": "fake", "id": "30", "name": "Playing"})
        self.wait_playing()
        for i in range(2):
            self.request("/api/add", "POST", {"source": "fake", "id": "4%d" % i, "name": "Queued%d" % i})
        _, state = self.request("/api/state")
        self.assertGreaterEqual(len(state["queue"]), 1)
        current = state["current"]["name"]
        status, _ = self.request("/api/clear", "POST", {})
        self.assertEqual(status, 200)
        _, state = self.request("/api/state")
        self.assertEqual(state["queue"], [])
        self.assertEqual(state["current"]["name"], current)

    def test_remove_drops_item(self):
        for i in range(2):
            self.request("/api/add", "POST", {"source": "fake", "id": str(20 + i), "name": "R%d" % i})
        _, state = self.request("/api/state")
        before = len(state["queue"])
        self.request("/api/remove", "POST", {"index": 0})
        _, state = self.request("/api/state")
        self.assertEqual(len(state["queue"]), before - 1)


class PlaylistTests(PanelTestCase):
    def setUp(self):
        super().setUp()
        self.app.plugins["netease"] = self.app.plugins["fake"]

    def test_playlist_is_parsed(self):
        status, data = self.request("/api/playlist?url=" + urllib.parse.quote("https://music.163.com/playlist?id=123"))
        self.assertEqual(status, 200)
        self.assertEqual(data["playlist"]["title"], "Test List")
        self.assertEqual([x["name"] for x in data["playlist"]["tracks"]], ["P1", "P2"])

    def test_unknown_host_is_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.request("/api/playlist?url=" + urllib.parse.quote("https://example.com/list"))
        self.assertEqual(ctx.exception.code, 400)

    def test_bulk_add_queues_tracks(self):
        tracks = [{"source": "fake", "id": "b1", "name": "B1"},
                  {"source": "fake", "id": "b2", "name": "B2"}]
        status, data = self.request("/api/add_bulk", "POST", {"tracks": tracks})
        self.assertEqual(status, 200)
        self.assertEqual(data["added"], 2)
        _, state = self.request("/api/state")
        self.assertEqual(state["current"]["name"], "B1")
        self.assertEqual([x["name"] for x in state["queue"]], ["B2"])


class PublicPlaylistTests(PanelTestCase):
    def test_publish_list_fetch_delete(self):
        playlist = {"source": "fake", "id": "p1", "title": "公共歌单", "artist": "t",
                    "tracks": [{"source": "fake", "id": "x1", "name": "X1"}]}
        status, data = self.request("/api/public_playlists", "POST", {"playlist": playlist})
        self.assertEqual(status, 200)
        _, listing = self.request("/api/public_playlists")
        self.assertEqual(len(listing["playlists"]), 1)
        self.assertEqual(listing["playlists"][0]["count"], 1)
        self.assertEqual(listing["playlists"][0]["title"], "公共歌单")
        _, full = self.request("/api/public_playlists?id=" + urllib.parse.quote(data["id"]))
        self.assertEqual(full["playlist"]["tracks"][0]["name"], "X1")
        status, _ = self.request("/api/public_playlists/delete", "POST", {"id": data["id"]})
        self.assertEqual(status, 200)
        _, listing = self.request("/api/public_playlists")
        self.assertEqual(listing["playlists"], [])

    def test_unknown_source_is_rejected(self):
        playlist = {"source": "nope", "id": "p2", "title": "x",
                    "tracks": [{"source": "nope", "id": "1", "name": "n"}]}
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.request("/api/public_playlists", "POST", {"playlist": playlist})
        self.assertEqual(ctx.exception.code, 400)


class PluginTests(PanelTestCase):
    def test_search_returns_limit(self):
        status, data = self.request("/api/search?source=fake&q=hello&limit=7")
        self.assertEqual(status, 200)
        self.assertEqual(len(data["songs"]), 7)

    def test_unknown_source_rejected(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.request("/api/search?source=nope&q=x")
        self.assertEqual(ctx.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
