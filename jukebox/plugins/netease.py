"""NetEase Cloud Music plugin.

Search and track URLs come from a NetEaseCloudMusicApi instance
(https://github.com/Binaryify/NeteaseCloudMusicApi) listening on localhost.
A MUSIC_U cookie unlocks VIP/high quality streams.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

from .base import Plugin, PluginError

LRC_TIME = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\]")
PLAYLIST_ID = re.compile(r"/playlist/(\d+)|[?&#]id=(\d+)")
PLAYLIST_LIMIT = 300


def playlist_id(url: str):
    """Extract a NetEase playlist id from share links with tracking params."""
    if "playlist" not in (url or ""):
        return None
    match = PLAYLIST_ID.search(url)
    return (match.group(1) or match.group(2)) if match else None


class NeteasePlugin(Plugin):
    id = "netease"
    title = "网易云音乐"

    def __init__(self, conf, app_dir):
        super().__init__(conf, app_dir)
        self.api = str(self.conf.get("api") or "http://127.0.0.1:3000").rstrip("/")
        self.level = str(self.conf.get("level") or "exhigh")
        self.limit = int(self.conf.get("search_limit") or 20)
        cookie = self.conf.get("cookie_file") or "data/netease_cookie.txt"
        self.cookie_file = cookie if os.path.isabs(cookie) else os.path.join(app_dir, cookie)

    def cookie(self) -> str:
        try:
            with open(self.cookie_file, encoding="utf-8") as fh:
                return fh.read().strip()
        except OSError:
            return ""

    def ready(self):
        if not self.cookie():
            return False, "未配置 MUSIC_U cookie，只能搜到不能播放"
        return True, ""

    def _get(self, path, **params):
        cookie = self.cookie()
        if cookie and "cookie" not in params:
            params["cookie"] = "MUSIC_U=" + cookie
        url = self.api + path + "?" + urllib.parse.urlencode(params)
        try:
            with urllib.request.urlopen(url, timeout=25) as resp:
                data = json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", "replace")
            try:
                payload = json.loads(raw)
            except Exception:
                payload = {}
            message = payload.get("message") or payload.get("msg") or ("网易云接口返回 HTTP %s" % exc.code)
            raise PluginError(str(message)) from None
        if isinstance(data, dict) and data.get("code") not in (200, None):
            raise PluginError(str(data.get("message") or data.get("msg") or "网易云接口返回错误"))
        return data

    def search(self, query, limit=20):
        data = self._get("/search", keywords=query, limit=min(max(limit, 1), 50))
        songs = []
        for row in (data.get("result") or {}).get("songs") or []:
            songs.append({
                "source": self.id,
                "id": row["id"],
                "name": row["name"],
                "artist": "/".join(a["name"] for a in row.get("artists") or []),
                "album": (row.get("album") or {}).get("name", ""),
                "cover": (row.get("album") or {}).get("picUrl", ""),
                "duration": row.get("duration", 0),
            })
        try:
            ids = ",".join(str(s["id"]) for s in songs)
            if ids:
                detail = self._get("/song/detail", ids=ids)
                covers = {x["id"]: ((x.get("al") or {}).get("picUrl") or "") for x in detail.get("songs") or []}
                for song in songs:
                    song["cover"] = covers.get(song["id"], song["cover"])
        except Exception:
            pass
        return songs

    def prepare(self, track, media):
        params = {"id": track["id"], "level": self.level}
        cookie = self.cookie()
        if cookie:
            params["cookie"] = "MUSIC_U=" + cookie
        data = self._get("/song/url", **params)
        url = ((data.get("data") or [{}])[0]).get("url")
        if not url:
            raise PluginError("网易云没有返回可播放地址（可能是 VIP / 版权限制）")
        return url


    # -- lyrics ------------------------------------------------------------
    def lyrics(self, track_id):
        """Return [{"t": seconds, "text": line}] parsed from the LRC response."""
        data = self._get("/lyric", id=track_id)
        raw = ((data.get("lrc") or {}).get("lyric") or "").strip()
        if not raw:
            return []
        lines = []
        for row in raw.splitlines():
            match = LRC_TIME.match(row)
            if not match:
                continue
            text = LRC_TIME.sub("", row).strip()
            if not text:
                continue
            lines.append({"t": int(match.group(1)) * 60 + float(match.group(2)), "text": text})
        lines.sort(key=lambda item: item["t"])
        return lines


    # -- playlist ----------------------------------------------------------
    def playlist(self, url):
        pid = playlist_id(url)
        if not pid:
            raise PluginError("不是有效的网易云歌单链接")
        detail = self._get("/playlist/detail", id=pid)
        data = detail.get("playlist") or {}
        if not data:
            raise PluginError("网易云没有返回这个歌单（可能是私密歌单或链接失效）")
        tracks = []
        offset = 0
        while len(tracks) < PLAYLIST_LIMIT:
            page = self._get("/playlist/track/all", id=pid, limit=200, offset=offset)
            rows = page.get("songs") or []
            if not rows:
                break
            for row in rows:
                tracks.append({
                    "source": self.id,
                    "id": row["id"],
                    "name": row["name"],
                    "artist": "/".join(a["name"] for a in row.get("ar") or []),
                    "album": (row.get("al") or {}).get("name", ""),
                    "cover": (row.get("al") or {}).get("picUrl", ""),
                    "duration": row.get("dt", 0),
                })
                if len(tracks) >= PLAYLIST_LIMIT:
                    break
            offset += len(rows)
            if len(rows) < 200:
                break
        return {
            "source": self.id,
            "id": pid,
            "url": "https://music.163.com/playlist?id=" + pid,
            "title": data.get("name") or ("歌单 " + pid),
            "artist": (data.get("creator") or {}).get("nickname", ""),
            "cover": data.get("coverImgUrl", ""),
            "tracks": tracks,
            "truncated": len(tracks) >= PLAYLIST_LIMIT,
        }
