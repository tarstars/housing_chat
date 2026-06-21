import json
from db import database
from processor import process
from bot.filters import Filters
from bot import service


class FakeClient:
    def __init__(self, filters):
        import types
        def parse(*, model, messages, response_format):
            msg = types.SimpleNamespace(parsed=filters)
            return types.SimpleNamespace(choices=[types.SimpleNamespace(message=msg)])
        self.beta = types.SimpleNamespace(chat=types.SimpleNamespace(
            completions=types.SimpleNamespace(parse=parse)))


def test_raw_to_db_to_answer(tmp_path):
    raw = {
        "id": "1", "url": "https://www.list.am/en/item/1", "title": "2 room flat",
        "price_text": "$650",
        "attributes": {"Rooms": "2", "Floor area": "60 m²", "Floor": "4/9"},
        "address_text": "Yerevan, Kentron", "description": "d",
        "photo_urls": ["u0"], "photo_paths": ["p0"],
        "scraped_at": "2026-06-21T10:00:00+00:00",
    }
    (tmp_path / "1.json").write_text(json.dumps(raw), encoding="utf-8")
    conn = database.connect(":memory:"); database.init_db(conn)
    written, _ = process.process_raw_dir(str(tmp_path), conn)
    assert written == 1
    client = FakeClient(Filters(max_price=700, district="Kentron"))
    results = service.answer("2 room in Kentron under 700$", conn, client, "m", 5)
    assert len(results) == 1
    assert "2 room flat" in results[0]["text"] and results[0]["photos"] == ["p0"]
