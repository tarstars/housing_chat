from pathlib import Path

from scraper.browser import browser_page, fetch_html

# Apartments for rent in Yerevan. Confirm/adjust during recon by browsing
# list.am: pick "Apartments for rent", set place = Yerevan, copy the URL.
CATEGORY_URL = "https://www.list.am/en/category/56"

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


def main() -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    with browser_page(headless=True) as page:
        cat_html = fetch_html(page, CATEGORY_URL)
        (FIXTURES / "category_sample.html").write_text(cat_html, encoding="utf-8")
        # Find the first item link and capture its detail page.
        import re
        m = re.search(r'href="(/(?:en/)?item/\d+)(?:\?[^"]*)??"', cat_html)
        if not m:
            print("No item link found — inspect category_sample.html and fix selectors.")
            return
        item_url = "https://www.list.am" + m.group(1)
        item_html = fetch_html(page, item_url)
        (FIXTURES / "item_sample.html").write_text(item_html, encoding="utf-8")
        print(f"Saved fixtures. Item: {item_url}")


if __name__ == "__main__":
    main()
