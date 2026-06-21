import json
from db import database
from processor import process

RAW = {
    "id": "1", "url": "https://www.list.am/en/item/1", "title": "2 room flat",
    "price_text": "$700",
    "attributes": {"Rooms": "2", "Floor area": "65 m²", "Floor": "3/9"},
    "address_text": "Yerevan, Kentron, Abovyan", "description": "nice",
    "photo_urls": ["http://x/0.jpg"], "photo_paths": ["data/raw/photos/1/0.jpg"],
    "scraped_at": "2026-06-21T10:00:00+00:00",
}

def test_raw_to_row_normalizes():
    row = process.raw_to_row(RAW)
    assert row["price"] == 700 and row["currency"] == "USD"
    assert row["rooms"] == 2 and row["area_sqm"] == 65.0
    assert row["floor"] == 3 and row["total_floors"] == 9
    assert row["district"] == "Kentron"

def test_is_complete_requires_price_and_size():
    assert process.is_complete({"price": 1, "rooms": 2}) is True
    assert process.is_complete({"price": None, "rooms": 2}) is False
    assert process.is_complete({"price": 1, "rooms": None, "area_sqm": None}) is False

def test_process_raw_dir(tmp_path):
    (tmp_path / "1.json").write_text(json.dumps(RAW), encoding="utf-8")
    bad = {**RAW, "id": "2", "price_text": ""}
    (tmp_path / "2.json").write_text(json.dumps(bad), encoding="utf-8")
    conn = database.connect(":memory:")
    database.init_db(conn)
    written, skipped = process.process_raw_dir(str(tmp_path), conn)
    assert (written, skipped) == (1, 1)
    rows = database.query_listings(conn, "SELECT * FROM listings", [])
    assert len(rows) == 1
    assert database.get_photos(conn, "1")[0]["local_path"] == "data/raw/photos/1/0.jpg"
