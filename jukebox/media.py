"""Local HTTP file server used to hand downloaded audio to the bot.

TS3AudioBot plays whatever URL it is given, so plugins that produce local files
(Apple Music downloads, for example) expose them through this server.
"""
from __future__ import annotations

import os
import re
import sys
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SAFE_NAME = re.compile(r"^[A-Za-z0-9._-]{1,128}$")
MEDIA_TYPES = {
    ".m4a": "audio/mp4",
    ".mp4": "audio/mp4",
    ".m4v": "audio/mp4",
    ".flac": "audio/flac",
    ".mp3": "audio/mpeg",
    ".aac": "audio/aac",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
}


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    media = None

    def log_message(self, fmt, *args):
        pass

    def do_HEAD(self):
        self._serve(head=True)

    def do_GET(self):
        self._serve(head=False)

    def _serve(self, head=False):
        name = os.path.basename(urllib.parse.unquote(urllib.parse.urlparse(self.path).path))
        if not SAFE_NAME.match(name):
            return self.send_error(404)
        path = self.media.resolve(name)
        if not path:
            return self.send_error(404)
        try:
            size = os.path.getsize(path)
            fh = open(path, "rb")
        except OSError:
            return self.send_error(404)
        with fh:
            start, end, partial = 0, size - 1, False
            header = (self.headers.get("Range") or "").strip()
            match = re.match(r"bytes=(\d*)-(\d*)$", header)
            if match and (match.group(1) or match.group(2)):
                if match.group(1):
                    start = int(match.group(1))
                if match.group(2):
                    end = min(int(match.group(2)), size - 1)
                if start >= size:
                    self.send_response(416)
                    self.send_header("Content-Range", "bytes */%d" % size)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                partial = True
            length = end - start + 1
            self.send_response(206 if partial else 200)
            self.send_header("Content-Type", MEDIA_TYPES.get(os.path.splitext(name)[1].lower(), "application/octet-stream"))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(length))
            if partial:
                self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
            self.end_headers()
            if head:
                return
            fh.seek(start)
            remaining = length
            while remaining > 0:
                chunk = fh.read(min(65536, remaining))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except Exception:
                    break
                remaining -= len(chunk)


class _Server(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionResetError, BrokenPipeError, TimeoutError)):
            return
        super().handle_error(request, client_address)


class MediaServer:
    """Serve files from one directory on 127.0.0.1:<port>."""

    def __init__(self, directory: str, host: str = "127.0.0.1", port: int = 8081):
        self.roots = []
        self.add_root(directory)
        handler = type("Handler", (_Handler,), {"media": self})
        self.server = _Server((host, port), handler)
        self.host = host
        self.port = port

    def add_root(self, directory: str) -> str:
        """Register an extra directory plugins may serve files from."""
        directory = os.path.abspath(directory)
        os.makedirs(directory, exist_ok=True)
        if directory not in self.roots:
            self.roots.append(directory)
        return directory

    def resolve(self, filename: str) -> str | None:
        for root in self.roots:
            path = os.path.join(root, filename)
            if os.path.isfile(path):
                return path
        return None

    def url(self, filename: str) -> str:
        return "http://%s:%d/%s" % (self.host, self.port, urllib.parse.quote(filename))

    def start(self) -> "MediaServer":
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return self

    def stop(self) -> None:
        self.server.shutdown()
