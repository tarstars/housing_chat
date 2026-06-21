# Bot Assistant Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the bot's single-shot search/count query layer with a tool-calling agent over a few audited, read-only tools, with multi-turn memory and structured logging — so it answers stats, comparisons, recommendations, and listing/meta questions, DB-grounded, in the user's language.

**Architecture:** Each Telegram message (voice transcribed first) plus recent per-chat history is sent to OpenAI chat-completions with four read-only tools (`search_listings`, `aggregate_stats`, `dataset_info`, `get_listing`). A bounded loop executes tool calls against SQLite (parameterized, read-only) and feeds results back until the model returns a natural-language answer; search/detail results are also rendered as photo cards. Every message is logged as JSONL for analysis.

**Tech Stack:** Python 3.10+, OpenAI Python SDK (chat-completions tool calling + Whisper), python-telegram-bot v22, SQLite (stdlib `sqlite3`), Pydantic v2, pytest.

## Global Constraints

- Python 3.10+.
- All AI via OpenAI only (`OPENAI_CHAT_MODEL` default `gpt-4o-mini`; Whisper for STT).
- Tools are **read-only**: SELECT only, all SQL **parameterized**; the agent uses a read-only SQLite connection. No model-generated SQL.
- Tool args validated: `limit` capped at 10; `metric`, `group_by`, `sort`, `currency` whitelisted; invalid args return `{"error": ...}` (never raise into the loop).
- Replies in the user's language; DB-grounded; brief general knowledge only when explicitly flagged as not from the listings.
- Conversation memory is per-chat, in-memory, last `HISTORY_MAX_TURNS` messages; `/start` and `/clear` reset it.
- Interaction log is JSONL at `<LOG_DIR>/interactions.jsonl` (git-ignored). Operational logs go to stdout at INFO.
- Each stage runnable via `python -m <pkg>.<module>`. Tests run from repo root (pytest `pythonpath=["."]`), command `python3 -m pytest`.
- The scrape/process stages are unchanged.

## File structure (delta)

```
common/config.py        # MODIFIED: + log_dir, agent_max_iters, history_max_turns
db/database.py          # MODIFIED: + connect_ro
bot/
  filters.py            # reused (_where_clause, build_query, Filters); intent + build_count_query removed in Task 7
  tools.py              # NEW: 4 read-only tools + JSON schemas + dispatch
  conversation.py       # NEW: per-chat memory
  interaction_log.py    # NEW: JSONL log + outcome classifier + record builder
  agent.py              # NEW: tool-calling loop + AgentResult + system prompt
  main.py               # MODIFIED: agent wiring, logging, /start /clear, card rendering
  format.py             # reused (format_listing); format_count/format_no_results removed in Task 7
  openai_client.py      # reused (transcribe); parse_query/SYSTEM_PROMPT removed in Task 7
  service.py            # REMOVED in Task 7
tests/                  # new tests per task; obsolete tests removed in Task 7
.env.example            # MODIFIED: + LOG_DIR, AGENT_MAX_ITERS, HISTORY_MAX_TURNS
```

Dependency order: Task 1 → (Tasks 2, 3, 4 independent) → Task 5 (needs 2) → Task 6 (needs 2,3,4,5) → Task 7 (cleanup).

---

### Task 1: Config additions

**Files:**
- Modify: `common/config.py`, `.env.example`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `Config` gains `log_dir: str`, `agent_max_iters: int`, `history_max_turns: int`; `load_config()` reads `LOG_DIR` (default `data/logs`), `AGENT_MAX_ITERS` (default `4`), `HISTORY_MAX_TURNS` (default `6`).

- [ ] **Step 1: Add failing assertions to `tests/test_config.py`**

Append to the existing `test_load_config_defaults`:

```python
    assert cfg.log_dir == "data/logs"
    assert cfg.agent_max_iters == 4
    assert cfg.history_max_turns == 6
```

- [ ] **Step 2: Run test, verify it fails**

Run: `python3 -m pytest tests/test_config.py -v`
Expected: FAIL (`AttributeError: 'Config' object has no attribute 'log_dir'`).

- [ ] **Step 3: Add the fields to `common/config.py`**

In the `Config` dataclass add after `result_limit: int`:

```python
    log_dir: str
    agent_max_iters: int
    history_max_turns: int
```

In `load_config()` add inside the `Config(...)` call after `result_limit=...`:

```python
        log_dir=os.environ.get("LOG_DIR", "data/logs"),
        agent_max_iters=int(os.environ.get("AGENT_MAX_ITERS", "4")),
        history_max_turns=int(os.environ.get("HISTORY_MAX_TURNS", "6")),
```

- [ ] **Step 4: Append to `.env.example`**

```bash
LOG_DIR=data/logs
AGENT_MAX_ITERS=4
HISTORY_MAX_TURNS=6
```

- [ ] **Step 5: Run test, verify it passes**

Run: `python3 -m pytest tests/test_config.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add common/config.py .env.example tests/test_config.py
git commit -m "feat(config): add log_dir, agent_max_iters, history_max_turns"
```

---

### Task 2: Read-only connection + tool layer

**Files:**
- Modify: `db/database.py`
- Create: `bot/tools.py`
- Test: `tests/test_database_ro.py`, `tests/test_tools.py`

**Interfaces:**
- Consumes: `bot.filters.Filters`, `bot.filters.build_query`, `bot.filters._where_clause`, `db.database.query_listings`, `db.database.get_photos`.
- Produces:
  - `db.database.connect_ro(db_path: str) -> sqlite3.Connection` (read-only)
  - `bot.tools.search_listings(conn, filters=None, sort="price_asc", limit=5) -> dict`
  - `bot.tools.aggregate_stats(conn, filters=None, metric="count", group_by=None) -> dict`
  - `bot.tools.dataset_info(conn) -> dict`
  - `bot.tools.get_listing(conn, listing_id) -> dict`
  - `bot.tools.dispatch(name: str, args: dict, conn) -> dict`
  - `bot.tools.TOOLS: list` (OpenAI function-calling schemas)

- [ ] **Step 1: Write failing test `tests/test_database_ro.py`**

```python
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
```

- [ ] **Step 2: Run test, verify it fails**

Run: `python3 -m pytest tests/test_database_ro.py -v`
Expected: FAIL (`AttributeError: module 'db.database' has no attribute 'connect_ro'`).

- [ ] **Step 3: Add `connect_ro` to `db/database.py`**

Add after `connect`:

```python
def connect_ro(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn
```

- [ ] **Step 4: Run test, verify it passes**

Run: `python3 -m pytest tests/test_database_ro.py -v`
Expected: PASS.

- [ ] **Step 5: Write failing test `tests/test_tools.py`**

```python
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
```

- [ ] **Step 6: Run test, verify it fails**

Run: `python3 -m pytest tests/test_tools.py -v`
Expected: FAIL (`ModuleNotFoundError: bot.tools`).

- [ ] **Step 7: Write `bot/tools.py`**

```python
from bot.filters import Filters, build_query, _where_clause
from db import database

_METRIC_SQL = {
    "count": "count(*)",
    "avg_price": "avg(price)",
    "min_price": "min(price)",
    "max_price": "max(price)",
    "avg_area": "avg(area_sqm)",
    "min_area": "min(area_sqm)",
    "max_area": "max(area_sqm)",
}
_SORTS = ("price_asc", "price_desc", "area_desc", "newest")
_FILTER_KEYS = ("min_price", "max_price", "currency", "min_rooms",
                "max_rooms", "min_area", "max_area", "district")
_ROW_COLS = ("id", "price", "currency", "rooms", "area_sqm", "floor",
             "total_floors", "district", "title", "url")


def _filters_from(args) -> Filters:
    args = args or {}
    return Filters(**{k: v for k, v in args.items() if k in _FILTER_KEYS})


def _round(v):
    return round(v, 1) if isinstance(v, float) else v


def search_listings(conn, filters=None, sort="price_asc", limit=5) -> dict:
    if sort not in _SORTS:
        sort = "price_asc"
    limit = max(1, min(int(limit or 5), 10))
    f = _filters_from(filters).model_copy(update={"sort": sort})
    sql, params = build_query(f, limit)
    rows = database.query_listings(conn, sql, params)
    return {"listings": [{c: r.get(c) for c in _ROW_COLS} for r in rows]}


def aggregate_stats(conn, filters=None, metric="count", group_by=None) -> dict:
    if metric not in _METRIC_SQL:
        return {"error": f"unknown metric '{metric}'; allowed: {list(_METRIC_SQL)}"}
    if group_by not in (None, "district"):
        return {"error": "group_by must be 'district' or null"}
    where, params = _where_clause(_filters_from(filters))
    expr = _METRIC_SQL[metric]
    if group_by == "district":
        sql = (f"SELECT district, {expr} AS value FROM listings{where} "
               "GROUP BY district ORDER BY value")
        rows = database.query_listings(conn, sql, params)
        return {"metric": metric, "group_by": "district",
                "groups": [{"district": r["district"], "value": _round(r["value"])}
                           for r in rows]}
    rows = database.query_listings(conn, f"SELECT {expr} AS value FROM listings{where}", params)
    return {"metric": metric, "value": _round(rows[0]["value"])}


def dataset_info(conn) -> dict:
    total = database.query_listings(conn, "SELECT count(*) AS n FROM listings", [])[0]["n"]
    districts = [r["district"] for r in database.query_listings(
        conn, "SELECT DISTINCT district FROM listings WHERE district IS NOT NULL ORDER BY district", [])]
    pr = database.query_listings(conn, "SELECT min(price) AS mn, max(price) AS mx FROM listings", [])[0]
    currencies = [r["currency"] for r in database.query_listings(
        conn, "SELECT DISTINCT currency FROM listings WHERE currency IS NOT NULL", [])]
    last = database.query_listings(conn, "SELECT max(scraped_at) AS m FROM listings", [])[0]["m"]
    return {"total": total, "districts": districts,
            "price_range": {"min": pr["mn"], "max": pr["mx"]},
            "currencies": currencies, "last_scraped_at": last}


def get_listing(conn, listing_id) -> dict:
    rows = database.query_listings(conn, "SELECT * FROM listings WHERE id = ?", [str(listing_id)])
    if not rows:
        return {"listing": None, "photos": []}
    photos = database.get_photos(conn, str(listing_id))
    return {"listing": rows[0], "photos": [p["local_path"] for p in photos if p.get("local_path")]}


_IMPL = {
    "search_listings": search_listings,
    "aggregate_stats": aggregate_stats,
    "dataset_info": dataset_info,
    "get_listing": get_listing,
}


def dispatch(name: str, args: dict, conn) -> dict:
    fn = _IMPL.get(name)
    if fn is None:
        return {"error": f"unknown tool '{name}'"}
    try:
        return fn(conn, **(args or {}))
    except TypeError as e:
        return {"error": f"bad arguments for {name}: {e}"}
    except Exception as e:  # tools must never raise into the loop
        return {"error": f"{name} failed: {e}"}


_FILTER_SCHEMA = {
    "type": "object",
    "properties": {
        "min_price": {"type": "integer"}, "max_price": {"type": "integer"},
        "currency": {"type": "string", "enum": ["AMD", "USD"]},
        "min_rooms": {"type": "integer"}, "max_rooms": {"type": "integer"},
        "min_area": {"type": "number"}, "max_area": {"type": "number"},
        "district": {"type": "string"},
    },
}

TOOLS = [
    {"type": "function", "function": {
        "name": "search_listings",
        "description": "Find rental listings matching filters. Returns matching "
                       "listings, which are also shown to the user as photo cards.",
        "parameters": {"type": "object", "properties": {
            "filters": _FILTER_SCHEMA,
            "sort": {"type": "string", "enum": list(_SORTS)},
            "limit": {"type": "integer"}}}}},
    {"type": "function", "function": {
        "name": "aggregate_stats",
        "description": "Compute a statistic (count, or avg/min/max of price or "
                       "area) over listings matching filters, optionally grouped "
                       "by district.",
        "parameters": {"type": "object", "properties": {
            "filters": _FILTER_SCHEMA,
            "metric": {"type": "string", "enum": list(_METRIC_SQL)},
            "group_by": {"type": "string", "enum": ["district"]}},
            "required": ["metric"]}}},
    {"type": "function", "function": {
        "name": "dataset_info",
        "description": "Overview of the dataset: total listings, districts "
                       "covered, price range, currencies, and data freshness.",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "get_listing",
        "description": "Full details and photos for one listing by its id.",
        "parameters": {"type": "object", "properties": {
            "listing_id": {"type": "string"}}, "required": ["listing_id"]}}},
]
```

- [ ] **Step 8: Run tests, verify they pass**

Run: `python3 -m pytest tests/test_tools.py tests/test_database_ro.py -v`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add db/database.py bot/tools.py tests/test_tools.py tests/test_database_ro.py
git commit -m "feat(bot): read-only connection + agent tool layer"
```

---

### Task 3: Conversation memory

**Files:**
- Create: `bot/conversation.py`
- Test: `tests/test_conversation.py`

**Interfaces:**
- Produces: `bot.conversation.Conversation(max_turns: int = 6)` with `history(chat_id) -> list[dict]`, `append(chat_id, user_text, assistant_text) -> None`, `clear(chat_id) -> None`. Messages are `{"role": "user"|"assistant", "content": str}`; only the last `max_turns` are kept.

- [ ] **Step 1: Write failing test `tests/test_conversation.py`**

```python
from bot.conversation import Conversation

def test_append_and_history():
    c = Conversation(max_turns=6)
    c.append(1, "hi", "hello")
    assert c.history(1) == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]
    assert c.history(2) == []          # unknown chat

def test_history_trims_to_max_turns():
    c = Conversation(max_turns=4)      # keep last 4 messages = 2 turns
    for i in range(5):
        c.append(1, f"u{i}", f"a{i}")
    h = c.history(1)
    assert len(h) == 4
    assert h[0] == {"role": "user", "content": "u3"}
    assert h[-1] == {"role": "assistant", "content": "a4"}

def test_history_returns_copy():
    c = Conversation()
    c.append(1, "u", "a")
    c.history(1).append({"role": "user", "content": "x"})
    assert len(c.history(1)) == 2      # internal store unaffected

def test_clear():
    c = Conversation()
    c.append(1, "u", "a")
    c.clear(1)
    assert c.history(1) == []
```

- [ ] **Step 2: Run test, verify it fails**

Run: `python3 -m pytest tests/test_conversation.py -v`
Expected: FAIL (`ModuleNotFoundError: bot.conversation`).

- [ ] **Step 3: Write `bot/conversation.py`**

```python
class Conversation:
    """In-memory per-chat message history, trimmed to the last max_turns."""

    def __init__(self, max_turns: int = 6):
        self._max = max_turns
        self._store: dict[int, list[dict]] = {}

    def history(self, chat_id: int) -> list[dict]:
        return list(self._store.get(chat_id, []))

    def append(self, chat_id: int, user_text: str, assistant_text: str) -> None:
        msgs = self._store.setdefault(chat_id, [])
        msgs.append({"role": "user", "content": user_text})
        msgs.append({"role": "assistant", "content": assistant_text})
        if len(msgs) > self._max:
            del msgs[: len(msgs) - self._max]

    def clear(self, chat_id: int) -> None:
        self._store.pop(chat_id, None)
```

- [ ] **Step 4: Run test, verify it passes**

Run: `python3 -m pytest tests/test_conversation.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add bot/conversation.py tests/test_conversation.py
git commit -m "feat(bot): per-chat conversation memory"
```

---

### Task 4: Interaction log

**Files:**
- Create: `bot/interaction_log.py`
- Test: `tests/test_interaction_log.py`

**Interfaces:**
- Produces:
  - `bot.interaction_log.classify_outcome(error, telemetry: dict, surfaced: list) -> str` → `"error"|"loop_exhausted"|"empty"|"ok"`
  - `bot.interaction_log.build_record(chat_id, input_type, query, telemetry, surfaced_ids, outcome, error, latency_ms) -> dict`
  - `bot.interaction_log.log_interaction(log_dir: str, record: dict) -> None` (appends one JSON line to `<log_dir>/interactions.jsonl`)

- [ ] **Step 1: Write failing test `tests/test_interaction_log.py`**

```python
import json
from pathlib import Path
from bot import interaction_log as il

def test_classify_outcome():
    assert il.classify_outcome("boom", {}, []) == "error"
    assert il.classify_outcome(None, {"loop_exhausted": True}, []) == "loop_exhausted"
    assert il.classify_outcome(None, {"empty_search": True}, []) == "empty"
    assert il.classify_outcome(None, {"empty_search": True}, [{"id": "1"}]) == "ok"
    assert il.classify_outcome(None, {}, []) == "ok"

def test_build_record_has_fields():
    tel = {"tool_calls": [{"name": "dataset_info", "args": {}}], "iterations": 1,
           "llm_calls": 1, "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    rec = il.build_record(7, "text", "hi", tel, ["1"], "ok", None, 1234)
    assert rec["chat_id"] == 7 and rec["input"] == "text" and rec["query"] == "hi"
    assert rec["tool_calls"] == tel["tool_calls"]
    assert rec["outcome"] == "ok" and rec["listing_ids"] == ["1"] and rec["error"] is None
    assert rec["latency_ms"] == 1234 and rec["total_tokens"] == 15
    assert "ts" in rec

def test_log_interaction_writes_jsonl(tmp_path):
    d = str(tmp_path / "logs")
    il.log_interaction(d, {"a": 1})
    il.log_interaction(d, {"a": 2})
    lines = Path(d, "interactions.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(x)["a"] for x in lines] == [1, 2]
```

- [ ] **Step 2: Run test, verify it fails**

Run: `python3 -m pytest tests/test_interaction_log.py -v`
Expected: FAIL (`ModuleNotFoundError: bot.interaction_log`).

- [ ] **Step 3: Write `bot/interaction_log.py`**

```python
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def classify_outcome(error, telemetry: dict, surfaced: list) -> str:
    if error:
        return "error"
    if telemetry.get("loop_exhausted"):
        return "loop_exhausted"
    if telemetry.get("empty_search") and not surfaced:
        return "empty"
    return "ok"


def build_record(chat_id, input_type, query, telemetry, surfaced_ids,
                 outcome, error, latency_ms) -> dict:
    return {
        "ts": datetime.now(timezone.utc).isoformat(),
        "chat_id": chat_id,
        "input": input_type,
        "query": query,
        "tool_calls": telemetry.get("tool_calls", []),
        "iterations": telemetry.get("iterations", 0),
        "llm_calls": telemetry.get("llm_calls", 0),
        "outcome": outcome,
        "listing_ids": surfaced_ids,
        "error": error,
        "latency_ms": latency_ms,
        "prompt_tokens": telemetry.get("prompt_tokens", 0),
        "completion_tokens": telemetry.get("completion_tokens", 0),
        "total_tokens": telemetry.get("total_tokens", 0),
    }


def log_interaction(log_dir: str, record: dict) -> None:
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    with open(os.path.join(log_dir, "interactions.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")
```

- [ ] **Step 4: Run test, verify it passes**

Run: `python3 -m pytest tests/test_interaction_log.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add bot/interaction_log.py tests/test_interaction_log.py
git commit -m "feat(bot): structured interaction log"
```

---

### Task 5: Agent tool-calling loop

**Files:**
- Create: `bot/agent.py`
- Test: `tests/test_agent.py`

**Interfaces:**
- Consumes: `bot.tools.TOOLS`, `bot.tools.dispatch`, `processor.normalize.YEREVAN_DISTRICTS`.
- Produces:
  - `bot.agent.AgentResult` (dataclass) with `.text: str`, `.listings: list[dict]`, `.telemetry: dict`
  - `bot.agent.run(messages: list, conn, client, model: str, max_iters: int = 4) -> AgentResult`
  - `bot.agent.SYSTEM_PROMPT: str`
  - telemetry keys: `iterations`, `llm_calls`, `prompt_tokens`, `completion_tokens`, `total_tokens`, `tool_calls` (list of `{name,args}`), `empty_search` (bool), `loop_exhausted` (bool)

The loop calls `client.chat.completions.create(model=, messages=, tools=tools.TOOLS, tool_choice="auto")`. While the assistant message has `tool_calls`, it dispatches each, appends the assistant message and `tool` result messages, tracks the most recent `search_listings`/`get_listing` listings as `surfaced` (search capped at 5), and loops. When the assistant returns text (no tool calls), that text is the answer. On `max_iters` exhaustion, returns the surfaced listings with empty text and `loop_exhausted=True`.

- [ ] **Step 1: Write failing test `tests/test_agent.py`**

```python
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
```

- [ ] **Step 2: Run test, verify it fails**

Run: `python3 -m pytest tests/test_agent.py -v`
Expected: FAIL (`ModuleNotFoundError: bot.agent`).

- [ ] **Step 3: Write `bot/agent.py`**

```python
import json
from dataclasses import dataclass

from bot import tools
from processor.normalize import YEREVAN_DISTRICTS

SYSTEM_PROMPT = (
    "You are a friendly, concise assistant for apartment rentals in Yerevan. "
    "You help users explore a database of rental listings: searching, statistics "
    "(counts, average/min/max price or area), comparisons across districts, "
    "recommendations, and dataset/listing details. "
    "ALWAYS answer using the provided tools and the data they return — never "
    "invent listings, prices, or counts. Reply in the user's language. "
    "Prices are in AMD (֏) or USD ($). The known districts are: "
    + ", ".join(YEREVAN_DISTRICTS) + ". "
    "If a question cannot be answered from the listings data, you may give a "
    "brief general note, but explicitly say it is general knowledge, not from "
    "the listings. When you show specific listings, keep your text short — the "
    "listings are also shown to the user as photo cards."
)


@dataclass
class AgentResult:
    text: str
    listings: list
    telemetry: dict


def _accumulate_usage(tel: dict, resp) -> None:
    u = getattr(resp, "usage", None)
    if u is not None:
        tel["prompt_tokens"] += getattr(u, "prompt_tokens", 0) or 0
        tel["completion_tokens"] += getattr(u, "completion_tokens", 0) or 0
        tel["total_tokens"] += getattr(u, "total_tokens", 0) or 0


def run(messages: list, conn, client, model: str, max_iters: int = 4) -> AgentResult:
    tel = {"iterations": 0, "llm_calls": 0, "prompt_tokens": 0,
           "completion_tokens": 0, "total_tokens": 0, "tool_calls": [],
           "empty_search": False, "loop_exhausted": False}
    surfaced: list = []
    for i in range(max_iters):
        tel["iterations"] = i + 1
        resp = client.chat.completions.create(
            model=model, messages=messages, tools=tools.TOOLS, tool_choice="auto")
        tel["llm_calls"] += 1
        _accumulate_usage(tel, resp)
        msg = resp.choices[0].message
        tool_calls = getattr(msg, "tool_calls", None)
        if not tool_calls:
            return AgentResult(msg.content or "", surfaced, tel)
        messages.append(msg)
        for tc in tool_calls:
            name = tc.function.name
            try:
                args = json.loads(tc.function.arguments or "{}")
            except Exception:
                args = {}
            tel["tool_calls"].append({"name": name, "args": args})
            result = tools.dispatch(name, args, conn)
            if name == "search_listings":
                listings = result.get("listings", [])
                surfaced = listings[:5]
                if not listings:
                    tel["empty_search"] = True
            elif name == "get_listing":
                listing = result.get("listing")
                surfaced = [listing] if listing else []
            messages.append({"role": "tool", "tool_call_id": tc.id,
                             "content": json.dumps(result, ensure_ascii=False)})
    tel["loop_exhausted"] = True
    return AgentResult("", surfaced, tel)
```

- [ ] **Step 4: Run test, verify it passes**

Run: `python3 -m pytest tests/test_agent.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add bot/agent.py tests/test_agent.py
git commit -m "feat(bot): tool-calling agent loop"
```

---

### Task 6: Wire the agent into the Telegram bot

**Files:**
- Modify: `bot/main.py`
- Modify: `README.md`
- Manual verification (Telegram + live OpenAI); logic is covered by Tasks 2–5 tests.

**Interfaces:**
- Consumes: `common.config.load_config`, `db.database.connect`/`connect_ro`/`init_db`/`get_photos`, `bot.agent` (`run`, `SYSTEM_PROMPT`, `AgentResult`), `bot.conversation.Conversation`, `bot.interaction_log` (`classify_outcome`, `build_record`, `log_interaction`), `bot.openai_client.transcribe`, `bot.format.format_listing`.
- Produces: `bot.main.main()` runnable via `python -m bot.main`.

- [ ] **Step 1: Replace `bot/main.py` with the agent-wired version**

```python
import logging
import os
import tempfile
import time

from openai import OpenAI
from telegram import InputMediaPhoto, Update
from telegram.ext import (
    Application, CommandHandler, ContextTypes, MessageHandler,
    filters as tg_filters,
)

from common.config import load_config
from db import database
from bot import agent, interaction_log
from bot.conversation import Conversation
from bot.openai_client import transcribe
from bot.format import format_listing

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("housing_chat.bot")

WELCOME = ("Hi! I'm your Yerevan rentals helper. Ask me about apartments — "
           "prices, districts, comparisons, stats, or find listings. "
           "Text or voice, in any language.")


async def _send_results(update, conn, result) -> None:
    if result.text:
        await update.message.reply_text(result.text)
    for row in result.listings[:5]:
        if not row:
            continue
        rid = row.get("id")
        paths = []
        if rid:
            paths = [p["local_path"] for p in database.get_photos(conn, rid)
                     if p.get("local_path")][:3]
        caption = format_listing(row)
        if paths:
            handles = [open(p, "rb") for p in paths]
            try:
                media = [InputMediaPhoto(fh) for fh in handles]
                await update.message.reply_media_group(media=media, caption=caption)
            finally:
                for fh in handles:
                    fh.close()
        else:
            await update.message.reply_text(caption)


async def _handle(update, context, text: str, input_type: str) -> None:
    data = context.application.bot_data
    cfg = data["cfg"]
    conn = data["conn"]
    conv = data["conv"]
    chat_id = update.effective_chat.id
    log.info("query chat=%s input=%s text=%r", chat_id, input_type, text)
    messages = ([{"role": "system", "content": agent.SYSTEM_PROMPT}]
                + conv.history(chat_id)
                + [{"role": "user", "content": text}])
    t0 = time.time()
    error = None
    result = None
    try:
        result = agent.run(messages, conn, data["client"], cfg.chat_model, cfg.agent_max_iters)
    except Exception as e:
        log.exception("agent failed")
        error = str(e)
    latency_ms = int((time.time() - t0) * 1000)

    if error or result is None:
        await update.message.reply_text("Sorry, something went wrong. Please try again.")
        telemetry, surfaced_ids = {}, []
    else:
        if not result.text and not result.listings:
            result.text = "I couldn't find anything for that. Try rephrasing, or ask what data I have."
        await _send_results(update, conn, result)
        conv.append(chat_id, text, result.text)
        telemetry = result.telemetry
        surfaced_ids = [r.get("id") for r in result.listings if r]

    outcome = interaction_log.classify_outcome(error, telemetry, surfaced_ids)
    record = interaction_log.build_record(chat_id, input_type, text, telemetry,
                                          surfaced_ids, outcome, error, latency_ms)
    interaction_log.log_interaction(cfg.log_dir, record)
    log.info("answered chat=%s outcome=%s latency_ms=%s tokens=%s",
             chat_id, outcome, latency_ms, telemetry.get("total_tokens", 0))


async def handle_text(update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _handle(update, context, update.message.text, "text")


async def handle_voice(update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = context.application.bot_data
    tg_file = await update.message.voice.get_file()
    fd, path = tempfile.mkstemp(suffix=".oga")
    os.close(fd)
    try:
        await tg_file.download_to_drive(path)
        text = transcribe(path, data["client"], data["cfg"].stt_model)
    finally:
        os.unlink(path)
    await _handle(update, context, text, "voice")


async def cmd_start(update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.application.bot_data["conv"].clear(update.effective_chat.id)
    await update.message.reply_text(WELCOME)


async def cmd_clear(update, context: ContextTypes.DEFAULT_TYPE) -> None:
    context.application.bot_data["conv"].clear(update.effective_chat.id)
    await update.message.reply_text("Conversation reset.")


def main() -> None:
    cfg = load_config()
    rw = database.connect(cfg.db_path)
    database.init_db(rw)              # ensure schema exists
    ro = database.connect_ro(cfg.db_path)
    app = Application.builder().token(cfg.telegram_bot_token).build()
    app.bot_data.update({
        "cfg": cfg, "conn": ro,
        "client": OpenAI(api_key=cfg.openai_api_key),
        "conv": Conversation(cfg.history_max_turns),
    })
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("clear", cmd_clear))
    app.add_handler(MessageHandler(tg_filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(tg_filters.TEXT & ~tg_filters.COMMAND, handle_text))
    log.info("bot starting (long polling)")
    app.run_polling()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify it imports**

Run: `python3 -c "import bot.main; print('import ok')"`
Expected: prints `import ok`.

- [ ] **Step 3: Run the full suite (nothing else broke)**

Run: `python3 -m pytest -q`
Expected: PASS (old tests for service/parse_query/format still pass — they're removed in Task 7).

- [ ] **Step 4: Update `README.md`**

Replace the "Then message the bot…" line and the bot bullet in Notes to reflect the assistant. Under the pipeline step 3, add:

```markdown
The bot is a conversational assistant: ask for listings, stats ("average price
in Kentron"), comparisons, recommendations, or dataset info — text or voice, in
any language. It remembers recent context per chat; `/clear` resets it.
Interaction logs are written to `data/logs/interactions.jsonl` for analysis.
```

- [ ] **Step 5: Manual smoke (documented)**

With `.env` set and a populated `data/housing.db`: `python3 -m bot.main`, then in Telegram send "how many apartments do you have?", "average price in Kentron", "2 room flat in Arabkir", and a voice note. Expect natural answers, photo cards for searches, and lines appended to `data/logs/interactions.jsonl`. Record the outcome.

- [ ] **Step 6: Commit**

```bash
git add bot/main.py README.md
git commit -m "feat(bot): conversational agent in Telegram (memory, logging, /clear)"
```

---

### Task 7: Remove the retired single-shot query layer

**Files:**
- Delete: `bot/service.py`, `tests/test_service.py`
- Modify: `bot/filters.py`, `bot/format.py`, `bot/openai_client.py`
- Modify: `tests/test_filters.py`, `tests/test_format.py`, `tests/test_openai_client.py`

**Interfaces:**
- Produces: `bot/filters.py` keeps `Filters` (without `intent`), `_where_clause`, `build_query` (no `build_count_query`). `bot/format.py` keeps only `format_listing`. `bot/openai_client.py` keeps only `transcribe`.

- [ ] **Step 1: Delete the retired files**

```bash
git rm bot/service.py tests/test_service.py
```

- [ ] **Step 2: Trim `bot/filters.py`**

Remove the `intent` field from `Filters` (delete the line `intent: Literal["search", "count"] = "search"`). Delete the entire `build_count_query` function. Keep `Filters`, `_SORT_SQL`, `_where_clause`, `build_query`.

- [ ] **Step 3: Trim `bot/format.py`**

Delete `format_count` and `format_no_results`. Keep `_CURRENCY_SIGN` and `format_listing`.

- [ ] **Step 4: Trim `bot/openai_client.py`**

Delete `SYSTEM_PROMPT`, `parse_query`, and the `from bot.filters import Filters` and `from processor.normalize import YEREVAN_DISTRICTS` imports. Keep only:

```python
def transcribe(file_path: str, client, model: str) -> str:
    with open(file_path, "rb") as f:
        result = client.audio.transcriptions.create(model=model, file=f)
    return result.text
```

- [ ] **Step 5: Trim the obsolete tests**

- `tests/test_filters.py`: change the import to `from bot.filters import Filters, build_query`; delete `test_default_intent_is_search`, `test_build_count_query_no_filters`, `test_build_count_query_with_filters`.
- `tests/test_format.py`: change the import to `from bot.format import format_listing`; delete `test_no_results_message` and `test_format_count`.
- `tests/test_openai_client.py`: delete the `parse_query` tests and the `test_system_prompt_lists_canonical_districts` test and the `Filters` import; keep `test_transcribe` (and its `FakeClient`/imports needed for it).

- [ ] **Step 6: Run the full suite**

Run: `python3 -m pytest -q`
Expected: PASS, with no remaining references to removed symbols. If a collection error names a removed symbol, fix that test file.

- [ ] **Step 7: Verify the bot still imports**

Run: `python3 -c "import bot.main, bot.agent, bot.tools; print('ok')"`
Expected: prints `ok`.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m "refactor(bot): remove retired single-shot search/count layer"
```

---

## Self-Review notes (for the implementer)

- **Spec coverage:** tool-calling agent (Task 5) over four read-only tools (Task 2); multi-turn memory (Task 3); interaction logging with intents/dead-ends/cost (Task 4); Telegram wiring with `/clear`, language-grounded replies, card rendering, operational logging (Task 6); config (Task 1); retirement of the old layer incl. `Filters.intent`/`build_count_query`/`service.py`/`parse_query` (Task 7). Read-only safety: `connect_ro` (Task 2) used by the bot (Task 6).
- **Type consistency:** `AgentResult{text, listings, telemetry}` produced in Task 5, consumed in Task 6; telemetry keys (Task 5) match `classify_outcome`/`build_record` reads (Task 4); tool names in `TOOLS`/`dispatch` (Task 2) match the agent's `search_listings`/`get_listing` special-casing (Task 5).
- **Grounding:** the agent system prompt enforces tool-based answers + flagged general knowledge + user-language replies.
