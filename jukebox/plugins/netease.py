"""NetEase Cloud Music plugin.

Search and track URLs come from a NetEaseCloudMusicApi instance
(https://github.com/Binaryify/NeteaseCloudMusicApi) listening on localhost.
A MUSIC_U cookie unlocks VIP/high quality streams.
"""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

from .base import Plugin, PluginError


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
        url = self.api + path + "?" + urllib.parse.urlencode(params)
        with urllib.request.urlopen(url, timeout=20) as resp:
            return json.loads(resp.read())

    def search(self, query):
        data = self._get("/search", keywords=query, limit=self.limit)
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
