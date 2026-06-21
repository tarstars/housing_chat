from pathlib import Path

from scraper.browser import browser_page, fetch_html

# Yerevan apartments for rent (long-term). Confirmed during recon: this
# category page passes Cloudflare headless and lists per-card data (price,
# district, rooms, area, floor, thumbnail). Individual /item/ detail pages
# are behind a harder Cloudflare managed challenge, so the scraper works at
# the category-card level only.
CATEGORY_URL = "https://www.list.am/en/category/56"

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


def main() -> None:
    """Capture a category page as a fixture for offline extractor tests."""
    FIXTURES.mkdir(parents=True, exist_ok=True)
    with browser_page(headless=True) as page:
        cat_html = fetch_html(page, CATEGORY_URL)
        out = FIXTURES / "category_sample.html"
        out.write_text(cat_html, encoding="utf-8")
        if "Just a moment" in cat_html or "challenge-platform" in cat_html:
            print("WARNING: category page returned a Cloudflare challenge, not listings.")
        else:
            print(f"Saved {out} ({len(cat_html)} bytes).")


if __name__ == "__main__":
    main()
