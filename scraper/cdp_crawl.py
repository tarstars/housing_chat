"""Scrape list.am via a real Chrome the user controls (Cloudflare-friendly).

Cloudflare blocks Playwright-launched browsers (automation-flagged). The reliable
workaround: launch the user's real Chrome with a remote-debugging port, let the
human solve the Cloudflare challenge once, then attach over CDP and paginate.

Usage:
  1. Launch Chrome with a debug port and the category page open:
       google-chrome --remote-debugging-port=9222 \\
         --user-data-dir=/tmp/hc_chrome_profile \\
         https://www.list.am/en/category/56
  2. Solve the Cloudflare check in that window.
  3. Run:  MAX_LISTINGS=1000 python3 -m scraper.cdp_crawl
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
from scraper.recon import CATEGORY_URL

CDP_URL = os.environ.get("CDP_URL", "http://127.0.0.1:9222")


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
    max_listings = int(os.environ.get("MAX_LISTINGS", "1000"))
    delay = float(os.environ.get("SCRAPE_DELAY", "1.5"))
    max_pages = int(os.environ.get("MAX_PAGES", "500"))
    Path(raw_dir).mkdir(parents=True, exist_ok=True)

    collected = 0
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP_URL)
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else context.new_page()
        for pno in range(1, max_pages + 1):
            if collected >= max_listings:
                break
            url = CATEGORY_URL if pno == 1 else f"{CATEGORY_URL}/{pno}"
            page.goto(url, wait_until="domcontentloaded", timeout=45000)
            try:
                page.wait_for_selector("a.h", timeout=30000)
            except Exception:
                print(f"page {pno}: no cards (Cloudflare?) — stopping", flush=True)
                break
            cards = extract.collect_cards(page.content())
            if not cards:
                print(f"page {pno}: 0 cards — stopping", flush=True)
                break
            new_on_page = 0
            for card in cards:
                if collected >= max_listings:
                    break
                iid = card["id"]
                out = Path(raw_dir) / f"{iid}.json"
                if out.exists():
                    continue
                card["scraped_at"] = datetime.now(timezone.utc).isoformat()
                paths = []
                for u in card.get("photo_urls", []):
                    pth = download_thumbnail(context, u, os.path.join(photos_dir, iid))
                    if pth:
                        paths.append(pth)
                card["photo_paths"] = paths
                out.write_text(json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8")
                collected += 1
                new_on_page += 1
            print(f"page {pno}: +{new_on_page} new (total {collected})", flush=True)
            time.sleep(delay)
    print(f"DONE: scraped {collected} listings into {raw_dir}")


if __name__ == "__main__":
    main()
