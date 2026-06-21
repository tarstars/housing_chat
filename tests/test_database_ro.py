import sqlite3
import pytest
from db import database

def test_connect_ro_reads_but_cannot_write(tmp_path):
    path = str(tmp_path / "t.db")
    rw = database.connect(path)
    database.init_db(rw)
    database.upsert_listing(rw, {"id": "1", "price": 500, "rooms": 2, "area_sqm": 50.0, "district": "Kentron"})
    ro = database.connect_ro(path)
    rows = database.query_listings(ro, "SELECT id FROM listings", [])
    assert [r["id"] for r in rows] == ["1"]
    with pytest.raises(sqlite3.OperationalError):
        ro.execute("INSERT INTO listings (id) VALUES ('2')")
