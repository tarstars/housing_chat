from db import database

def make_conn():
    conn = database.connect(":memory:")
    database.init_db(conn)
    return conn

def test_upsert_and_query():
    conn = make_conn()
    database.upsert_listing(conn, {
        "id": "1", "url": "u", "title": "t", "price": 500, "currency": "USD",
        "rooms": 2, "area_sqm": 60.0, "floor": 3, "total_floors": 9,
        "district": "Kentron", "address": "a", "description": "d",
        "posted_at": None, "scraped_at": "now",
    })
    rows = database.query_listings(conn, "SELECT * FROM listings WHERE price <= ?", [600])
    assert len(rows) == 1 and rows[0]["district"] == "Kentron"

def test_upsert_is_idempotent():
    conn = make_conn()
    row = {"id": "1", "price": 500, "currency": "USD", "rooms": 2, "area_sqm": 60.0}
    database.upsert_listing(conn, row)
    database.upsert_listing(conn, {**row, "price": 450})
    rows = database.query_listings(conn, "SELECT * FROM listings", [])
    assert len(rows) == 1 and rows[0]["price"] == 450

def test_replace_photos():
    conn = make_conn()
    database.upsert_listing(conn, {"id": "1", "price": 1})
    database.replace_photos(conn, "1", [{"url": "x", "local_path": "p0", "position": 0}])
    database.replace_photos(conn, "1", [{"url": "y", "local_path": "p1", "position": 0}])
    photos = database.get_photos(conn, "1")
    assert len(photos) == 1 and photos[0]["local_path"] == "p1"
