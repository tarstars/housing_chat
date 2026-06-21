from contextlib import contextmanager

from playwright.sync_api import sync_playwright

_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


@contextmanager
def browser_page(headless: bool = True):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(user_agent=_UA, locale="en-US")
        page = context.new_page()
        try:
            yield page
        finally:
            context.close()
            browser.close()


def fetch_html(page, url: str, wait_selector: str | None = None,
               timeout: int = 30000) -> str:
    page.goto(url, timeout=timeout, wait_until="domcontentloaded")
    if wait_selector:
        page.wait_for_selector(wait_selector, timeout=timeout)
    else:
        try:
            page.wait_for_load_state("networkidle", timeout=timeout)
        except Exception:
            # Some pages have long-running third-party requests (maps, analytics).
            # Fall back to a brief fixed delay after domcontentloaded.
            page.wait_for_timeout(3000)
    return page.content()
