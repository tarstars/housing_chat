import json
import os
import time
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path

from PIL import Image

from scraper.browser import browser_page, fetch_html
from scraper import extract
from scraper.recon import CATEGORY_URL


def category_page_url(page: int) -> str:
    return CATEGORY_URL if page <= 1 else f"{CATEGORY_URL}/{page}"


def already_scraped(raw_dir: str, item_id: str) -> bool:
    return (Path(raw_dir) / f"{item_id}.json").exists()


def _fetch_listing_page(page, url: str, attempts: int = 5) -> str:
    """Fetch a category page, waiting for real listing cards to render.

    list.am intermittently serves a Cloudflare interstitial before the cards
    appear. Waiting for the ``a.h`` card selector lets the challenge resolve;
    if it still has no cards, retry a few times before giving up.
    """
    html = ""
    for _ in range(attempts):
        try:
            html = fetch_html(page, url, wait_selector="a.h", timeout=30000)
        except Exception:
            html = ""
        if extract.collect_cards(html):
            return html
        page.wait_for_timeout(3000)
    return html


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


def crawl(raw_dir: str, photos_dir: str, max_listings: int,
          delay: float = 2.0, headless: bool = True, max_pages: int = 200) -> int:
    Path(raw_dir).mkdir(parents=True, exist_ok=True)
    collected = 0
    with browser_page(headless=headless) as page:
        for pno in range(1, max_pages + 1):
            if collected >= max_listings:
                break
            html = _fetch_listing_page(page, category_page_url(pno))
            cards = extract.collect_cards(html)
            if not cards:
                break
            for card in cards:
                if collected >= max_listings:
                    break
                iid = card["id"]
                if already_scraped(raw_dir, iid):
                    continue
                card["scraped_at"] = datetime.now(timezone.utc).isoformat()
                thumb_dir = os.path.join(photos_dir, iid)
                paths = []
                for u in card.get("photo_urls", []):
                    p = download_thumbnail(page.context, u, thumb_dir)
                    if p:
                        paths.append(p)
                card["photo_paths"] = paths
                (Path(raw_dir) / f"{iid}.json").write_text(
                    json.dumps(card, ensure_ascii=False, indent=2), encoding="utf-8")
                collected += 1
            time.sleep(delay)
    return collected


def main() -> None:
    from common.config import load_config
    cfg = load_config()
    max_listings = int(os.environ.get("MAX_LISTINGS", "200"))
    # Headless reliably gets only the first category page (Cloudflare blocks
    # sequential pagination headless). Set HEADLESS=0 on a machine with a real
    # display to open a visible browser that passes the challenge per page.
    headless = os.environ.get("HEADLESS", "1").lower() not in ("0", "false", "no")
    delay = float(os.environ.get("SCRAPE_DELAY", "2.0"))
    n = crawl(cfg.raw_dir, cfg.photos_dir, max_listings, delay=delay, headless=headless)
    print(f"scraped {n} listings into {cfg.raw_dir}")


if __name__ == "__main__":
    main()
