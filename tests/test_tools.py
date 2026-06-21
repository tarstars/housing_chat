from db import database
from bot import tools

def seed():
    conn = database.connect(":memory:")
    database.init_db(conn)
    database.upsert_listing(conn, {"id": "1", "url": "u1", "title": "a", "price": 300000,
        "currency": "AMD", "rooms": 2, "area_sqm": 60.0, "district": "Kentron", "scraped_at": "2026-06-21T10:00:00+00:00"})
    database.upsert_listing(conn, {"id": "2", "url": "u2", "title": "b", "price": 500000,
        "currency": "AMD", "rooms": 3, "area_sqm": 80.0, "district": "Arabkir", "scraped_at": "2026-06-20T10:00:00+00:00"})
    database.upsert_listing(conn, {"id": "3", "url": "u3", "title": "c", "price": 200000,
        "currency": "AMD", "rooms": 1, "area_sqm": 40.0, "district": "Kentron", "scraped_at": "2026-06-19T10:00:00+00:00"})
    database.replace_photos(conn, "1", [{"url": "x", "local_path": "p0", "position": 0}])
    return conn

def test_search_listings_filters_and_limits():
    conn = seed()
    out = tools.search_listings(conn, filters={"district": "Kentron"}, sort="price_asc", limit=5)
    ids = [r["id"] for r in out["listings"]]
    assert ids == ["3", "1"]            # Kentron only, cheapest first
    assert out["listings"][0]["district"] == "Kentron"

def test_search_listings_limit_capped():
    conn = seed()
    out = tools.search_listings(conn, limit=999)
    assert len(out["listings"]) == 3   # capped at <=10, only 3 exist

def test_aggregate_count_and_avg():
    conn = seed()
    assert tools.aggregate_stats(conn, metric="count")["value"] == 3
    assert tools.aggregate_stats(conn, filters={"district": "Kentron"}, metric="count")["value"] == 2
    assert tools.aggregate_stats(conn, metric="min_price")["value"] == 200000
    assert tools.aggregate_stats(conn, metric="max_price")["value"] == 500000

def test_aggregate_group_by_district():
    conn = seed()
    out = tools.aggregate_stats(conn, metric="count", group_by="district")
    groups = {g["district"]: g["value"] for g in out["groups"]}
    assert groups == {"Kentron": 2, "Arabkir": 1}

def test_aggregate_bad_metric_returns_error():
    conn = seed()
    assert "error" in tools.aggregate_stats(conn, metric="median")

def test_dataset_info():
    conn = seed()
    info = tools.dataset_info(conn)
    assert info["total"] == 3
    assert set(info["districts"]) == {"Kentron", "Arabkir"}
    assert info["price_range"] == {"min": 200000, "max": 500000}
    assert info["last_scraped_at"] == "2026-06-21T10:00:00+00:00"

def test_get_listing_found_and_missing():
    conn = seed()
    got = tools.get_listing(conn, "1")
    assert got["listing"]["id"] == "1"
    assert got["photos"] == ["p0"]
    assert tools.get_listing(conn, "999")["listing"] is None

def test_dispatch_unknown_and_bad_args():
    conn = seed()
    assert "error" in tools.dispatch("nope", {}, conn)
    assert "error" in tools.dispatch("get_listing", {"wrong": 1}, conn)

def test_tools_schema_shape():
    names = {t["function"]["name"] for t in tools.TOOLS}
    assert names == {"search_listings", "aggregate_stats", "dataset_info", "get_listing"}
