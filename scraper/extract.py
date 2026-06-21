import re

from bs4 import BeautifulSoup

BASE = "https://www.list.am"


def item_id(url: str) -> str:
    m = re.search(r"/item/(\d+)", url)
    return m.group(1) if m else url.rstrip("/").split("/")[-1].split("?")[0]


def _abs(src: str) -> str:
    if src.startswith("//"):
        return "https:" + src
    if src.startswith("/"):
        return BASE + src
    return src


def _parse_at(at_text: str) -> dict:
    attrs: dict[str, str] = {}
    m = re.search(r"(\d+)\s*rm", at_text)
    if m:
        attrs["Rooms"] = m.group(1)
    m = re.search(r"([\d.,]+)\s*sq\.?\s*m", at_text)
    if m:
        attrs["Floor area"] = m.group(1)
    m = re.search(r"(\d+\s*/\s*\d+)\s*floor", at_text)
    if m:
        attrs["Floor"] = m.group(1)
    return attrs


def _period(price_text: str) -> str:
    t = (price_text or "").lower()
    if "daily" in t:
        return "daily"
    if "weekly" in t:
        return "weekly"
    return "monthly"


def extract_card(a) -> dict:
    iid = item_id(a.get("href", ""))
    price_el = a.select_one(".p")
    title_el = a.select_one(".l")
    at_el = a.select_one(".at")
    img_el = a.select_one("img")
    at_text = at_el.get_text(" ", strip=True) if at_el else ""
    title = title_el.get_text(" ", strip=True) if title_el else None
    photo_urls = []
    if img_el:
        src = img_el.get("src") or img_el.get("data-src")
        if src:
            photo_urls.append(_abs(src))
    price_text = price_el.get_text(" ", strip=True) if price_el else ""
    return {
        "id": iid,
        "url": f"{BASE}/en/item/{iid}",
        "title": title,
        "price_text": price_text,
        "period": _period(price_text),
        "attributes": _parse_at(at_text),
        "address_text": at_text,
        "description": title,
        "photo_urls": photo_urls,
    }


def collect_cards(category_html: str) -> list[dict]:
    soup = BeautifulSoup(category_html, "lxml")
    cards, seen = [], set()
    for a in soup.select('a.h[href*="/item/"]'):
        iid = item_id(a.get("href", ""))
        if not iid or iid in seen:
            continue
        seen.add(iid)
        cards.append(extract_card(a))
    return cards
