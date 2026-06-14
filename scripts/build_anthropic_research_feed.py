"""Scrape https://www.anthropic.com/research and emit an RSS 2.0 feed.

The page is server-rendered Next.js. Items live in two distinct sections:

1. FeaturedGrid — featured blog-style posts that link to /research/<slug>
2. PublicationList — papers that usually link to PDFs / arXiv

Both expose a <time> tag with a human date like "May 7, 2026". An entry is
treated as a post if it has both a <time> and an <a href>.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from urllib.parse import urljoin
from xml.sax.saxutils import escape

import requests
from bs4 import BeautifulSoup, Tag

SOURCE_URL = "https://www.anthropic.com/research"
OUTPUT_PATH = Path("feeds/anthropic-research.xml")
USER_AGENT = (
    "Mozilla/5.0 (compatible; awesome-ai-engineering-blogs/1.0; "
    "+https://github.com/marek5050/awesome-ai-engineering-blogs)"
)


@dataclass(frozen=True)
class Item:
    title: str
    link: str
    date: datetime
    category: str | None
    summary: str | None

    @property
    def guid(self) -> str:
        return self.link


def parse_date(raw: str) -> datetime | None:
    raw = raw.strip()
    for fmt in ("%b %d, %Y", "%B %d, %Y"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def text_or_none(node: Tag | None) -> str | None:
    if node is None:
        return None
    text = node.get_text(" ", strip=True)
    return text or None


def extract_items(html: str) -> list[Item]:
    soup = BeautifulSoup(html, "html.parser")
    items: dict[str, Item] = {}

    for time_tag in soup.find_all("time"):
        date = parse_date(time_tag.get_text(strip=True))
        if date is None:
            continue

        # Walk up to the nearest ancestor anchor (some templates wrap content
        # in <a>, others put the <a> as a sibling of the meta block).
        container = time_tag
        anchor: Tag | None = None
        for _ in range(8):
            container = container.parent
            if container is None:
                break
            if container.name == "a" and container.get("href"):
                anchor = container
                break
            anchor = container.find("a", href=True)
            if anchor is not None:
                break
        if anchor is None:
            continue

        href = anchor["href"]
        link = urljoin(SOURCE_URL, href)

        def has_class_substr(needle: str):
            def _match(tag: Tag) -> bool:
                classes = tag.get("class") or []
                return any(needle in c.lower() for c in classes)
            return _match

        title_node = (
            anchor.find(["h1", "h2", "h3"])
            or anchor.find(has_class_substr("title"))
            or (container.find(["h1", "h2", "h3"]) if container else None)
        )
        title = text_or_none(title_node)
        if not title:
            title = anchor.get("aria-label")
        if not title:
            continue

        category_node = anchor.find(has_class_substr("subject"))
        if category_node is None and container is not None:
            for node in container.find_all(class_="caption bold"):
                if node is time_tag:
                    continue
                category_node = node
                break
        category = text_or_none(category_node)

        body_node = anchor.find("p") or (container.find("p") if container else None)
        summary = text_or_none(body_node)

        item = Item(title=title, link=link, date=date, category=category, summary=summary)
        # Dedupe on link; keep the earliest-seen (page renders newest first).
        items.setdefault(item.guid, item)

    return sorted(items.values(), key=lambda i: i.date, reverse=True)


def build_rss(items: list[Item], *, now: datetime) -> str:
    last_build = format_datetime(now)
    parts: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
        "  <channel>",
        "    <title>Anthropic Research</title>",
        f"    <link>{escape(SOURCE_URL)}</link>",
        "    <description>Research posts and publications from Anthropic.</description>",
        "    <language>en-us</language>",
        f"    <lastBuildDate>{last_build}</lastBuildDate>",
        '    <atom:link href="https://raw.githubusercontent.com/marek5050/awesome-ai-engineering-blogs/main/feeds/anthropic-research.xml" rel="self" type="application/rss+xml" />',
        "    <generator>awesome-ai-engineering-blogs</generator>",
    ]
    for item in items:
        parts.append("    <item>")
        parts.append(f"      <title>{escape(item.title)}</title>")
        parts.append(f"      <link>{escape(item.link)}</link>")
        parts.append(f"      <guid isPermaLink=\"true\">{escape(item.guid)}</guid>")
        parts.append(f"      <pubDate>{format_datetime(item.date)}</pubDate>")
        if item.category:
            parts.append(f"      <category>{escape(item.category)}</category>")
        if item.summary:
            parts.append(f"      <description>{escape(item.summary)}</description>")
        parts.append("    </item>")
    parts.append("  </channel>")
    parts.append("</rss>")
    parts.append("")
    return "\n".join(parts)


def main() -> int:
    resp = requests.get(SOURCE_URL, headers={"User-Agent": USER_AGENT}, timeout=30)
    resp.raise_for_status()

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
