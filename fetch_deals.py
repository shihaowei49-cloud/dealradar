#!/usr/bin/env python3
"""
DealRadar 数据更新脚本
每天自动从各论坛抓取最新数据，更新 deals.json 的 views/likes/replies 字段
"""

import json
import re
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

DEALS_PATH = Path(__file__).parent / "data" / "structured" / "deals.json"

def fetch_json(url, timeout=10):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        print(f"  ✗ {url[:60]}: {e}")
        return None


def update_v2ex(deal):
    m = re.search(r"/t/(\d+)", deal["url"])
    if not m:
        return False
    data = fetch_json(f"https://www.v2ex.com/api/topics/show.json?id={m.group(1)}")
    if data and isinstance(data, list) and data:
        t = data[0]
        deal["replies"] = t.get("replies", deal.get("replies", 0))
        return True
    return False


def update_hacker_news(deal):
    m = re.search(r"id=(\d+)", deal["url"])
    if not m:
        return False
    data = fetch_json(f"https://hacker-news.firebaseio.com/v0/item/{m.group(1)}.json")
    if data:
        deal["likes"] = data.get("score", deal.get("likes", 0))
        deal["replies"] = data.get("descendants", deal.get("replies", 0))
        return True
    return False


def update_linux_do(deal):
    """linux.do 需要登录态，此函数为占位符，实际由 GitHub Actions + Secrets 处理"""
    # 如需支持，可配合 cookie 在 headers 里传入 _forum_session
    topic_id = deal["url"].rstrip("/").split("/")[-1]
    # 尝试公开 API（未登录可能受限）
    data = fetch_json(f"https://linux.do/t/{topic_id}.json")
    if data and data.get("views"):
        deal["views"] = data.get("views", deal.get("views", 0))
        deal["likes"] = data.get("like_count", deal.get("likes", 0))
        deal["replies"] = data.get("posts_count", deal.get("replies", 0))
        deal["last_posted_at"] = data.get("last_posted_at", deal.get("last_posted_at", ""))
        return True
    return False


def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始更新 deals.json ...")

    with open(DEALS_PATH, encoding="utf-8") as f:
        raw = json.load(f)

    deals = raw["deals"]
    updated = 0
    skipped = 0

    for i, deal in enumerate(deals):
        src = deal["source"]
        print(f"[{i+1:02d}/{len(deals)}] {src:12s} {deal['title'][:35]}")

        ok = False
        if src == "v2ex":
            ok = update_v2ex(deal)
            time.sleep(0.3)
        elif src == "hacker-news":
            ok = update_hacker_news(deal)
            time.sleep(0.2)
        elif src == "linux.do":
            ok = update_linux_do(deal)
            time.sleep(0.5)
        else:
            skipped += 1
            print(f"  ⊘ 跳过（{src} 需手动/浏览器采集）")
            continue

        if ok:
            updated += 1
            print(f"  ✓ 更新成功")
        else:
            print(f"  ✗ 更新失败，保留原值")

    raw["updated_at"] = datetime.now(timezone.utc).isoformat()
    raw["generated_by"] = "dealradar-auto-updater"

    with open(DEALS_PATH, "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False, indent=2)

    print(f"\n完成：{updated} 条更新，{skipped} 条跳过，共 {len(deals)} 条")
    print(f"updated_at → {raw['updated_at']}")


if __name__ == "__main__":
    main()
