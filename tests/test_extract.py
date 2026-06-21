from pathlib import Path
from scraper import extract

FIX = Path(__file__).parent / "fixtures"

def test_item_id():
    assert extract.item_id("/en/item/23742410?ld_src=2") == "23742410"
    assert extract.item_id("https://www.list.am/en/item/55?x=1") == "55"

def test_period_from_price_text():
    assert extract._period("32,000 ֏ daily") == "daily"
    assert extract._period("300,000 ֏ monthly") == "monthly"
    assert extract._period("") == "monthly"

def test_parse_at():
    a = extract._parse_at("Arabkir, 8 rm., 600 sq.m., 8/10 floor")
    assert a["Rooms"] == "8"
    assert a["Floor area"].startswith("600")
    assert a["Floor"].replace(" ", "") == "8/10"

def test_collect_cards_from_real_fixture():
    html = (FIX / "category_sample.html").read_text(encoding="utf-8")
    cards = extract.collect_cards(html)
    assert len(cards) >= 5
    ids = [c["id"] for c in cards]
    assert len(ids) == len(set(ids))                       # deduped
    assert all(c["url"].startswith("https://www.list.am/en/item/") for c in cards)
    assert any(c["price_text"] for c in cards)
    parsed = [c for c in cards
              if c["attributes"].get("Rooms") and c["attributes"].get("Floor area")]
    assert parsed, "expected at least one card with rooms and area parsed"
    assert any(c["photo_urls"] and c["photo_urls"][0].startswith("https://") for c in cards)
