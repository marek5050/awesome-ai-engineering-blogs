"""Scrape https://shopify.engineering/authors/shopify-engineering and emit
an RSS 2.0 feed.

The page is a fully client-rendered Remix app; the static HTML has no
article markup. Remix exposes the same loader data under `.data`, which
returns a turbo-stream JSON payload — a flat array where dict keys
`_N` reference array index N (which holds the actual key name), and dict
values are themselves array indices that hold the value. Negative values
(e.g. -5, -7) are sentinels (null/undefined).

We resolve every object with `__typename == "Article"` and pull the
fields we need (handle, title, publishedAt, excerpt, imageUrl).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape

import json
import requests

SOURCE_URL = "https://shopify.engineering/authors/shopify-engineering"
DATA_URL = f"{SOURCE_URL}.data"
ARTICLE_BASE = "https://shopify.engineering/"
OUTPUT_PATH = Path("feeds/shopify-engineering.xml")
USER_AGENT = (
    "Mozilla/5.0 (compatible; awesome-ai-engineering-blogs/1.0; "
    "+https://github.com/marek5050/awesome-ai-engineering-blogs)"
)


@dataclass(frozen=True)
class Item:
    title: str
    link: str
    date: datetime
    summary: str | None

    @property
    def guid(self) -> str:
        return self.link


def resolve(arr: list, value):
    """Follow a turbo-stream index reference to its concrete value."""
    if isinstance(value, int):
        if value < 0:
            return None
        if 0 <= value < len(arr):
            return arr[value]
    return value


def decode_article(arr: list, obj: dict) -> dict[str, object]:
    out: dict[str, object] = {}
    for k, v in obj.items():
        if not (isinstance(k, str) and k.startswith("_")):
            continue
        try:
            key_idx = int(k[1:])
        except ValueError:
            continue
        if not (0 <= key_idx < len(arr)):
            continue
        key = arr[key_idx]
        if not isinstance(key, str):
            continue
        out[key] = resolve(arr, v)
    return out


def find_article_objects(arr: list) -> list[dict]:
    articles: list[dict] = []
    for item in arr:
        if not isinstance(item, dict):
            continue
        decoded = decode_article(arr, item)
        if decoded.get("__typename") == "Article":
            articles.append(decoded)
    return articles


def parse_published(raw) -> datetime | None:
    if not isinstance(raw, str):
        return None
    raw = raw.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def extract_items(payload: str) -> list[Item]:
    arr = json.loads(payload)
    if not isinstance(arr, list):
        return []
    items: dict[str, Item] = {}
    for art in find_article_objects(arr):
        handle = art.get("handle")
        title = art.get("title")
        if not isinstance(handle, str) or not isinstance(title, str):
            continue
        date = parse_published(art.get("publishedAt"))
        if date is None:
            continue
        link = ARTICLE_BASE + handle.lstrip("/")
        excerpt = art.get("excerpt")
        summary = excerpt if isinstance(excerpt, str) and excerpt.strip() else None
        items.setdefault(link, Item(title=title.strip(), link=link, date=date, summary=summary))
    return sorted(items.values(), key=lambda i: i.date, reverse=True)


def build_rss(items: list[Item], *, now: datetime) -> str:
    last_build = format_datetime(now)
    parts: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
        "  <channel>",
        "    <title>Shopify Engineering</title>",
        f"    <link>{escape(SOURCE_URL)}</link>",
        "    <description>Posts authored by Shopify Engineering on shopify.engineering.</description>",
        "    <language>en-us</language>",
        f"    <lastBuildDate>{last_build}</lastBuildDate>",
        '    <atom:link href="https://raw.githubusercontent.com/marek5050/awesome-ai-engineering-blogs/main/feeds/shopify-engineering.xml" rel="self" type="application/rss+xml" />',
        "    <generator>awesome-ai-engineering-blogs</generator>",
    ]
    for item in items:
        parts.append("    <item>")
        parts.append(f"      <title>{escape(item.title)}</title>")
        parts.append(f"      <link>{escape(item.link)}</link>")
        parts.append(f"      <guid isPermaLink=\"true\">{escape(item.guid)}</guid>")
        parts.append(f"      <pubDate>{format_datetime(item.date)}</pubDate>")
        if item.summary:
            parts.append(f"      <description>{escape(item.summary)}</description>")
        parts.append("    </item>")
    parts.append("  </channel>")
    parts.append("</rss>")
    parts.append("")
    return "\n".join(parts)


def main() -> int:
    resp = requests.get(DATA_URL, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"

    items = extract_items(resp.text)
    if not items:
        print("ERROR: no items parsed — site layout likely changed.", file=sys.stderr)
        return 1

    now = datetime.now(timezone.utc).replace(microsecond=0)
    rss = build_rss(items, now=now)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(rss, encoding="utf-8")
    print(f"Wrote {len(items)} items to {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())