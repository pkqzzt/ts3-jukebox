#!/usr/bin/env python3
"""Find the best matching track inside the account's Apple Music storefront.

Search results come from the hk/tw/us iTunes API, but the Apple Music account
often lives in another storefront (cn, for example) where some songs are
licensed under a different catalog id. This helper maps a song onto the account
storefront so gamdl can download it.

Usage: find_track.py "<name>" "<artist>" "<album>" "<cookies.txt>"
Prints one JSON line: {"ok": true, "id": "...", "score": 0.93, ...}
"""
import asyncio
import difflib
import json
import sys
import unicodedata


def norm(text):
    text = unicodedata.normalize("NFKC", str(text or "")).lower()
    return "".join(ch for ch in text if ch.isalnum())


def ratio(a, b):
    a, b = norm(a), norm(b)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return difflib.SequenceMatcher(None, a, b).ratio()


async def search(term, cookies):
    from gamdl.api import AppleMusicApi

    api = await AppleMusicApi.from_cookies(cookies)
    async with api:
        data = await api.get_search_results(term, types="songs", limit=10)
        songs = ((data.get("results") or {}).get("songs") or {}).get("data") or []
        return api.storefront, songs


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else ""
    artist = sys.argv[2] if len(sys.argv) > 2 else ""
    album = sys.argv[3] if len(sys.argv) > 3 else ""
    cookies = sys.argv[4] if len(sys.argv) > 4 else ""
    if not cookies:
        print(json.dumps({"ok": False, "error": "cookies path missing"}))
        return
    term = " ".join(x for x in (name, artist) if x)
    try:
        storefront, songs = asyncio.run(search(term, cookies))
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(exc)[:200]}, ensure_ascii=False))
        return
    best = None
    for song in songs:
        attrs = song.get("attributes") or {}
        name_score = ratio(name, attrs.get("name"))
        artist_score = ratio(artist, attrs.get("artistName"))
        album_score = ratio(album, attrs.get("albumName")) if album else 0.0
        score = 0.62 * name_score + 0.24 * artist_score + 0.14 * album_score
        if name_score < 0.55:
            continue
        if best is None or score > best["score"]:
            best = {
                "ok": True,
                "id": str(song.get("id")),
                "name": attrs.get("name"),
                "artist": attrs.get("artistName"),
                "album": attrs.get("albumName"),
                "storefront": storefront,
                "score": round(score, 3),
            }
    print(json.dumps(best or {"ok": False, "error": "no match"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
