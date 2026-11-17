#!/usr/bin/env python3
"""Parse an Apple Music playlist link into track metadata.

Usage: playlist.py <playlist-url> <cookies.txt>
Prints one JSON line: {"ok": true, "title": ..., "tracks": [...]}
"""
import asyncio
import json
import re
import sys

MAX_TRACKS = 300
# Catalog ids look like pl.0123456789abcdef0123456789abcdef, personal/shared
# playlists look like pl.u-r2yBDbkFRzBlqkL (hyphen after "u").
URL_RE = re.compile(r"music\.apple\.com/(?:([a-z]{2})/)?playlist/[^/?#]+/(pl\.[A-Za-z0-9.\-]+)")


def cover_url(art):
    url = (art or {}).get("url") if isinstance(art, dict) else ""
    if not url:
        return ""
    return url.replace("{w}x{h}", "600x600")


async def run(url, cookies):
    from gamdl.api import AppleMusicApi

    match = URL_RE.search(url or "")
    if not match:
        return {"ok": False, "error": "不是有效的 Apple Music 歌单链接"}
    storefront = match.group(1)
    playlist_id = match.group(2)

    api = await AppleMusicApi.from_cookies(cookies, storefront=storefront)
    async with api:
        meta = await api.get_playlist(playlist_id, limit_tracks=1)
        data = (meta.get("data") or [{}])[0]
        attrs = data.get("attributes") or {}
        tracks = []
        async for item in api.iter_playlist_tracks(playlist_id):
            if item.get("type") not in ("songs", "library-songs"):
                continue
            song = item.get("attributes") or {}
            track_id = item.get("id")
            if not track_id:
                continue
            tracks.append({
                "source": "applemusic",
                "id": str(track_id),
                "name": song.get("name") or "",
                "artist": song.get("artistName") or "",
                "album": song.get("albumName") or "",
                "cover": cover_url(song.get("artwork")),
                "duration": int(song.get("durationInMillis") or 0),
                "url": "https://music.apple.com/%s/song/%s" % (api.storefront, track_id),
                "storefront": api.storefront,
            })
            if len(tracks) >= MAX_TRACKS:
                break
        return {
            "ok": True,
            "source": "applemusic",
            "id": playlist_id,
            "url": url.split("?")[0],
            "storefront": api.storefront,
            "title": attrs.get("name") or playlist_id,
            "artist": attrs.get("curatorName") or "",
            "cover": cover_url(attrs.get("artwork")),
            "tracks": tracks,
            "truncated": len(tracks) >= MAX_TRACKS,
        }


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("usage: playlist.py <playlist-url> <cookies.txt>")
    try:
        result = asyncio.run(run(sys.argv[1], sys.argv[2]))
    except Exception as exc:  # noqa: BLE001
        result = {"ok": False, "error": str(exc)[:300]}
    print(json.dumps(result, ensure_ascii=False))
