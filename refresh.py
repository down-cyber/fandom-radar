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
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "sources.json"
OUTPUT_PATH = ROOT / "data.json"
SEOUL = timezone(timedelta(hours=9), "Asia/Seoul")
USER_AGENT = "FandomRadar/0.1 (+public-feed discovery; contact: site operator)"
TIMEOUT_SECONDS = 20


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
        results.append(
            {
                "id": f"{source['id']}:{link}",
                "channel": source["channel"],
                "type": source["type"],
                "title": title,
                "summary": description,
                "url": link,
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

    result = {
        "schemaVersion": 1,
        "timezone": "Asia/Seoul",
        "updatedAt": datetime.now(SEOUL).isoformat(timespec="seconds"),
        "updateBasis": "Daily scheduled public-feed discovery; metrics are only shown when exposed by an authorized source.",
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
