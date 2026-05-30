#!/usr/bin/env python3
"""
DealRadar data updater.

Commercial MVP goals:
- keep old data when a source fails
- write a visible update report to data/status.json
- make source reliability clear instead of pretending every crawler is equal
"""

import json
import os
import re
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
DEALS_PATH = ROOT / "data" / "structured" / "deals.json"
STATUS_PATH = ROOT / "data" / "status.json"

SOURCE_META = {
    "v2ex": {
        "label": "V2EX",
        "mode": "stable_api",
        "reliability": "stable",
        "note": "官方公开 API，可自动更新回复数。",
    },
    "hacker-news": {
        "label": "Hacker News",
        "mode": "stable_api",
        "reliability": "stable",
        "note": "Firebase 公开 API，可自动更新分数和评论数。",
    },
    "linux.do": {
        "label": "Linux.do",
        "mode": "public_or_cookie_api",
        "reliability": "partial",
        "note": "公开接口可能受限；配置 LINUX_DO_COOKIE 后更稳定。",
    },
    "nodeseek": {
        "label": "NodeSeek",
        "mode": "manual_or_browser",
        "reliability": "manual",
        "note": "当前 Actions 中保留旧值，后续可接 Playwright。",
    },
    "52pojie": {
        "label": "52pojie",
        "mode": "blocked_or_rss",
        "reliability": "manual",
        "note": "当前保留旧值，适合人工核验或 RSS 兜底。",
    },
}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def fetch_json(url, timeout=10, headers=None):
    req_headers = {"User-Agent": "Mozilla/5.0 DealRadar/1.0"}
    if headers:
        req_headers.update(headers)

    req = urllib.request.Request(url, headers=req_headers)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def update_v2ex(deal):
    match = re.search(r"/t/(\d+)", deal.get("url", ""))
    if not match:
        return False, "missing_topic_id"

    data = fetch_json(f"https://www.v2ex.com/api/topics/show.json?id={match.group(1)}")
    if data and isinstance(data, list) and data:
        topic = data[0]
        deal["replies"] = topic.get("replies", deal.get("replies", 0))
        return True, ""
    return False, "empty_response"


def update_hacker_news(deal):
    match = re.search(r"id=(\d+)", deal.get("url", ""))
    if not match:
        return False, "missing_item_id"

    data = fetch_json(f"https://hacker-news.firebaseio.com/v0/item/{match.group(1)}.json")
    if data:
        deal["likes"] = data.get("score", deal.get("likes", 0))
        deal["replies"] = data.get("descendants", deal.get("replies", 0))
        return True, ""
    return False, "empty_response"


def update_linux_do(deal):
    match = re.search(r"/t/(?:topic/)?(\d+)", deal.get("url", ""))
    if not match:
        return False, "missing_topic_id"

    headers = {}
    cookie = os.environ.get("LINUX_DO_COOKIE") or os.environ.get("LINUX_DO_SESSION")
    if cookie:
        headers["Cookie"] = cookie

    data = fetch_json(f"https://linux.do/t/{match.group(1)}.json", headers=headers)
    if data and data.get("views") is not None:
        deal["views"] = data.get("views", deal.get("views", 0))
        deal["likes"] = data.get("like_count", deal.get("likes", 0))
        deal["replies"] = data.get("posts_count", deal.get("replies", 0))
        deal["last_posted_at"] = data.get("last_posted_at", deal.get("last_posted_at", ""))
        return True, ""
    return False, "empty_or_restricted_response"


def build_source_stats(deals):
    stats = {}
    for deal in deals:
        source = deal.get("source", "unknown")
        meta = SOURCE_META.get(source, {})
        stats.setdefault(
            source,
            {
                "source": source,
                "label": meta.get("label", source),
                "mode": meta.get("mode", "unknown"),
                "reliability": meta.get("reliability", "unknown"),
                "note": meta.get("note", ""),
                "total": 0,
                "updated": 0,
                "failed": 0,
                "skipped": 0,
                "last_error": "",
            },
        )
        stats[source]["total"] += 1
    return stats


def write_status(raw, source_stats, updated, failed, skipped):
    status = {
        "updated_at": raw.get("updated_at", now_iso()),
        "generated_at": now_iso(),
        "generated_by": "dealradar-auto-updater",
        "total_deals": len(raw.get("deals", [])),
        "updated_deals": updated,
        "failed_deals": failed,
        "skipped_deals": skipped,
        "freshness": "fresh" if updated else "using_cached_data",
        "sources": sorted(source_stats.values(), key=lambda item: item["source"]),
        "notes": [
            "自动源失败时保留旧数据，不中断部署。",
            "manual/partial 来源建议人工核验后再作为重点推荐。",
        ],
    }

    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(STATUS_PATH, "w", encoding="utf-8") as file:
        json.dump(status, file, ensure_ascii=False, indent=2)
        file.write("\n")


def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] start updating deals")

    with open(DEALS_PATH, encoding="utf-8") as file:
        raw = json.load(file)

    deals = raw.get("deals", [])
    source_stats = build_source_stats(deals)
    updated = 0
    failed = 0
    skipped = 0

    for index, deal in enumerate(deals, start=1):
        source = deal.get("source", "unknown")
        title = deal.get("title", "")[:35]
        print(f"[{index:02d}/{len(deals)}] {source:12s} {title}")

        updater = {
            "v2ex": update_v2ex,
            "hacker-news": update_hacker_news,
            "linux.do": update_linux_do,
        }.get(source)

        if not updater:
            skipped += 1
            source_stats[source]["skipped"] += 1
            print(f"  skip: {source_stats[source]['note']}")
            continue

        try:
            ok, reason = updater(deal)
        except Exception as exc:
            ok = False
            reason = str(exc)

        if ok:
            updated += 1
            source_stats[source]["updated"] += 1
            print("  updated")
        else:
            failed += 1
            source_stats[source]["failed"] += 1
            source_stats[source]["last_error"] = reason or "unknown_error"
            print(f"  failed: {source_stats[source]['last_error']}")

        if source == "v2ex":
            time.sleep(0.3)
        elif source == "hacker-news":
            time.sleep(0.2)
        elif source == "linux.do":
            time.sleep(0.5)

    raw["updated_at"] = now_iso()
    raw["generated_by"] = "dealradar-auto-updater"

    with open(DEALS_PATH, "w", encoding="utf-8") as file:
        json.dump(raw, file, ensure_ascii=False, indent=2)
        file.write("\n")

    write_status(raw, source_stats, updated, failed, skipped)

    print(f"\nDone: {updated} updated, {failed} failed, {skipped} skipped, {len(deals)} total")
    print(f"deals updated_at: {raw['updated_at']}")
    print(f"status written: {STATUS_PATH}")


if __name__ == "__main__":
    main()
