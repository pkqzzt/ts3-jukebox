"""Apple Music plugin (powered by gamdl).

Search uses Apple's public iTunes Search API, which needs no login and covers
the hk/tw/us storefronts. Playback needs DRM-free local files, so gamdl (with
an Apple Music account) downloads and decrypts the track, and the panel serves
that file to the bot over its local media server.

Storefront note: search hits belong to hk/tw/us while the account usually lives
in another storefront. Tracks that are not licensed in the account storefront
report "Media is unavailable in this storefront"; we then map the song onto the
account storefront by name/artist/album and retry once.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from .base import Plugin, PluginError

MEDIA_EXT = (".m4a", ".mp4", ".m4v", ".flac", ".mp3", ".aac", ".wav")
SEARCH_TTL = 300


class AppleMusicPlugin(Plugin):
    id = "applemusic"
    title = "Apple Music"

    def __init__(self, conf, app_dir):
        super().__init__(conf, app_dir)
        self.gamdl = str(self.conf.get("gamdl") or "gamdl")
        self.python = str(self.conf.get("python") or "python3")
        self.gamdl_config = self._abs(self.conf.get("gamdl_config"), "data/gamdl.yml")
        self.cookies = self._abs(self.conf.get("cookies"), "data/cookies.txt")
        self.checker = self._abs(self.conf.get("checker"), "scripts/apple/check_auth.py")
        self.finder = self._abs(self.conf.get("finder"), "scripts/apple/find_track.py")
        self.status_file = self._abs(self.conf.get("status_file"), "data/apple_status.json")
        self.cache = self._abs(self.conf.get("cache"), "data/applemusic")
        self.log = self._abs(self.conf.get("log"), "data/apple_download.log")
        self.max_files = int(self.conf.get("max_files") or 400)
        self.max_bytes = int(float(self.conf.get("max_gigabytes") or 4) * 1024 ** 3)
        self._lock = threading.Lock()
        self._search_cache = {}
        self._search_lock = threading.Lock()

    def _abs(self, value, default):
        value = value or default
        value = os.path.expanduser(str(value))
        return value if os.path.isabs(value) else os.path.join(self.app_dir, value)

    # -- status ------------------------------------------------------------
    def configured(self):
        try:
            return os.path.getsize(self.cookies) > 40
        except OSError:
            return False

    def status(self):
        out = {"configured": self.configured(), "ok": False}
        try:
            with open(self.status_file, encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict) and data.get("ok"):
                out.update(data)
                return out
        except Exception:
            pass
        out["error"] = "cookies 未校验" if out["configured"] else "未导入 cookies"
        return out

    def storefront(self):
        value = str(self.status().get("storefront") or "us").strip().lower()
        return value if re.fullmatch(r"[a-z]{2}", value) else "us"

    def ready(self):
        status = self.status()
        if not status.get("configured"):
            return False, "未导入 Apple Music cookies"
        if not status.get("ok"):
            return False, str(status.get("error") or "cookies 校验失败")
        return True, ""

    def check_auth(self):
        if not self.configured():
            return {"ok": False, "error": "未导入 cookies"}
        try:
            proc = subprocess.run([self.python, self.checker, self.cookies],
                                  stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, timeout=120)
        except Exception as exc:
            return {"ok": False, "error": "校验失败: %s" % exc}
        raw = (proc.stdout or b"").decode("utf-8", "replace").strip()
        try:
            data = json.loads(raw.splitlines()[-1]) if raw else {}
        except Exception:
            data = {"ok": False, "error": "cookies 校验输出无法解析"}
        if data.get("ok"):
            data["checked"] = int(time.time())
            try:
                with open(self.status_file, "w", encoding="utf-8") as fh:
                    json.dump(data, fh, ensure_ascii=False)
            except Exception:
                pass
        return data

    # -- search ------------------------------------------------------------
    def search(self, query, limit=20):
        term = (query or "").strip()
        if not term:
            return []
        key = term.lower()
        now = time.time()
        with self._search_lock:
            hit = self._search_cache.get(key)
            if hit and now - hit[0] < SEARCH_TTL:
                return hit[1][:limit]

        with ThreadPoolExecutor(max_workers=3) as pool:
            pages = list(pool.map(lambda country: self._fetch_storefront(term, country), ("hk", "tw", "us")))

        found, seen_ids, seen_keys = [], set(), set()
        for rows in pages:
            for row in rows:
                track_id = row.get("trackId")
                if not track_id or track_id in seen_ids:
                    continue
                if row.get("kind") and row.get("kind") != "song":
                    continue
                dedupe = (str(row.get("trackName") or "").strip().lower(),
                          str(row.get("artistName") or "").strip().lower())
                if dedupe in seen_keys:
                    continue
                seen_ids.add(track_id)
                seen_keys.add(dedupe)
                art = row.get("artworkUrl100") or ""
                art = art.replace("100x100bb", "600x600bb").replace("100x100", "600x600")
                found.append({
                    "source": self.id,
                    "id": str(track_id),
                    "name": row.get("trackName") or "",
                    "artist": row.get("artistName") or "",
                    "album": row.get("collectionName") or "",
                    "cover": art,
                    "duration": int(row.get("trackTimeMillis") or 0),
                    "url": row.get("trackViewUrl") or "",
                    "storefront": row.get("_storefront") or "",
                })
                if len(found) >= 50:
                    break
        with self._search_lock:
            self._search_cache[key] = (now, found)
        return found[:limit]

    def _fetch_storefront(self, term, country):
        """Fetch one storefront page; failures degrade to an empty list."""
        query = urllib.parse.urlencode({
            "term": term, "country": country, "media": "music",
            "entity": "song", "limit": 50, "lang": "zh_CN",
        })
        try:
            req = urllib.request.Request("https://itunes.apple.com/search?" + query,
                                         headers={"User-Agent": "ts3-jukebox"})
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read().decode("utf-8", "replace"))
            rows = data.get("results") or []
            for row in rows:
                row["_storefront"] = country
            return rows
        except Exception:
            return []

    # -- playback ----------------------------------------------------------
    def validate(self, track):
        ready, hint = self.ready()
        if not ready:
            return "Apple Music 不可用：%s" % hint
        if not str(track.get("id") or "").isdigit():
            return "非法的 Apple Music 曲目 ID"
        return None

    def prefetch(self, track, media):
        try:
            self._ensure(track, media)
        except Exception:
            pass

    def prepare(self, track, media):
        path = self._ensure(track, media)
        return media.url(os.path.basename(path))

    # -- internals ---------------------------------------------------------
    def _cache_path(self, track_id):
        return os.path.join(self.cache, "%s.m4a" % track_id)

    def _cached(self, track_id):
        path = self._cache_path(track_id)
        try:
            if os.path.getsize(path) > 4096:
                os.utime(path, None)
                return path
        except OSError:
            pass
        return None

    def _ensure(self, track, media):
        track_id = str(track.get("id") or "").strip()
        if not re.fullmatch(r"\d+", track_id):
            raise PluginError("非法的 Apple Music 曲目 ID")
        media.add_root(self.cache)
        path = self._cached(track_id)
        if path:
            return path
        ready, hint = self.ready()
        if not ready:
            raise PluginError("Apple Music 不可用：%s" % hint)
        with self._lock:
            path = self._cached(track_id)
            if path:
                return path
            path = self._cache_path(track_id)
            os.makedirs(self.cache, exist_ok=True)
            tmp = tempfile.mkdtemp(prefix="dl-", dir=self.cache)
            try:
                urls = []
                ref = str(track.get("url") or "").strip()
                if ref.startswith("https://music.apple.com"):
                    urls.append(ref)
                primary = "https://music.apple.com/%s/song/%s" % (self.storefront(), track_id)
                if primary not in urls:
                    urls.append(primary)
                last_error = ""
                for url in urls:
                    ok, output = self._download(url, tmp)
                    source = _pick(tmp)
                    if ok and source:
                        os.replace(source, path)
                        self._prune()
                        return path
                    last_error = _tail(output) or "gamdl 退出码异常"
                    _clean(tmp)
                mapped = self._find_in_storefront(track)
                if mapped:
                    ok, output = self._download(
                        "https://music.apple.com/%s/song/%s" % (self.storefront(), mapped["id"]), tmp)
                    source = _pick(tmp)
                    if ok and source:
                        os.replace(source, path)
                        self._prune()
                        return path
                    last_error = _tail(output) or last_error
                    _clean(tmp)
                raise PluginError(last_error)
            finally:
                shutil.rmtree(tmp, ignore_errors=True)

    def _download(self, url, outdir):
        cmd = [self.gamdl, "--config", self.gamdl_config, "rip", url,
               "--output-dir", outdir, "--no-progress", "--no-database", "--overwrite"]
        started = time.time()
        try:
            proc = subprocess.run(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                  stderr=subprocess.STDOUT, timeout=int(self.conf.get("timeout") or 300))
            text = (proc.stdout or b"").decode("utf-8", "replace")
            code = proc.returncode
        except subprocess.TimeoutExpired:
            text, code = "gamdl 下载超时", 124
        except Exception as exc:
            text, code = "gamdl 启动失败: %s" % exc, 125
        try:
            os.makedirs(os.path.dirname(self.log), exist_ok=True)
            with open(self.log, "a", encoding="utf-8") as fh:
                fh.write("\n=== %s  %s  (%.1fs, exit %s)\n%s\n" % (
                    time.strftime("%Y-%m-%d %H:%M:%S"), url, time.time() - started, code, text[-4000:]))
        except Exception:
            pass
        return code == 0, text

    def _find_in_storefront(self, track):
        name = str(track.get("name") or "").strip()
        if not name:
            return None
        args = [self.python, self.finder, name, str(track.get("artist") or ""),
                str(track.get("album") or ""), self.cookies]
        try:
            proc = subprocess.run(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, timeout=120)
            raw = (proc.stdout or b"").decode("utf-8", "replace").strip()
            data = json.loads(raw.splitlines()[-1]) if raw else {}
            return data if data.get("ok") else None
        except Exception:
            return None

    def _prune(self):
        try:
            entries = []
            for name in os.listdir(self.cache):
                if not name.lower().endswith(MEDIA_EXT):
                    continue
                path = os.path.join(self.cache, name)
                if os.path.isfile(path):
                    entries.append((os.path.getmtime(path), os.path.getsize(path), path))
            total = sum(item[1] for item in entries)
            if len(entries) <= self.max_files and total <= self.max_bytes:
                return
            for _mtime, size, path in sorted(entries):
                try:
                    os.remove(path)
                    entries = [e for e in entries if e[2] != path]
                    total -= size
                except OSError:
                    pass
                if len(entries) <= self.max_files and total <= self.max_bytes:
                    break
        except Exception:
            pass


def _pick(root):
    best, best_size = None, -1
    for dirpath, _dirs, files in os.walk(root):
        for name in files:
            if name.lower().endswith(MEDIA_EXT):
                path = os.path.join(dirpath, name)
                try:
                    size = os.path.getsize(path)
                except OSError:
                    continue
                if size > best_size:
                    best, best_size = path, size
    return best


def _clean(root):
    for name in os.listdir(root):
        path = os.path.join(root, name)
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        else:
            try:
                os.remove(path)
            except OSError:
                pass


def _tail(text):
    lines = [ln.strip() for ln in (text or "").splitlines() if ln.strip()]
    for line in reversed(lines):
        low = line.lower()
        if "✗" in line or "error" in low or "失败" in line or "reject" in low or "unavailable" in low:
            return line.replace("✗", "").strip()[:200]
    return lines[-1][:200] if lines else ""
