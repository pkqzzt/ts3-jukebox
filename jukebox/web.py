"""HTTP panel, queue engine and worker."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import plugins as plugin_registry
from .bot import BotClient

PENDING = ("preparing", "downloading")


def _label(item: dict) -> str:
    artist = item.get("artist") or ""
    return "%s%s" % (item.get("name", ""), " - " + artist if artist else "")


class Jukebox:
    """Owns the queue, the current track and the plugin instances."""

    def __init__(self, config, media):
        self.config = config
        self.media = media
        self.bot = BotClient(
            str(config.get("bot", "url", "http://127.0.0.1:58913")),
            str(config.get("bot", "context", "/api/bot/use/0/(/")),
        )
        self.password = str(config.get("server", "password", "change-me"))
        self.worker_enabled = bool(config.get("server", "worker", True))
        self.cookie_name = str(config.get("server", "cookie_name", "jukebox_auth"))
        self.rate_limit = int(config.get("server", "rate_limit", 5))
        self.rate_window = int(config.get("server", "rate_window", 60))
        self.state_file = config.path(config.get("server", "state_file"), "data/state.json")
        self.secret_file = config.path(config.get("server", "secret_file"), "data/secret")

        self.plugins = {}
        for name in config.section("plugins").get("enabled") or []:
            try:
                self.plugins[name] = plugin_registry.create(name, config.plugin(name), config.base_dir)
            except Exception as exc:  # a broken plugin must not kill the panel
                print("plugin %s failed to load: %s" % (name, exc), file=sys.stderr)

        self.queue = []
        self.current = None
        self.lock = threading.RLock()
        self.hits = {}
        self.hits_lock = threading.Lock()
        self.secret = self._load_secret()
        self.token = hmac.new(self.secret.encode(), self.password.encode(), hashlib.sha256).hexdigest()
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
        self.load_state()

    # -- auth --------------------------------------------------------------
    def _load_secret(self):
        try:
            with open(self.secret_file, encoding="utf-8") as fh:
                value = fh.read().strip()
                if value:
                    return value
        except OSError:
            pass
        value = secrets.token_hex(32)
        os.makedirs(os.path.dirname(self.secret_file), exist_ok=True)
        with open(self.secret_file, "w", encoding="utf-8") as fh:
            fh.write(value)
        os.chmod(self.secret_file, 0o600)
        return value

    def authed(self, cookie_header: str) -> bool:
        for part in (cookie_header or "").split(";"):
            key, _, value = part.strip().partition("=")
            if key == self.cookie_name and hmac.compare_digest(value, self.token):
                return True
        return False

    def rate_ok(self, ip: str) -> bool:
        now = time.time()
        with self.hits_lock:
            hits = [t for t in self.hits.get(ip, []) if now - t < self.rate_window]
            if len(hits) >= self.rate_limit:
                self.hits[ip] = hits
                return False
            hits.append(now)
            self.hits[ip] = hits
            return True

    # -- state -------------------------------------------------------------
    def save_state(self):
        try:
            with open(self.state_file, "w", encoding="utf-8") as fh:
                json.dump({"queue": self.queue, "current": self.current}, fh, ensure_ascii=False)
        except Exception:
            pass

    def load_state(self):
        try:
            with open(self.state_file, encoding="utf-8") as fh:
                data = json.load(fh)
            self.queue = data.get("queue") or []
            self.current = data.get("current")
            if isinstance(self.current, dict) and self.current.get("status") in PENDING:
                self.current.pop("status", None)
        except Exception:
            pass

    def plugin_list(self):
        out = []
        for name, plugin in self.plugins.items():
            try:
                out.append(plugin.describe())
            except Exception:
                out.append({"id": name, "title": name, "ready": False, "hint": "插件异常"})
        return out

    # -- playback ----------------------------------------------------------
    def start(self, item):
        plugin = self.plugins.get(item.get("source"))
        if plugin is None:
            return False
        item["status"] = "preparing"
        item.pop("error", None)
        self.current = item
        threading.Thread(target=self._prepare_and_play, args=(item, plugin), daemon=True).start()
        return True

    def _prepare_and_play(self, item, plugin):
        try:
            url = plugin.prepare(item, self.media)
        except Exception as exc:
            print("prepare failed for %r: %s" % (item.get("name"), exc), file=sys.stderr)
            with self.lock:
                item["status"] = "error"
                item["error"] = str(exc)[-200:]
                if self.current is item:
                    self.current = None
                self.save_state()
            self.bot.set_description("点歌失败：" + str(item.get("name", "")))
            return
        with self.lock:
            if self.current is not item:
                return
            item["status"] = "playing"
            self.save_state()
        try:
            self.bot.play(url)
            self.bot.set_description("正在播放：" + _label(item))
        except Exception:
            pass

    def worker(self):
        misses = 0
        while True:
            time.sleep(2)
            try:
                song = self.bot.song()
                with self.lock:
                    misses = 0 if song else misses + 1
                    pending = bool(self.current and self.current.get("status") in PENDING)
                    ended = False
                    if self.current and not pending and song:
                        length = song.get("Length") or 0
                        if not length and self.current.get("duration"):
                            try:
                                length = float(self.current["duration"]) / 1000.0
                            except Exception:
                                length = 0
                        if length > 0 and (song.get("Position") or 0) >= length - 1:
                            ended = True
                    if self.current and not pending and misses >= 3:
                        ended = True
                    if ended:
                        self.current = None
                        self.bot.set_description("空闲中")
                    if self.current is None and self.queue:
                        item = self.queue.pop(0)
                        if not self.start(item):
                            self.bot.set_description("播放失败：" + str(item.get("name", "")))
                    self.save_state()
            except Exception:
                pass

    def refresh_credentials(self):
        """Re-validate plugin credentials (called at boot and every 6 hours)."""
        for plugin in self.plugins.values():
            checker = getattr(plugin, "check_auth", None)
            configured = getattr(plugin, "configured", None)
            if not callable(checker):
                continue
            try:
                if not callable(configured) or configured():
                    checker()
            except Exception:
                pass

    def auth_watch(self, interval=3600 * 6):
        self.refresh_credentials()
        while True:
            time.sleep(interval)
            self.refresh_credentials()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    app: Jukebox = None
    html = ""
    login_html = ""

    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, ctype="application/json; charset=utf-8", extra=None):
        data = body if isinstance(body, bytes) else str(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        for key, value in extra or []:
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(data)

    def _ip(self):
        return (self.headers.get("CF-Connecting-IP")
                or (self.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
                or self.client_address[0])

    def _authed(self):
        return self.app.authed(self.headers.get("Cookie") or "")

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(url.query)
        if url.path == "/login":
            return self._send(200, self.login_html, "text/html; charset=utf-8")
        if not self._authed():
            if url.path.startswith("/api/"):
                return self._send(401, json.dumps({"error": "unauthorized"}))
            return self._send(302, b"", "text/plain", [("Location", "/login")])
        if url.path in ("/", "/index.html"):
            return self._send(200, self.html, "text/html; charset=utf-8")
        if url.path == "/api/plugins":
            return self._send(200, json.dumps({"plugins": self.app.plugin_list()}, ensure_ascii=False))
        if url.path == "/api/search":
            term = (query.get("q") or [""])[0].strip()
            source = (query.get("source") or [""])[0]
            plugin = self.app.plugins.get(source)
            if plugin is None:
                return self._send(400, json.dumps({"error": "unknown source"}, ensure_ascii=False))
            if not term:
                return self._send(200, json.dumps({"songs": [], "source": source}, ensure_ascii=False))
            try:
                songs = plugin.search(term)
                ready, hint = plugin.ready()
                return self._send(200, json.dumps({"songs": songs, "source": source,
                                                   "ready": ready, "hint": hint}, ensure_ascii=False))
            except Exception as exc:
                return self._send(500, json.dumps({"error": str(exc)}, ensure_ascii=False))
        if url.path == "/api/state":
            song = self.app.bot.song()
            with self.app.lock:
                out = {"current": dict(self.app.current) if self.app.current else None,
                       "queue": list(self.app.queue)}
            if song:
                out["position"] = song.get("Position", 0)
                out["length"] = song.get("Length", 0)
                out["paused"] = song.get("Paused", False)
            out["plugins"] = self.app.plugin_list()
            return self._send(200, json.dumps(out, ensure_ascii=False))
        return self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        url = urllib.parse.urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        if length > 2_000_000:
            self.close_connection = True
            return self._send(413, json.dumps({"error": "payload too large"}))
        raw = self.rfile.read(length) if length else b""
        if url.path == "/login":
            form = urllib.parse.parse_qs(raw.decode("utf-8", "replace"))
            password = (form.get("password") or [""])[0]
            if hmac.compare_digest(password, self.app.password):
                return self._send(302, b"", "text/plain", [
                    ("Location", "/"),
                    ("Set-Cookie", "%s=%s; Path=/; HttpOnly; Max-Age=2592000; SameSite=Lax" % (self.app.cookie_name, self.app.token)),
                ])
            return self._send(302, b"", "text/plain", [("Location", "/login?err=1")])
        if not self._authed():
            return self._send(401, json.dumps({"error": "unauthorized"}))
        try:
            body = json.loads(raw or b"{}") if raw else {}
        except Exception:
            body = {}
        app = self.app
        if url.path == "/api/add":
            if not app.rate_ok(self._ip()):
                return self._send(429, json.dumps({"error": "点歌太频繁，请稍后再试"}, ensure_ascii=False))
            item = {k: v for k, v in body.items() if k not in ("insert", "status", "error")}
            plugin = app.plugins.get(str(item.get("source") or ""))
            if plugin is None:
                return self._send(400, json.dumps({"error": "unknown source"}, ensure_ascii=False))
            if not str(item.get("name") or "").strip():
                return self._send(400, json.dumps({"error": "missing name"}))
            problem = plugin.validate(item)
            if problem:
                return self._send(409, json.dumps({"error": problem}, ensure_ascii=False))
            insert = bool(body.get("insert"))
            with app.lock:
                if insert:
                    if app.current is None:
                        app.start(item)
                    else:
                        app.queue.insert(0, item)
                else:
                    app.queue.append(item)
                    if app.current is None and len(app.queue) == 1:
                        app.start(app.queue.pop(0))
                app.save_state()
            threading.Thread(target=plugin.prefetch, args=(item, app.media), daemon=True).start()
            return self._send(200, json.dumps({"ok": True}))
        if url.path == "/api/skip":
            with app.lock:
                app.current = None
                app.save_state()
            try:
                app.bot.pause()
            except Exception:
                pass
            return self._send(200, json.dumps({"ok": True}))
        if url.path == "/api/toggle":
            song = app.bot.song()
            try:
                if song and song.get("Paused"):
                    app.bot.play()
                else:
                    app.bot.pause()
            except Exception:
                pass
            return self._send(200, json.dumps({"ok": True}))
        if url.path == "/api/pause":
            try:
                app.bot.pause()
            except Exception:
                pass
            return self._send(200, json.dumps({"ok": True}))
        if url.path == "/api/play":
            try:
                app.bot.play()
            except Exception:
                pass
            return self._send(200, json.dumps({"ok": True}))
        if url.path == "/api/volume":
            try:
                app.bot.volume(int(body.get("v", 50)))
            except Exception:
                pass
            return self._send(200, json.dumps({"ok": True}))
        if url.path == "/api/remove":
            index = int(body.get("index", -1))
            with app.lock:
                if 0 <= index < len(app.queue):
                    app.queue.pop(index)
                app.save_state()
            return self._send(200, json.dumps({"ok": True}))
        return self._send(404, json.dumps({"error": "not found"}))


class PanelServer(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionResetError, BrokenPipeError, TimeoutError)):
            return
        super().handle_error(request, client_address)


def serve(config, media, web_dir):
    app = Jukebox(config, media)
    with open(os.path.join(web_dir, "index.html"), encoding="utf-8") as fh:
        Handler.html = fh.read()
    with open(os.path.join(web_dir, "login.html"), encoding="utf-8") as fh:
        Handler.login_html = fh.read()
    Handler.app = app
    host = str(config.get("server", "host", "0.0.0.0"))
    port = int(config.get("server", "port", 8080))
    if app.worker_enabled:
        threading.Thread(target=app.worker, daemon=True).start()
    threading.Thread(target=app.auth_watch, daemon=True).start()
    server = PanelServer((host, port), Handler)
    print("ts3-jukebox listening on %s:%d (plugins: %s)" % (host, port, ", ".join(app.plugins) or "none"))
    server.serve_forever()
