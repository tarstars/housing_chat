import json
from types import SimpleNamespace
from db import database
from bot import agent

def _usage(p, c):
    return SimpleNamespace(prompt_tokens=p, completion_tokens=c, total_tokens=p + c)

def _tool_call(call_id, name, args):
    return SimpleNamespace(id=call_id, function=SimpleNamespace(name=name, arguments=json.dumps(args)))

def _resp(message, usage):
    return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)

class ScriptedClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._create))

    def _create(self, *, model, messages, tools, tool_choice):
        self.calls += 1
        return self._responses.pop(0)

def _seed():
    conn = database.connect(":memory:")
    database.init_db(conn)
    database.upsert_listing(conn, {"id": "1", "url": "u1", "title": "a", "price": 300000,
        "currency": "AMD", "rooms": 2, "area_sqm": 60.0, "district": "Kentron"})
    return conn

def test_run_executes_tool_then_returns_text():
    conn = _seed()
    first = SimpleNamespace(content=None, tool_calls=[
        _tool_call("c1", "search_listings", {"filters": {"district": "Kentron"}})])
    second = SimpleNamespace(content="Here is 1 listing in Kentron.", tool_calls=None)
    client = ScriptedClient([_resp(first, _usage(10, 5)), _resp(second, _usage(8, 7))])
    res = agent.run([{"role": "user", "content": "flats in Kentron"}], conn, client, "m", max_iters=4)
    assert res.text == "Here is 1 listing in Kentron."
    assert [r["id"] for r in res.listings] == ["1"]
    assert res.telemetry["llm_calls"] == 2
    assert res.telemetry["iterations"] == 2
    assert res.telemetry["total_tokens"] == 30
    assert res.telemetry["tool_calls"][0]["name"] == "search_listings"

def test_run_marks_empty_search():
    conn = _seed()
    first = SimpleNamespace(content=None, tool_calls=[
        _tool_call("c1", "search_listings", {"filters": {"district": "Avan"}})])
    second = SimpleNamespace(content="No listings there.", tool_calls=None)
    client = ScriptedClient([_resp(first, _usage(1, 1)), _resp(second, _usage(1, 1))])
    res = agent.run([{"role": "user", "content": "flats in Avan"}], conn, client, "m")
    assert res.listings == []
    assert res.telemetry["empty_search"] is True

def test_run_loop_exhausted():
    conn = _seed()
    looping = _resp(SimpleNamespace(content=None, tool_calls=[
        _tool_call("c1", "dataset_info", {})]), _usage(1, 1))
    client = ScriptedClient([looping, looping, looping, looping])
    res = agent.run([{"role": "user", "content": "x"}], conn, client, "m", max_iters=3)
    assert res.telemetry["loop_exhausted"] is True
    assert res.telemetry["iterations"] == 3
    assert client.calls == 3
