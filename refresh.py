#!/usr/bin/env python3
"""Build data.json from public discovery RSS feeds.

This first connector is for discovery only. It does not claim to measure
funding totals, sales, likes, or inventory unless an authorized source exposes
those fields. Feed links always point readers to the original publisher.
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "sources.json"
OUTPUT_PATH = ROOT / "data.json"
SEOUL = timezone(timedelta(hours=9), "Asia/Seoul")
USER_AGENT = "FandomRadar/0.1 (+public-feed discovery; contact: site operator)"
TIMEOUT_SECONDS = 20
IMAGE_TIMEOUT_SECONDS = 8


class MetadataParser(HTMLParser):
    """Extract an Open Graph image from a public article page."""

    def __init__(self) -> None:
        super().__init__()
        self.image: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "meta":
            return
        values = {key.lower(): value for key, value in attrs if value}
        key = (values.get("property") or values.get("name") or "").lower()
        if key in {"og:image", "twitter:image"} and values.get("content") and not self.image:
            self.image = values["content"]


def fetch_image(url: str) -> str | None:
    """Read a publisher's public OG image; never download or rehost the image."""
    try:
        if urllib.parse.urlparse(url).hostname in {"news.google.com", "www.google.com"}:
            # Google's wrapper page exposes its generic logo as og:image, not the story art.
            return None
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; FandomRadar/1.0; +https://down-cyber.github.io/fandom-radar/)"},
        )
        with urllib.request.urlopen(request, timeout=IMAGE_TIMEOUT_SECONDS) as response:
            content_type = response.headers.get("Content-Type", "")
            if "html" not in content_type.lower():
                return None
            parser = MetadataParser()
            parser.feed(response.read(1_500_000).decode("utf-8", "replace"))
            image = parser.image
            if not image:
                return None
            resolved = urllib.parse.urljoin(response.geturl(), image)
            parsed = urllib.parse.urlparse(resolved)
            return resolved if parsed.scheme in {"http", "https"} else None
    except (OSError, urllib.error.URLError, ValueError):
        return None


def enrich_images(items: list[dict[str, Any]]) -> None:
    """Fetch card thumbnails concurrently while keeping the daily run bounded."""
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(fetch_image, item["url"]): item for item in items}
        for future in as_completed(futures):
            item = futures[future]
            try:
                item["image"] = future.result()
            except Exception as error:
                print(f"Image metadata unavailable for {item['id']}: {error}", file=sys.stderr)
                item["image"] = None


def clean_text(value: str | None, limit: int = 240) -> str:
    value = value or ""
    value = re.sub(r"<[^>]+>", " ", value)
    value = urllib.parse.unquote(value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:limit]


def published_at(item: ET.Element) -> datetime | None:
    raw = item.findtext("pubDate")
    if not raw:
        return None
    try:
        parsed = parsedate_to_datetime(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(SEOUL)
    except (TypeError, ValueError, OverflowError):
        return None


def fetch_feed(source: dict[str, Any], max_items: int, max_age_days: int) -> list[dict[str, Any]]:
    query = urllib.parse.quote(source["query"], safe="")
    url = (
        "https://news.google.com/rss/search?q="
        f"{query}&hl=ko&gl=KR&ceid=KR%3Ako"
    )
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        payload = response.read(4_000_000)

    root = ET.fromstring(payload)
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    results: list[dict[str, Any]] = []
    for item in root.findall("./channel/item"):
        title = clean_text(item.findtext("title"), 180)
        link = (item.findtext("link") or "").strip()
        if not title or not link:
            continue
        published = published_at(item)
        if published and published.astimezone(timezone.utc) < cutoff:
            continue
        description = clean_text(item.findtext("description"), 260)
        image = None
        for element in item.iter():
            if element.tag.rsplit("}", 1)[-1].lower() in {"thumbnail", "content"}:
                candidate = element.attrib.get("url")
                if candidate and candidate.startswith(("https://", "http://")):
                    image = candidate
                    break
        results.append(
            {
                "id": f"{source['id']}:{link}",
                "channel": source["channel"],
                "type": source["type"],
                "title": title,
                "summary": description,
                "url": link,
                "image": image,
                "publishedAt": published.isoformat() if published else None,
                "source": "Google News RSS discovery",
                "collectedAt": datetime.now(SEOUL).isoformat(),
                "metrics": {"fundingPercent": None, "supporters": None, "price": None},
                "signal": "신규 소식",
            }
        )
        if len(results) >= max_items:
            break
    return results


def main() -> int:
    with CONFIG_PATH.open(encoding="utf-8") as file:
        config = json.load(file)

    items: list[dict[str, Any]] = []
    statuses: list[dict[str, str]] = []
    for source in config["sources"]:
        try:
            found = fetch_feed(
                source,
                int(config.get("max_items_per_source", 12)),
                int(config.get("max_age_days", 30)),
            )
            items.extend(found)
            statuses.append({"channel": source["channel"], "status": "ok", "count": str(len(found))})
        except (OSError, urllib.error.URLError, ET.ParseError, KeyError, ValueError) as error:
            print(f"Feed failed for {source.get('id', 'unknown')}: {error}", file=sys.stderr)
            statuses.append({"channel": source.get("channel", "unknown"), "status": "error", "count": "0"})
        time.sleep(1)

    # Deduplicate across overlapping search feeds, retaining the first channel match.
    unique: dict[str, dict[str, Any]] = {}
    for item in items:
        unique.setdefault(item["url"], item)
    items = sorted(
        unique.values(),
        key=lambda item: item.get("publishedAt") or "",
        reverse=True,
    )
    enrich_images(items)

    result = {
        "schemaVersion": 1,
        "timezone": "Asia/Seoul",
        "updatedAt": datetime.now(SEOUL).isoformat(timespec="seconds"),
        "updateBasis": "Daily public-feed discovery; article thumbnails link to publisher-hosted images and metrics appear only when a source exposes them.",
        "items": items,
        "sourceStatus": statuses,
    }
    OUTPUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(items)} discovery items to {OUTPUT_PATH}")
    # Fail the run only if every configured feed failed; partial data is still useful.
    if statuses and all(entry["status"] == "error" for entry in statuses):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
