#!/usr/bin/env python3
"""Validate an exported Apple Music cookies file and print one JSON line.

Usage: check_auth.py /path/to/cookies.txt
Requires gamdl in the interpreter that runs it (use the gamdl venv).
"""
import asyncio
import json
import sys
import time


async def main(path):
    from gamdl.api import AppleMusicApi

    try:
        api = await AppleMusicApi.from_cookies(path)
    except Exception as exc:  # noqa: BLE001 - surfaced to the panel
        print(json.dumps({"ok": False, "error": str(exc)[:300]}, ensure_ascii=False))
        return
    async with api:
        attrs = {}
        try:
            data = (api.account_info or {}).get("data") or []
            if data:
                attrs = data[0].get("attributes") or {}
        except Exception:
            attrs = {}
        print(json.dumps({
            "ok": True,
            "storefront": api.storefront,
            "subscription": bool(api.active_subscription),
            "name": attrs.get("displayName") or attrs.get("username") or "",
            "checked": int(time.time()),
        }, ensure_ascii=False))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("usage: check_auth.py <cookies.txt>")
    asyncio.run(main(sys.argv[1]))
