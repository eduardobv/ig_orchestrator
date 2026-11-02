"""POC: descargar posts/reels de Instagram sin el bot, con /api/v1/media/<id>/info/.

Uso:
    set IG_SESSIONID=...   (cookie sessionid de Chrome, NO guardar en el repo)
    set IG_CSRFTOKEN=...   (opcional pero recomendable)
    python poc_media_info.py https://www.instagram.com/p/DJryedPJmGk/ [carpeta_salida]

Aislado: no importa nada de ig_orchestrator.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import requests

ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
IG_APP_ID = "936619743392459"  # constante de la web de Instagram
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36"
)


def shortcode_from_url(url: str) -> str:
    m = re.search(r"instagram\.com/(?:[^/]+/)?(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)", url)
    if not m:
        raise ValueError(f"URL no es post/reel: {url}")
    return m.group(1)


def shortcode_to_media_id(code: str) -> int:
    # Los shortcodes nuevos pueden traer prefijo extra; los clásicos son 11 caracteres.
    n = 0
    for c in code:
        n = n * 64 + ALPHABET.index(c)
    return n


def fetch_info(media_id: int, sessionid: str, csrftoken: str | None) -> dict:
    cookies = {"sessionid": sessionid}
    if csrftoken:
        cookies["csrftoken"] = csrftoken
    r = requests.get(
        f"https://i.instagram.com/api/v1/media/{media_id}/info/",
        headers={
            "accept": "*/*",
            "origin": "https://www.instagram.com",
            "referer": "https://www.instagram.com/",
            "user-agent": UA,
            "x-ig-app-id": IG_APP_ID,
        },
        cookies=cookies,
        timeout=30,
    )
    print(f"info -> HTTP {r.status_code}")
    r.raise_for_status()
    return r.json()


def best(item: dict) -> tuple[str, str]:
    """Devuelve (url, extensión) de la mejor calidad del item (vídeo > imagen)."""
    if item.get("video_versions"):
        v = max(item["video_versions"], key=lambda x: x.get("width", 0) * x.get("height", 0))
        return v["url"], "mp4"
    c = max(
        item["image_versions2"]["candidates"],
        key=lambda x: x.get("width", 0) * x.get("height", 0),
    )
    return c["url"], "jpg"


def items_of(media: dict) -> list[tuple[str, dict]]:
    """(nombre de archivo, item) por cada objeto del post. pk == carousel_media_ids."""
    if media.get("carousel_media"):
        return [(str(it["pk"]), it) for it in media["carousel_media"]]
    return [(str(media["pk"]), media)]


def main() -> int:
    url = sys.argv[1]
    out = Path(sys.argv[2] if len(sys.argv) > 2 else "out")
    sessionid = os.environ["IG_SESSIONID"]
    code = shortcode_from_url(url)
    media_id = shortcode_to_media_id(code)
    print(f"shortcode={code} media_id={media_id}")

    data = fetch_info(media_id, sessionid, os.environ.get("IG_CSRFTOKEN"))
    media = data["items"][0]
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{code}_info.json").write_text(json.dumps(data, indent=1), encoding="utf-8")
    print("carousel_media_ids:", media.get("carousel_media_ids"))

    for name, item in items_of(media):
        u, ext = best(item)
        r = requests.get(u, headers={"user-agent": UA}, timeout=60)  # CDN: sin cookies
        r.raise_for_status()
        dest = out / f"{name}.{ext}"
        dest.write_bytes(r.content)
        print(f"  {dest.name}  {len(r.content)} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
