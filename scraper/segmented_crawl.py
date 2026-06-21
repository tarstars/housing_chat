"""Segmented scrape of list.am via the user's real Chrome (CDP).

list.am's flat category view only exposes a small rotating pool (~60 listings).
To reach the real inventory we segment by PRICE BAND: each narrow band exposes
its own pool, and narrow bands hold fewer listings than the rotating cap, so we
capture most of each. Combining many bands (× a few pages each) yields far more
unique listings. Drives the real Chrome over CDP (Cloudflare-friendly).

Prereq: Chrome already launched with --remote-debugging-port=9222 and the
Cloudflare check solved (see scraper/cdp_crawl.py docstring).

Usage:  MAX_LISTINGS=1000 python3 -m scraper.segmented_crawl
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
BASE = "https://www.list.am/en/category/56"


def price_bands() -> list[tuple[int, int]]:
    bands = [(0, 80000)]                       # incl. USD-numeric + very cheap
    lo = 80000
    while lo < 600000:                         # dense rental range: 20k steps
        bands.append((lo, lo + 20000)); lo += 20000
    while lo < 1000000:                        # 50k steps
        bands.append((lo, lo + 50000)); lo += 50000
    while lo < 3000000:                        # 250k steps
        bands.append((lo, lo + 250000)); lo += 250000
    bands.append((3000000, 99000000))
    return bands


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


def band_url(lo: int, hi: int, pg: int) -> str:
    path = BASE if pg == 1 else f"{BASE}/{pg}"
    return f"{path}?price1={lo}&price2={hi}&crc=0"


def main() -> None:
    raw_dir = os.environ.get("RAW_DIR", "data/raw")
    photos_dir = os.environ.get("PHOTOS_DIR", "data/raw/photos")
    max_listings = int(os.environ.get("MAX_LISTINGS", "1000"))
    pages_per_band = int(os.environ.get("PAGES_PER_BAND", "4"))
    delay = float(os.environ.get("SCRAPE_DELAY", "1.2"))
    Path(raw_dir).mkdir(parents=True, exist_ok=True)
    existing = {p.stem for p in Path(raw_dir).glob("*.json")}

    collected = 0
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP_URL)
        ctx = browser.contexts[0]
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        for lo, hi in price_bands():
            if collected >= max_listings:
                break
            band_seen: set[str] = set()
            for pg in range(1, pages_per_band + 1):
                if collected >= max_listings:
                    break
                try:
                    page.goto(band_url(lo, hi, pg), wait_until="domcontentloaded", timeout=45000)
                    page.wait_for_selector("a.h", timeout=15000)
                except Exception:
                    break
                cards = extract.collect_cards(page.content())
                fresh = [c for c in cards if c["id"] not in band_seen]
                if not fresh:
                    break  # this band's rotation is repeating — move on
                for c in cards:
                    band_seen.add(c["id"])
                newly = 0
                for c in fresh:
                    if collected >= max_listings:
                        break
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
                    collected += 1
                    newly += 1
                print(f"band {lo}-{hi} pg{pg}: +{newly} new (total {collected})", flush=True)
                time.sleep(delay)
    print(f"DONE: scraped {collected} new listings into {raw_dir}")


if __name__ == "__main__":
    main()
