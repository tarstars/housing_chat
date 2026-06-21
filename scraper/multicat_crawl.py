"""Scrape several list.am categories via the user's real Chrome (CDP).

Used to gather apartments across rent types — long-term (56) + short-term (166)
— since each category exposes its own rotating pool. Paginate each category
until its pool stops yielding new cards. Period (monthly/daily) is captured by
`scraper.extract` from each card's price text.

Prereq: Chrome launched with --remote-debugging-port=9222 and Cloudflare solved.
Usage:  CATEGORY_IDS=56,166 python3 -m scraper.multicat_crawl
"""
import json
import os
import time
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

from scraper import extract

CDP_URL = os.environ.get("CDP_URL", "http://127.0.0.1:9222")
CATEGORY_IDS = [c.strip() for c in os.environ.get("CATEGORY_IDS", "56,166").split(",") if c.strip()]


def download_thumbnail(context, url: str, dest_dir: str) -> str | None:
    Path(dest_dir).mkdir(parents=True, exist_ok=True)
    try:
        resp = context.request.get(url, timeout=20000)
        if not resp.ok:
            return None
        out = os.path.join(dest_dir, "0.jpg")
        with Image.open(BytesIO(resp.body())) as im:
            im.convert("RGB").save(out, "JPEG", quality=85)
        return out
    except Exception:
        return None


def main() -> None:
    raw_dir = os.environ.get("RAW_DIR", "data/raw")
    photos_dir = os.environ.get("PHOTOS_DIR", "data/raw/photos")
    pages_per_cat = int(os.environ.get("PAGES_PER_CAT", "15"))
    delay = float(os.environ.get("SCRAPE_DELAY", "1.2"))
    Path(raw_dir).mkdir(parents=True, exist_ok=True)
    existing = {p.stem for p in Path(raw_dir).glob("*.json")}

    total = 0
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP_URL)
        ctx = browser.contexts[0]
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        for cid in CATEGORY_IDS:
            cat_seen: set[str] = set()
            cat_new = 0
            empty_streak = 0
            for pg in range(1, pages_per_cat + 1):
                url = (f"https://www.list.am/en/category/{cid}" if pg == 1
                       else f"https://www.list.am/en/category/{cid}/{pg}")
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=40000)
                    page.wait_for_selector("a.h", timeout=15000)
                except Exception:
                    break
                cards = extract.collect_cards(page.content())
                fresh = [c for c in cards if c["id"] not in cat_seen]
                for c in cards:
                    cat_seen.add(c["id"])
                if not fresh:
                    empty_streak += 1
                    if empty_streak >= 3:       # pool is just repeating now
                        break
                    time.sleep(delay)
                    continue
                empty_streak = 0
                wrote = 0
                for c in fresh:
                    iid = c["id"]
                    if iid in existing:
                        continue
                    existing.add(iid)
                    c["scraped_at"] = datetime.now(timezone.utc).isoformat()
                    paths = []
                    for u in c.get("photo_urls", []):
                        pth = download_thumbnail(ctx, u, os.path.join(photos_dir, iid))
                        if pth:
                            paths.append(pth)
                    c["photo_paths"] = paths
                    (Path(raw_dir) / f"{iid}.json").write_text(
                        json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")
                    total += 1
                    cat_new += 1
                    wrote += 1
                print(f"cat {cid} pg{pg}: +{wrote} new (cat {cat_new}, total {total})", flush=True)
                time.sleep(delay)
            print(f"== category {cid}: {cat_new} new ==", flush=True)
    print(f"DONE: scraped {total} new listings into {raw_dir}")


if __name__ == "__main__":
    main()
