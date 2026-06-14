"""Scrape https://ai.meta.com/blog/ and emit an RSS 2.0 feed.

The page is server-rendered with obfuscated class names. Each post card
contains, in order:
  - <h4> category (e.g. "Computer Vision")
  - <h4> title
  - <p>  description
  - <p>  date like "December 16, 2025"
  - <a href="https://ai.meta.com/blog/<slug>/"> Learn More </a>

We anchor on the per-post <a> link and walk up to the nearest ancestor that
also contains the title and date, then read the fields by position.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import format_datetime
from pathlib import Path
from xml.sax.saxutils import escape

import requests
from bs4 import BeautifulSoup, Tag

SOURCE_URL = "https://ai.meta.com/blog/"
OUTPUT_PATH = Path("feeds/meta-ai.xml")
USER_AGENT = (
    "Mozilla/5.0 (compatible; awesome-ai-engineering-blogs/1.0; "
    "+https://github.com/marek5050/awesome-ai-engineering-blogs)"
)

LINK_RE = re.compile(r"^https://ai\.meta\.com/blog/[a-z0-9][a-z0-9-]*/?$")
DATE_RE = re.compile(
    r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},\s+\d{4}$"
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
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
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


def find_date_node(scope: Tag, skip: set[int] | None = None) -> Tag | None:
    for el in scope.find_all(["p", "div", "span", "time"]):
        if skip and id(el) in skip:
            continue
        if DATE_RE.match(el.get_text(strip=True)):
            return el
    return None


def collect_blog_hrefs(scope: Tag) -> set[str]:
    out: set[str] = set()
    for a in scope.find_all("a", href=True):
        href = str(a.get("href", "")).rstrip("/") + "/"
        if LINK_RE.match(href):
            out.add(href)
    return out


def find_card(anchor: Tag, own_href: str) -> Tag | None:
    """Largest ancestor whose blog-link set is exactly {own_href}. That
    captures the full card (title, category, date, description) while still
    excluding sibling cards."""
    best: Tag | None = None
    node: Tag | None = anchor
    for _ in range(20):
        node = node.parent
        if node is None or node.name is None:
            break
        hrefs = collect_blog_hrefs(node)
        if hrefs - {own_href}:
            break
        best = node
    return best


def extract_items(html: str) -> list[Item]:
    soup = BeautifulSoup(html, "html.parser")
    items: dict[str, Item] = {}

    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"]).rstrip("/") + "/"
        if not LINK_RE.match(href):
            continue
        if href in items:
            continue
        card = find_card(anchor, href)
        if card is None:
            continue

        date_node = find_date_node(card)
        if date_node is None:
            continue
        date = parse_date(date_node.get_text(strip=True))
        if date is None:
            continue

        heading_texts = [text_or_none(h) or "" for h in card.find_all(["h1", "h2", "h3", "h4"])]
        heading_texts = [t for t in heading_texts if t]
        # Title is the longest heading; remaining short ones are categories.
        title: str | None = None
        category: str | None = None
        if heading_texts:
            title = max(heading_texts, key=len)
            shorter = [t for t in heading_texts if t is not title]
            if shorter:
                category = shorter[0]

        # Featured cards have no headings; pick the most descriptive anchor
        # in the card with the same href.
        if not title:
            candidates: list[str] = []
            for a in card.find_all("a", href=True):
                if str(a.get("href", "")).rstrip("/") + "/" != href:
                    continue
                text = text_or_none(a)
                if text:
                    candidates.append(text)
                for attr in ("title", "aria-label"):
                    val = a.get(attr)
                    if val:
                        candidates.append(str(val))
            candidates = [c for c in candidates if c.lower() not in {"featured", "learn more"}]
            if candidates:
                title = max(candidates, key=len)
        if not title:
            continue
        title = title.strip()
        # Some featured cards expose the title via an aria-label like
        # "Read <title>" or "Watch <title>" — strip the CTA verb.
        title = re.sub(r"^(Read|Watch|Listen to|See)\s+", "", title)

        # Description: the longest <p> in the card that isn't the date.
        summary: str | None = None
        candidates_p: list[str] = []
        for p in card.find_all("p"):
            if p is date_node:
                continue
            text = p.get_text(" ", strip=True)
            if not text or text == title or text == category:
                continue
            if len(text) < 30:
                continue
            candidates_p.append(text)
        if candidates_p:
            summary = max(candidates_p, key=len)

        items[href] = Item(
            title=title,
            link=href,
            date=date,
            category=category,
            summary=summary,
        )

    return sorted(items.values(), key=lambda i: i.date, reverse=True)


def build_rss(items: list[Item], *, now: datetime) -> str:
    last_build = format_datetime(now)
    parts: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
        "  <channel>",
        "    <title>Meta AI</title>",
        f"    <link>{escape(SOURCE_URL)}</link>",
        "    <description>Posts from the Meta AI blog.</description>",
        "    <language>en-us</language>",
        f"    <lastBuildDate>{last_build}</lastBuildDate>",
        '    <atom:link href="https://raw.githubusercontent.com/marek5050/awesome-ai-engineering-blogs/main/feeds/meta-ai.xml" rel="self" type="application/rss+xml" />',
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