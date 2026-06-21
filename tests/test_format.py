from bot.format import format_listing, format_no_results

def test_format_listing_contains_fields():
    s = format_listing({
        "title": "2 room flat", "price": 700, "currency": "USD",
        "rooms": 2, "area_sqm": 65.0, "district": "Kentron",
        "url": "https://www.list.am/en/item/1",
    })
    assert "700" in s and "$" in s
    assert "2" in s and "65" in s and "Kentron" in s
    assert "https://www.list.am/en/item/1" in s

def test_no_results_message():
    assert "No matching" in format_no_results()

def test_format_count():
    from bot.format import format_count
    assert "21" in format_count(21, filtered=False)
    assert "6" in format_count(6, filtered=True)
    assert "listing" in format_count(1, filtered=False)
