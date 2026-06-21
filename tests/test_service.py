from db import database
from bot.filters import Filters
from bot import service

class FakeClient:
    def __init__(self, filters):
        import types
        self._f = filters
        def parse(*, model, messages, response_format):
            msg = types.SimpleNamespace(parsed=self._f)
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])
        self.beta = types.SimpleNamespace(chat=types.SimpleNamespace(
            completions=types.SimpleNamespace(parse=parse)))

def seed(conn):
    database.upsert_listing(conn, {"id": "1", "url": "u1", "title": "cheap",
        "price": 500, "currency": "USD", "rooms": 2, "area_sqm": 50.0, "district": "Kentron"})
    database.upsert_listing(conn, {"id": "2", "url": "u2", "title": "pricey",
        "price": 900, "currency": "USD", "rooms": 3, "area_sqm": 80.0, "district": "Arabkir"})
    database.replace_photos(conn, "1", [
        {"url": "a", "local_path": "p0", "position": 0},
        {"url": "b", "local_path": "p1", "position": 1},
        {"url": "c", "local_path": "p2", "position": 2},
        {"url": "d", "local_path": "p3", "position": 3},
    ])

def test_answer_filters_and_limits_photos():
    conn = database.connect(":memory:"); database.init_db(conn); seed(conn)
    client = FakeClient(Filters(max_price=600, currency="USD"))
    results = service.answer("under 600 usd", conn, client, "gpt-4o-mini", 5)
    assert len(results) == 1
    assert "cheap" in results[0]["text"]
    assert results[0]["photos"] == ["p0", "p1", "p2"]

def test_answer_no_match_returns_empty():
    conn = database.connect(":memory:"); database.init_db(conn); seed(conn)
    client = FakeClient(Filters(max_price=100))
    assert service.answer("very cheap", conn, client, "gpt-4o-mini", 5) == []
