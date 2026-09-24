"""
Live news for Ascent's dashboard Signal strip. Pulls Google News RSS (no API
key) for three topic queries, parses with stdlib, caches in-memory. Fail-soft:
network/parse errors return an empty list + an error note, never raise.
"""
from __future__ import annotations

import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

FEEDS = {
    "robotics": "https://news.google.com/rss/search?q=robotics+automation+controls+engineering&hl=en-US&gl=US&ceid=US:en",
    "ai": "https://news.google.com/rss/search?q=artificial+intelligence+machine+learning&hl=en-US&gl=US&ceid=US:en",
    "az": "https://news.google.com/rss/search?q=Phoenix+Arizona+engineering+hiring+OR+aerospace+OR+defense&hl=en-US&gl=US&ceid=US:en",
}
TTL = 1800  # 30 min
_cache: dict[str, tuple[float, list[dict]]] = {}


def _fetch(topic: str) -> list[dict]:
    url = FEEDS.get(topic)
    if not url:
        return []
    cached = _cache.get(topic)
    now = time.time()
    if cached and now - cached[0] < TTL:
        return cached[1]
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Ascent)"})
    with urllib.request.urlopen(req, timeout=4) as resp:
        root = ET.fromstring(resp.read())
    items = []
    for it in root.findall(".//item")[:12]:
        items.append({
            "title": (it.findtext("title") or "").strip(),
            "link": (it.findtext("link") or "").strip(),
            "published": (it.findtext("pubDate") or "").strip(),
            "source": (it.findtext("source") or "").strip(),
            "topic": topic,
        })
    _cache[topic] = (now, items)
    return items


def _ts(item: dict) -> float:
    try:
        return parsedate_to_datetime(item["published"]).timestamp()
    except (TypeError, ValueError):
        return 0.0


def get_news(topics: list[str]) -> dict:
    out: list[dict] = []
    errors: dict[str, str] = {}
    # Fetch topics concurrently: wall-clock = slowest feed, not the sum. Each
    # _fetch is fail-soft per topic so one dead feed can't sink the others.
    with ThreadPoolExecutor(max_workers=len(topics) or 1) as ex:
        futs = {ex.submit(_fetch, tp): tp for tp in topics}
        for fut in as_completed(futs):
            try:
                out.extend(fut.result())
            except Exception as exc:
                errors[futs[fut]] = str(exc)
    out.sort(key=_ts, reverse=True)
    return {"items": out[:18], "errors": errors}
