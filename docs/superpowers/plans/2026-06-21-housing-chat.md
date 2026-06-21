# Housing Chat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Telegram bot that answers text/voice queries (RU/EN/HY) about Yerevan apartment rentals, served from a locally-scraped list.am snapshot stored in SQLite.

**Architecture:** Three sequential, independently-runnable stages joined by one SQLite file. (1) A Playwright scraper passes list.am's Cloudflare challenge and writes a documented **raw-JSON** record per listing plus downloaded photos. (2) A processor normalizes those raw strings into typed SQLite rows. (3) A `python-telegram-bot` long-polling bot turns a query into OpenAI structured-output filters, runs parameterized SQL, and replies with text + photo media groups. Voice is transcribed with OpenAI Whisper first.

**Tech Stack:** Python 3.11+, Playwright (Chromium), BeautifulSoup + lxml, SQLite (stdlib `sqlite3`), OpenAI Python SDK (GPT structured outputs + Whisper), `python-telegram-bot` v21, Pydantic v2, python-dotenv, pytest.

## Global Constraints

- Python 3.11+.
- All AI via OpenAI only: chat model for query understanding, Whisper for STT.
- Scrape the **English** locale of list.am (`/en/…`) so attribute labels are English.
- Geographic scope: Yerevan rentals only. Listing type: apartments for rent.
- All SQL against `listings` must be **parameterized** (never string-interpolate user/LLM values).
- All secrets and tunables come from environment / `.env` (`OPENAI_API_KEY`, `TELEGRAM_BOT_TOKEN`, model names, paths, `RESULT_LIMIT`). `.env` is git-ignored; `.env.example` is committed.
- `data/raw/`, `data/housing.db`, and downloaded photos are git-ignored.
- Scraper, processor, and bot must each be runnable standalone via `python -m <pkg>.<module>`.
- Default result limit: 5 listings per reply; up to 3 photos per listing.

## Shared raw-listing JSON schema

The scraper writes one file `data/raw/<id>.json` per listing; the processor reads it. Both stages depend on exactly this shape:

```json
{
  "id": "12345678",
  "url": "https://www.list.am/en/item/12345678",
  "title": "2 room apartment for rent",
  "price_text": "$700",
  "attributes": {"Rooms": "2", "Floor area": "65 m²", "Floor": "3/9"},
  "address_text": "Yerevan, Kentron, Abovyan St",
  "description": "Sunny apartment ...",
  "photo_urls": ["https://s.list.am/.../1.jpg"],
  "photo_paths": ["data/raw/photos/12345678/0.jpg"],
  "scraped_at": "2026-06-21T10:00:00+00:00"
}
```

`attributes` keys are English labels as they appear on list.am (e.g. `Rooms`, `Floor area`, `Floor`). Any field may be missing; the processor handles absence.

## File structure

```
housing_chat/
  pyproject.toml            # deps + setuptools package list
  .env.example
  README.md
  common/
    __init__.py
    config.py               # load_config() -> Config
  db/
    __init__.py
    schema.sql              # CREATE TABLE/INDEX IF NOT EXISTS
    database.py             # connect/init/upsert/query/photos
  processor/
    __init__.py
    normalize.py            # parse_price/area/rooms/floor, extract_district
    process.py              # raw_to_row, process_raw_dir, main
  bot/
    __init__.py
    filters.py              # Filters (Pydantic) + build_query
    openai_client.py        # parse_query, transcribe
    format.py               # format_listing, format_no_results
    service.py              # answer() — orchestration, no Telegram
    main.py                 # Telegram handlers + run_polling
  scraper/
    __init__.py
    browser.py              # Playwright fetch (passes Cloudflare)
    extract.py              # html -> raw schema; url/pagination helpers
    crawl.py                # crawl driver + photo download + resume
    recon.py                # one-off: capture real fixtures
  tests/
    __init__.py
    fixtures/               # captured + synthetic html/json
    test_normalize.py
    test_process.py
    test_filters.py
    test_openai_client.py
    test_format.py
    test_service.py
    test_extract.py
```

---

### Task 1: Project scaffolding, config, packaging

**Files:**
- Create: `pyproject.toml`, `.env.example`, `common/__init__.py`, `common/config.py`, and empty `__init__.py` in `db/ processor/ bot/ scraper/ tests/`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `common.config.Config` (frozen dataclass) and `common.config.load_config() -> Config` with fields `openai_api_key, telegram_bot_token, chat_model, stt_model, db_path, raw_dir, photos_dir, result_limit`.

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "housing-chat"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "playwright>=1.44",
    "openai>=1.40",
    "python-telegram-bot>=21.0",
    "beautifulsoup4>=4.12",
    "lxml>=5.0",
    "pydantic>=2.6",
    "python-dotenv>=1.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[tool.setuptools]
packages = ["common", "db", "processor", "bot", "scraper"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Create package markers**

Create empty files: `common/__init__.py`, `db/__init__.py`, `processor/__init__.py`, `bot/__init__.py`, `scraper/__init__.py`, `tests/__init__.py`.

- [ ] **Step 3: Write `.env.example`**

```bash
OPENAI_API_KEY=sk-...
TELEGRAM_BOT_TOKEN=123456:ABC...
OPENAI_CHAT_MODEL=gpt-4o-mini
OPENAI_STT_MODEL=whisper-1
HOUSING_DB_PATH=data/housing.db
RAW_DIR=data/raw
PHOTOS_DIR=data/raw/photos
RESULT_LIMIT=5
```

- [ ] **Step 4: Write the failing test `tests/test_config.py`**

```python
from common.config import load_config

def test_load_config_defaults(monkeypatch):
    monkeypatch.delenv("OPENAI_CHAT_MODEL", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    cfg = load_config()
    assert cfg.openai_api_key == "k"
    assert cfg.chat_model == "gpt-4o-mini"
    assert cfg.stt_model == "whisper-1"
    assert cfg.result_limit == 5
```

- [ ] **Step 5: Run test, verify it fails**

Run: `pip install -e ".[dev]" && pytest tests/test_config.py -v`
Expected: FAIL (`ModuleNotFoundError: common.config`).

- [ ] **Step 6: Write `common/config.py`**

```python
import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    openai_api_key: str
    telegram_bot_token: str
    chat_model: str
    stt_model: str
    db_path: str
    raw_dir: str
    photos_dir: str
    result_limit: int


def load_config() -> Config:
    return Config(
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        chat_model=os.environ.get("OPENAI_CHAT_MODEL", "gpt-4o-mini"),
        stt_model=os.environ.get("OPENAI_STT_MODEL", "whisper-1"),
        db_path=os.environ.get("HOUSING_DB_PATH", "data/housing.db"),
        raw_dir=os.environ.get("RAW_DIR", "data/raw"),
        photos_dir=os.environ.get("PHOTOS_DIR", "data/raw/photos"),
        result_limit=int(os.environ.get("RESULT_LIMIT", "5")),
    )
```

- [ ] **Step 7: Run test, verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml .env.example common db processor bot scraper tests
git commit -m "feat: project scaffolding, packaging, and config loader"
```

---

### Task 2: SQLite schema + data-access layer

**Files:**
- Create: `db/schema.sql`, `db/database.py`
- Test: `tests/test_database.py`

**Interfaces:**
- Produces:
  - `db.database.connect(db_path: str) -> sqlite3.Connection` (row_factory=Row, `check_same_thread=False`, creates parent dir)
  - `db.database.init_db(conn) -> None`
  - `db.database.upsert_listing(conn, listing: dict) -> None` (keys = listings columns)
  - `db.database.replace_photos(conn, listing_id: str, photos: list[dict])` (each `{url, local_path, position}`)
  - `db.database.query_listings(conn, sql: str, params: list) -> list[dict]`
  - `db.database.get_photos(conn, listing_id: str) -> list[dict]`

- [ ] **Step 1: Write `db/schema.sql`**

```sql
CREATE TABLE IF NOT EXISTS listings (
  id            TEXT PRIMARY KEY,
  url           TEXT,
  title         TEXT,
  price         INTEGER,
  currency      TEXT,
  rooms         INTEGER,
  area_sqm      REAL,
  floor         INTEGER,
  total_floors  INTEGER,
  district      TEXT,
  address       TEXT,
  description   TEXT,
  posted_at     TEXT,
  scraped_at    TEXT
);
CREATE TABLE IF NOT EXISTS photos (
  listing_id    TEXT,
  url           TEXT,
  local_path    TEXT,
  position      INTEGER
);
CREATE INDEX IF NOT EXISTS idx_listings_price ON listings(price);
CREATE INDEX IF NOT EXISTS idx_listings_rooms ON listings(rooms);
CREATE INDEX IF NOT EXISTS idx_listings_area ON listings(area_sqm);
CREATE INDEX IF NOT EXISTS idx_listings_district ON listings(district);
CREATE INDEX IF NOT EXISTS idx_photos_listing ON photos(listing_id);
```

- [ ] **Step 2: Write failing test `tests/test_database.py`**

```python
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
```

- [ ] **Step 3: Run test, verify it fails**

Run: `pytest tests/test_database.py -v`
Expected: FAIL (`ModuleNotFoundError: db.database`).

- [ ] **Step 4: Write `db/database.py`**

```python
import sqlite3
from pathlib import Path

SCHEMA = (Path(__file__).with_name("schema.sql")).read_text(encoding="utf-8")

_COLUMNS = [
    "id", "url", "title", "price", "currency", "rooms", "area_sqm",
    "floor", "total_floors", "district", "address", "description",
    "posted_at", "scraped_at",
]


def connect(db_path: str) -> sqlite3.Connection:
    if db_path != ":memory:":
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def upsert_listing(conn: sqlite3.Connection, listing: dict) -> None:
    values = {c: listing.get(c) for c in _COLUMNS}
    placeholders = ", ".join(f":{c}" for c in _COLUMNS)
    updates = ", ".join(f"{c}=excluded.{c}" for c in _COLUMNS if c != "id")
    conn.execute(
        f"INSERT INTO listings ({', '.join(_COLUMNS)}) VALUES ({placeholders}) "
        f"ON CONFLICT(id) DO UPDATE SET {updates}",
        values,
    )
    conn.commit()


def replace_photos(conn: sqlite3.Connection, listing_id: str, photos: list[dict]) -> None:
    conn.execute("DELETE FROM photos WHERE listing_id = ?", (listing_id,))
    conn.executemany(
        "INSERT INTO photos (listing_id, url, local_path, position) "
        "VALUES (:listing_id, :url, :local_path, :position)",
        [{"listing_id": listing_id, **p} for p in photos],
    )
    conn.commit()


def query_listings(conn: sqlite3.Connection, sql: str, params: list) -> list[dict]:
    return [dict(r) for r in conn.execute(sql, params).fetchall()]


def get_photos(conn: sqlite3.Connection, listing_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT url, local_path, position FROM photos WHERE listing_id = ? ORDER BY position",
        (listing_id,),
    ).fetchall()
    return [dict(r) for r in rows]
```

- [ ] **Step 5: Run test, verify it passes**

Run: `pytest tests/test_database.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add db/schema.sql db/database.py tests/test_database.py
git commit -m "feat: sqlite schema and data-access layer"
```

---

### Task 3: Normalization functions (raw strings → typed values)

**Files:**
- Create: `processor/normalize.py`
- Test: `tests/test_normalize.py`

**Interfaces:**
- Produces:
  - `parse_price(text: str) -> tuple[int | None, str | None]` (amount, "AMD"|"USD"|None)
  - `parse_area(text: str) -> float | None`
  - `parse_rooms(text: str) -> int | None`
  - `parse_floor(text: str) -> tuple[int | None, int | None]` (floor, total)
  - `extract_district(address: str) -> str | None`
  - `YEREVAN_DISTRICTS: list[str]`

- [ ] **Step 1: Write failing test `tests/test_normalize.py`**

```python
import pytest
from processor import normalize as n

@pytest.mark.parametrize("text,amount,cur", [
    ("$700", 700, "USD"),
    ("700 $", 700, "USD"),
    ("1,200 USD", 1200, "USD"),
    ("450,000 ֏", 450000, "AMD"),
    ("450000 AMD", 450000, "AMD"),
    ("250 000 դրամ", 250000, "AMD"),
    ("", None, None),
])
def test_parse_price(text, amount, cur):
    assert n.parse_price(text) == (amount, cur)

@pytest.mark.parametrize("text,expected", [
    ("65 m²", 65.0), ("65.5 m2", 65.5), ("80", 80.0), ("", None),
])
def test_parse_area(text, expected):
    assert n.parse_area(text) == expected

@pytest.mark.parametrize("text,expected", [("2", 2), ("3 rooms", 3), ("", None)])
def test_parse_rooms(text, expected):
    assert n.parse_rooms(text) == expected

@pytest.mark.parametrize("text,floor,total", [
    ("3/9", 3, 9), ("3 of 9", 3, 9), ("5", 5, None), ("", None, None),
])
def test_parse_floor(text, floor, total):
    assert n.parse_floor(text) == (floor, total)

@pytest.mark.parametrize("addr,expected", [
    ("Yerevan, Kentron, Abovyan St", "Kentron"),
    ("Arabkir 41 street", "Arabkir"),
    ("Yerevan", None),
    ("", None),
])
def test_extract_district(addr, expected):
    assert n.extract_district(addr) == expected
```

- [ ] **Step 2: Run test, verify it fails**

Run: `pytest tests/test_normalize.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Write `processor/normalize.py`**

```python
import re

YEREVAN_DISTRICTS = [
    "Kentron", "Arabkir", "Avan", "Davtashen", "Erebuni",
    "Kanaker-Zeytun", "Malatia-Sebastia", "Nor Nork", "Nork-Marash",
    "Nubarashen", "Shengavit", "Ajapnyak",
]


def parse_price(text: str) -> tuple[int | None, str | None]:
    if not text:
        return (None, None)
    upper = text.upper()
    currency = None
    if "$" in text or "USD" in upper:
        currency = "USD"
    elif "֏" in text or "AMD" in upper or "ДРАМ" in upper or "ԴՐԱՄ" in text or "դրամ" in text:
        currency = "AMD"
    digits = re.sub(r"[^\d]", "", text)
    amount = int(digits) if digits else None
    return (amount, currency)


def parse_area(text: str) -> float | None:
    if not text:
        return None
    m = re.search(r"(\d+(?:[.,]\d+)?)", text)
    return float(m.group(1).replace(",", ".")) if m else None


def parse_rooms(text: str) -> int | None:
    if not text:
        return None
    m = re.search(r"\d+", text)
    return int(m.group()) if m else None


def parse_floor(text: str) -> tuple[int | None, int | None]:
    if not text:
        return (None, None)
    nums = re.findall(r"\d+", text)
    floor = int(nums[0]) if len(nums) >= 1 else None
    total = int(nums[1]) if len(nums) >= 2 else None
    return (floor, total)


def extract_district(address: str) -> str | None:
    if not address:
        return None
    low = address.lower()
    for d in YEREVAN_DISTRICTS:
        if d.lower() in low:
            return d
    return None
```

- [ ] **Step 4: Run test, verify it passes**

Run: `pytest tests/test_normalize.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add processor/normalize.py tests/test_normalize.py
git commit -m "feat: raw-string normalization helpers"
```

---

### Task 4: Processor pipeline (raw JSON dir → SQLite)

**Files:**
- Create: `processor/process.py`
- Test: `tests/test_process.py`

**Interfaces:**
- Consumes: `db.database`, `processor.normalize`, the shared raw-JSON schema.
- Produces:
  - `raw_to_row(raw: dict) -> dict` (keys = listings columns)
  - `is_complete(row: dict) -> bool`
  - `process_raw_dir(raw_dir: str, conn) -> tuple[int, int]` (written, skipped)
  - `main() -> None`

- [ ] **Step 1: Write failing test `tests/test_process.py`**

```python
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
```

- [ ] **Step 2: Run test, verify it fails**

Run: `pytest tests/test_process.py -v`
Expected: FAIL (`ModuleNotFoundError: processor.process`).

- [ ] **Step 3: Write `processor/process.py`**

```python
import json
from pathlib import Path

from db import database
from processor import normalize


def raw_to_row(raw: dict) -> dict:
    price, currency = normalize.parse_price(raw.get("price_text", ""))
    attrs = raw.get("attributes", {}) or {}
    rooms = normalize.parse_rooms(attrs.get("Rooms") or attrs.get("Number of rooms") or "")
    area = normalize.parse_area(attrs.get("Floor area") or attrs.get("Area") or "")
    floor, total = normalize.parse_floor(attrs.get("Floor") or "")
    address = raw.get("address_text") or ""
    return {
        "id": raw["id"], "url": raw.get("url"), "title": raw.get("title"),
        "price": price, "currency": currency, "rooms": rooms, "area_sqm": area,
        "floor": floor, "total_floors": total,
        "district": normalize.extract_district(address), "address": address,
        "description": raw.get("description"), "posted_at": raw.get("posted_text"),
        "scraped_at": raw.get("scraped_at"),
    }


def is_complete(row: dict) -> bool:
    return row.get("price") is not None and (
        row.get("rooms") is not None or row.get("area_sqm") is not None
    )


def process_raw_dir(raw_dir: str, conn) -> tuple[int, int]:
    written = skipped = 0
    for path in sorted(Path(raw_dir).glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        row = raw_to_row(raw)
        if not is_complete(row):
            skipped += 1
            continue
        database.upsert_listing(conn, row)
        urls = raw.get("photo_urls", []) or []
        paths = raw.get("photo_paths", []) or []
        photos = [
            {"url": u, "local_path": p, "position": i}
            for i, (u, p) in enumerate(zip(urls, paths))
        ]
        database.replace_photos(conn, row["id"], photos)
        written += 1
    return (written, skipped)


def main() -> None:
    from common.config import load_config
    cfg = load_config()
    conn = database.connect(cfg.db_path)
    database.init_db(conn)
    written, skipped = process_raw_dir(cfg.raw_dir, conn)
    print(f"processed: wrote {written}, skipped {skipped}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test, verify it passes**

Run: `pytest tests/test_process.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add processor/process.py tests/test_process.py
git commit -m "feat: processor pipeline from raw json to sqlite"
```

---

### Task 5: Filters model + SQL builder

**Files:**
- Create: `bot/filters.py`
- Test: `tests/test_filters.py`

**Interfaces:**
- Produces:
  - `bot.filters.Filters` — Pydantic v2 model, all fields optional: `min_price, max_price` (int), `currency` (`Literal["AMD","USD"]`), `min_rooms, max_rooms` (int), `min_area, max_area` (float), `district` (str), `sort` (`Literal["price_asc","price_desc","area_desc","newest"]`).
  - `bot.filters.build_query(f: Filters, limit: int) -> tuple[str, list]` — parameterized SQL + params; default sort `price_asc`.

- [ ] **Step 1: Write failing test `tests/test_filters.py`**

```python
from bot.filters import Filters, build_query

def test_empty_filters_select_all_default_sort():
    sql, params = build_query(Filters(), 5)
    assert "WHERE" not in sql
    assert "ORDER BY price ASC" in sql
    assert params == [5]

def test_filters_build_parameterized_where():
    f = Filters(max_price=800, currency="USD", min_rooms=2, district="Kentron", sort="price_desc")
    sql, params = build_query(f, 10)
    assert "price <= ?" in sql and "currency = ?" in sql
    assert "rooms >= ?" in sql and "district = ?" in sql
    assert "ORDER BY price DESC" in sql
    assert params == [800, "USD", 2, "Kentron", 10]

def test_area_bounds():
    f = Filters(min_area=50.0, max_area=90.0)
    sql, params = build_query(f, 5)
    assert "area_sqm >= ?" in sql and "area_sqm <= ?" in sql
    assert params == [50.0, 90.0, 5]
```

- [ ] **Step 2: Run test, verify it fails**

Run: `pytest tests/test_filters.py -v`
Expected: FAIL (`ModuleNotFoundError: bot.filters`).

- [ ] **Step 3: Write `bot/filters.py`**

```python
from typing import Literal, Optional
from pydantic import BaseModel


class Filters(BaseModel):
    min_price: Optional[int] = None
    max_price: Optional[int] = None
    currency: Optional[Literal["AMD", "USD"]] = None
    min_rooms: Optional[int] = None
    max_rooms: Optional[int] = None
    min_area: Optional[float] = None
    max_area: Optional[float] = None
    district: Optional[str] = None
    sort: Optional[Literal["price_asc", "price_desc", "area_desc", "newest"]] = None


_SORT_SQL = {
    "price_asc": "price ASC",
    "price_desc": "price DESC",
    "area_desc": "area_sqm DESC",
    "newest": "scraped_at DESC",
}


def build_query(f: Filters, limit: int) -> tuple[str, list]:
    clauses: list[str] = []
    params: list = []
    if f.min_price is not None:
        clauses.append("price >= ?"); params.append(f.min_price)
    if f.max_price is not None:
        clauses.append("price <= ?"); params.append(f.max_price)
    if f.currency:
        clauses.append("currency = ?"); params.append(f.currency)
    if f.min_rooms is not None:
        clauses.append("rooms >= ?"); params.append(f.min_rooms)
    if f.max_rooms is not None:
        clauses.append("rooms <= ?"); params.append(f.max_rooms)
    if f.min_area is not None:
        clauses.append("area_sqm >= ?"); params.append(f.min_area)
    if f.max_area is not None:
        clauses.append("area_sqm <= ?"); params.append(f.max_area)
    if f.district:
        clauses.append("district = ?"); params.append(f.district)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    order = " ORDER BY " + _SORT_SQL.get(f.sort or "price_asc", "price ASC")
    params.append(limit)
    return (f"SELECT * FROM listings{where}{order} LIMIT ?", params)
```

- [ ] **Step 4: Run test, verify it passes**

Run: `pytest tests/test_filters.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add bot/filters.py tests/test_filters.py
git commit -m "feat: filters model and parameterized sql builder"
```

---

### Task 6: OpenAI wrappers — query understanding + STT

**Files:**
- Create: `bot/openai_client.py`
- Test: `tests/test_openai_client.py`

**Interfaces:**
- Consumes: `bot.filters.Filters`.
- Produces:
  - `parse_query(text: str, client, model: str) -> Filters`
  - `transcribe(file_path: str, client, model: str) -> str`

Both take an OpenAI-like `client` so tests inject a fake. `parse_query` uses `client.beta.chat.completions.parse(..., response_format=Filters)` and returns `.choices[0].message.parsed`. `transcribe` uses `client.audio.transcriptions.create(model=..., file=<open file>)` and returns `.text`.

- [ ] **Step 1: Write failing test `tests/test_openai_client.py`**

```python
from types import SimpleNamespace
from bot.filters import Filters
from bot import openai_client

class FakeParse:
    def __init__(self, filters): self._f = filters; self.calls = {}
    def parse(self, *, model, messages, response_format):
        self.calls = {"model": model, "messages": messages, "rf": response_format}
        msg = SimpleNamespace(parsed=self._f)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])

class FakeClient:
    def __init__(self, filters):
        self._parser = FakeParse(filters)
        self.beta = SimpleNamespace(chat=SimpleNamespace(completions=self._parser))
        self.audio = SimpleNamespace(transcriptions=self)
        self.tr_args = {}
    def create(self, *, model, file):
        self.tr_args = {"model": model, "has_file": file is not None}
        return SimpleNamespace(text="hello world")

def test_parse_query_returns_filters_and_passes_model():
    f = Filters(max_price=800, currency="USD")
    client = FakeClient(f)
    out = openai_client.parse_query("rent under 800$", client, "gpt-4o-mini")
    assert out == f
    assert client._parser.calls["model"] == "gpt-4o-mini"
    assert client._parser.calls["rf"] is Filters
    assert client._parser.calls["messages"][-1]["content"] == "rent under 800$"

def test_transcribe(tmp_path):
    p = tmp_path / "a.oga"; p.write_bytes(b"x")
    client = FakeClient(Filters())
    text = openai_client.transcribe(str(p), client, "whisper-1")
    assert text == "hello world"
    assert client.tr_args == {"model": "whisper-1", "has_file": True}
```

- [ ] **Step 2: Run test, verify it fails**

Run: `pytest tests/test_openai_client.py -v`
Expected: FAIL (`ModuleNotFoundError: bot.openai_client`).

- [ ] **Step 3: Write `bot/openai_client.py`**

```python
from bot.filters import Filters

SYSTEM_PROMPT = (
    "You convert a user's apartment-rental search request into structured filters "
    "for a Yerevan rentals database. The user may write in Russian, English, or "
    "Armenian. Prices are AMD (֏) or USD ($). Only set a field the user clearly "
    "specifies; leave the rest null. If the user names a Yerevan district, set "
    "`district` to its English name (e.g. Kentron, Arabkir, Shengavit). Choose a "
    "`sort` only if the user implies one (e.g. 'cheapest' -> price_asc)."
)


def parse_query(text: str, client, model: str) -> Filters:
    completion = client.beta.chat.completions.parse(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": text},
        ],
        response_format=Filters,
    )
    return completion.choices[0].message.parsed


def transcribe(file_path: str, client, model: str) -> str:
    with open(file_path, "rb") as f:
        result = client.audio.transcriptions.create(model=model, file=f)
    return result.text
```

- [ ] **Step 4: Run test, verify it passes**

Run: `pytest tests/test_openai_client.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add bot/openai_client.py tests/test_openai_client.py
git commit -m "feat: openai query-understanding and whisper wrappers"
```

---

### Task 7: Reply formatting + answer service

**Files:**
- Create: `bot/format.py`, `bot/service.py`
- Test: `tests/test_format.py`, `tests/test_service.py`

**Interfaces:**
- Produces:
  - `bot.format.format_listing(row: dict) -> str`
  - `bot.format.format_no_results() -> str`
  - `bot.service.answer(query_text, conn, client, model: str, limit: int) -> list[dict]` where each item is `{"text": str, "photos": list[str]}` (≤3 photo paths).

- [ ] **Step 1: Write failing test `tests/test_format.py`**

```python
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
```

- [ ] **Step 2: Run test, verify it fails**

Run: `pytest tests/test_format.py -v`
Expected: FAIL (`ModuleNotFoundError: bot.format`).

- [ ] **Step 3: Write `bot/format.py`**

```python
_CURRENCY_SIGN = {"AMD": "֏", "USD": "$"}


def format_listing(row: dict) -> str:
    price = row.get("price")
    sign = _CURRENCY_SIGN.get(row.get("currency"), row.get("currency") or "")
    price_str = f"{price:,} {sign}".strip() if price is not None else "price n/a"
    parts = [f"🏠 {row.get('title') or 'Apartment'}", f"💰 {price_str}"]
    if row.get("rooms") is not None:
        parts.append(f"🛏 {row['rooms']} rooms")
    if row.get("area_sqm") is not None:
        parts.append(f"📐 {row['area_sqm']:g} m²")
    if row.get("district"):
        parts.append(f"📍 {row['district']}")
    if row.get("url"):
        parts.append(row["url"])
    return "\n".join(parts)


def format_no_results() -> str:
    return "No matching rentals found. Try relaxing the price, rooms, or area."
```

- [ ] **Step 4: Run `tests/test_format.py`, verify it passes**

Run: `pytest tests/test_format.py -v`
Expected: PASS.

- [ ] **Step 5: Write failing test `tests/test_service.py`**

```python
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
```

- [ ] **Step 6: Run test, verify it fails**

Run: `pytest tests/test_service.py -v`
Expected: FAIL (`ModuleNotFoundError: bot.service`).

- [ ] **Step 7: Write `bot/service.py`**

```python
from db import database
from bot import filters as filters_mod
from bot.openai_client import parse_query
from bot.format import format_listing


def answer(query_text: str, conn, client, model: str, limit: int) -> list[dict]:
    f = parse_query(query_text, client, model)
    sql, params = filters_mod.build_query(f, limit)
    rows = database.query_listings(conn, sql, params)
    results: list[dict] = []
    for row in rows:
        photos = database.get_photos(conn, row["id"])
        paths = [p["local_path"] for p in photos if p.get("local_path")][:3]
        results.append({"text": format_listing(row), "photos": paths})
    return results
```

- [ ] **Step 8: Run test, verify it passes**

Run: `pytest tests/test_service.py -v`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add bot/format.py bot/service.py tests/test_format.py tests/test_service.py
git commit -m "feat: reply formatting and answer orchestration service"
```

---

### Task 8: Telegram handlers + bot entry point

**Files:**
- Create: `bot/main.py`
- Manual verification only (Telegram + live OpenAI); no automated test (logic lives in tested `service.answer`).

**Interfaces:**
- Consumes: `common.config.load_config`, `db.database.connect`, `bot.service.answer`, `bot.openai_client.transcribe`, `bot.format.format_no_results`.
- Produces: `bot.main.main()` runnable via `python -m bot.main`.

- [ ] **Step 1: Write `bot/main.py`**

```python
import os
import tempfile

from openai import OpenAI
from telegram import InputMediaPhoto
from telegram.ext import (
    Application, ContextTypes, MessageHandler, filters as tg_filters,
)

from common.config import load_config
from db import database
from bot.service import answer
from bot.openai_client import transcribe
from bot.format import format_no_results


async def _send_results(update, results: list[dict]) -> None:
    if not results:
        await update.message.reply_text(format_no_results())
        return
    for r in results:
        if r["photos"]:
            media = [InputMediaPhoto(open(p, "rb")) for p in r["photos"]]
            await update.message.reply_media_group(media=media, caption=r["text"])
        else:
            await update.message.reply_text(r["text"])


async def handle_text(update, context: ContextTypes.DEFAULT_TYPE) -> None:
    data = context.application.bot_data
    results = answer(update.message.text, data["conn"], data["client"],
                     data["cfg"].chat_model, data["cfg"].result_limit)
    await _send_results(update, results)


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
    results = answer(text, data["conn"], data["client"],
                     data["cfg"].chat_model, data["cfg"].result_limit)
    await _send_results(update, results)


def main() -> None:
    cfg = load_config()
    conn = database.connect(cfg.db_path)
    app = Application.builder().token(cfg.telegram_bot_token).build()
    app.bot_data.update({
        "cfg": cfg, "conn": conn, "client": OpenAI(api_key=cfg.openai_api_key),
    })
    app.add_handler(MessageHandler(tg_filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(tg_filters.TEXT & ~tg_filters.COMMAND, handle_text))
    app.run_polling()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Verify it imports and builds without runtime errors**

Run: `python -c "import bot.main; print('ok')"`
Expected: prints `ok` (no import errors).

- [ ] **Step 3: Manual smoke (documented, run when a token + DB exist)**

With a populated `data/housing.db` and `.env` set, run `python -m bot.main`, then in Telegram send the bot a text query (e.g. "2 room flat in Kentron under 800$") and a voice message. Expected: a text reply per match with a photo media group. Note this is manual — record the outcome.

- [ ] **Step 4: Commit**

```bash
git add bot/main.py
git commit -m "feat: telegram long-polling bot entry point"
```

---

### Task 9: Scraper browser fetch + recon (capture real fixtures)

**Files:**
- Create: `scraper/browser.py`, `scraper/recon.py`
- Output: `tests/fixtures/item_sample.html`, `tests/fixtures/category_sample.html` (captured from the live site during recon)

**Interfaces:**
- Produces:
  - `scraper.browser.browser_page(headless: bool = True)` — context manager yielding a Playwright `page`.
  - `scraper.browser.fetch_html(page, url: str, wait_selector: str | None = None, timeout: int = 30000) -> str`
  - `scraper.recon.main()` — fetches the category page + one item page and saves them to `tests/fixtures/`.

This task is network-dependent and run locally once. Its deliverable is the captured fixtures (ground truth for Task 10) and confirmation of the real category URL and key selectors.

- [ ] **Step 1: Install Playwright browser**

Run: `python -m playwright install chromium`
Expected: Chromium downloaded.

- [ ] **Step 2: Write `scraper/browser.py`**

```python
from contextlib import contextmanager

from playwright.sync_api import sync_playwright

_UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


@contextmanager
def browser_page(headless: bool = True):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(user_agent=_UA, locale="en-US")
        page = context.new_page()
        try:
            yield page
        finally:
            context.close()
            browser.close()


def fetch_html(page, url: str, wait_selector: str | None = None,
               timeout: int = 30000) -> str:
    page.goto(url, timeout=timeout, wait_until="domcontentloaded")
    if wait_selector:
        page.wait_for_selector(wait_selector, timeout=timeout)
    else:
        page.wait_for_load_state("networkidle", timeout=timeout)
    return page.content()
```

- [ ] **Step 3: Write `scraper/recon.py`**

```python
from pathlib import Path

from scraper.browser import browser_page, fetch_html

# Apartments for rent in Yerevan. Confirm/adjust during recon by browsing
# list.am: pick "Apartments for rent", set place = Yerevan, copy the URL.
CATEGORY_URL = "https://www.list.am/en/category/56"

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"


def main() -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    with browser_page(headless=True) as page:
        cat_html = fetch_html(page, CATEGORY_URL)
        (FIXTURES / "category_sample.html").write_text(cat_html, encoding="utf-8")
        # Find the first item link and capture its detail page.
        import re
        m = re.search(r'href="(/(?:en/)?item/\d+)"', cat_html)
        if not m:
            print("No item link found — inspect category_sample.html and fix selectors.")
            return
        item_url = "https://www.list.am" + m.group(1)
        item_html = fetch_html(page, item_url)
        (FIXTURES / "item_sample.html").write_text(item_html, encoding="utf-8")
        print(f"Saved fixtures. Item: {item_url}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run recon to capture fixtures**

Run: `python -m scraper.recon`
Expected: prints "Saved fixtures." and writes `tests/fixtures/category_sample.html` and `tests/fixtures/item_sample.html`. If it reports the Cloudflare "Just a moment..." title is still present, increase the `timeout`, add a short `page.wait_for_timeout(4000)` after `goto`, and re-run. Open the saved item HTML and note the real selectors for title, price, the attribute rows, address, and images — these drive Task 10.

- [ ] **Step 5: Commit**

```bash
git add scraper/browser.py scraper/recon.py tests/fixtures/category_sample.html tests/fixtures/item_sample.html
git commit -m "feat: playwright fetch and recon fixture capture"
```

---

### Task 10: Scraper extraction (HTML → raw schema)

**Files:**
- Create: `scraper/extract.py`
- Test: `tests/test_extract.py`

**Interfaces:**
- Consumes: `tests/fixtures/item_sample.html`, `tests/fixtures/category_sample.html` from Task 9.
- Produces:
  - `extract.collect_listing_urls(category_html: str) -> list[str]`
  - `extract.next_page_url(category_html: str, current_url: str) -> str | None`
  - `extract.item_id(url: str) -> str`
  - `extract.extract_listing(html: str, url: str) -> dict` (returns the shared raw schema, minus `photo_paths`/`scraped_at` which the crawler adds)

The CSS selectors below are a starting point. The test asserts the **contract** (correct keys/types, id derived from URL, ≥1 item URL collected). Run it against the real captured fixture; where a selector yields empty/None, open `item_sample.html`, find the real class/structure, and adjust the selector until the contract test passes with sensible non-empty values. This is the normal red→green loop, not a placeholder.

- [ ] **Step 1: Write failing test `tests/test_extract.py`**

```python
from pathlib import Path
from scraper import extract

FIX = Path(__file__).parent / "fixtures"

def test_item_id_from_url():
    assert extract.item_id("https://www.list.am/en/item/12345678") == "12345678"

def test_collect_listing_urls_from_category():
    html = (FIX / "category_sample.html").read_text(encoding="utf-8")
    urls = extract.collect_listing_urls(html)
    assert len(urls) >= 1
    assert all("/item/" in u for u in urls)
    assert len(urls) == len(set(urls))  # deduped

def test_extract_listing_contract():
    html = (FIX / "item_sample.html").read_text(encoding="utf-8")
    url = "https://www.list.am/en/item/12345678"
    raw = extract.extract_listing(html, url)
    assert raw["id"] == "12345678"
    assert raw["url"] == url
    assert isinstance(raw["attributes"], dict)
    assert isinstance(raw["photo_urls"], list)
    # At least a title or a price must be recovered from a real page.
    assert raw["title"] or raw["price_text"]
```

- [ ] **Step 2: Run test, verify it fails**

Run: `pytest tests/test_extract.py -v`
Expected: FAIL (`ModuleNotFoundError: scraper.extract`).

- [ ] **Step 3: Write `scraper/extract.py`**

```python
import re

from bs4 import BeautifulSoup

BASE = "https://www.list.am"


def item_id(url: str) -> str:
    m = re.search(r"/item/(\d+)", url)
    return m.group(1) if m else url.rstrip("/").split("/")[-1]


def _abs(href: str) -> str:
    return BASE + href if href.startswith("/") else href


def collect_listing_urls(category_html: str) -> list[str]:
    soup = BeautifulSoup(category_html, "lxml")
    out, seen = [], set()
    for a in soup.select("a[href*='/item/']"):
        href = a.get("href")
        if not href:
            continue
        url = _abs(href)
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


def next_page_url(category_html: str, current_url: str) -> str | None:
    soup = BeautifulSoup(category_html, "lxml")
    nxt = soup.select_one("a.next, a[rel='next'], .dlf a:last-child")
    if nxt and nxt.get("href"):
        return _abs(nxt["href"])
    return None


def extract_listing(html: str, url: str) -> dict:
    soup = BeautifulSoup(html, "lxml")

    title_el = soup.select_one("h1")
    title = title_el.get_text(strip=True) if title_el else None

    price_el = soup.select_one(".price, [itemprop='price'], .pr")
    price_text = price_el.get_text(" ", strip=True) if price_el else ""

    attributes: dict[str, str] = {}
    for row in soup.select(".attr, .attributes .row, table.attr tr"):
        label = row.select_one(".t, .label, td:first-child, dt")
        value = row.select_one(".i, .value, td:last-child, dd")
        if label and value:
            key = label.get_text(strip=True)
            if key:
                attributes[key] = value.get_text(" ", strip=True)

    addr_el = soup.select_one(".address, [itemprop='address'], .loc")
    address_text = addr_el.get_text(" ", strip=True) if addr_el else None

    desc_el = soup.select_one("[itemprop='description'], .body, .desc, #desc")
    description = desc_el.get_text("\n", strip=True) if desc_el else None

    photo_urls: list[str] = []
    for img in soup.select(".images img, .gallery img, [itemprop='image']"):
        src = img.get("src") or img.get("data-src") or img.get("content")
        if src:
            photo_urls.append(_abs(src) if src.startswith("/") else src)

    return {
        "id": item_id(url),
        "url": url,
        "title": title,
        "price_text": price_text,
        "attributes": attributes,
        "address_text": address_text,
        "description": description,
        "photo_urls": photo_urls,
    }
```

- [ ] **Step 4: Run test against the real fixtures; tune selectors until green**

Run: `pytest tests/test_extract.py -v`
Expected: PASS. If `collect_listing_urls` returns 0 or `extract_listing` yields empty title and price, open the captured fixtures, identify the real selectors, edit them in `extract.py`, and re-run until all three tests pass with non-empty values.

- [ ] **Step 5: Commit**

```bash
git add scraper/extract.py tests/test_extract.py
git commit -m "feat: scraper html extraction to raw schema"
```

---

### Task 11: Crawl driver + photo download + resume

**Files:**
- Create: `scraper/crawl.py`
- Test: `tests/test_crawl.py` (offline parts only)

**Interfaces:**
- Consumes: `scraper.browser`, `scraper.extract`.
- Produces:
  - `download_photos(context, photo_urls: list[str], dest_dir: str, max_n: int = 5) -> list[str]`
  - `crawl(category_url, raw_dir, photos_dir, max_listings, delay=2.0, headless=True) -> int`
  - `main()` runnable via `python -m scraper.crawl`. Reads `MAX_LISTINGS` env (default 200).

Resume: an item whose `<raw_dir>/<id>.json` already exists is skipped. Photos are fetched through the Playwright context (`context.request.get`) so they reuse the Cloudflare cookie.

- [ ] **Step 1: Write failing test `tests/test_crawl.py`**

```python
import json
from pathlib import Path
from scraper import crawl

class FakeResp:
    def __init__(self, ok, body): self._ok = ok; self._body = body
    @property
    def ok(self): return self._ok
    def body(self): return self._body

class FakeContext:
    def __init__(self): self.request = self
    def get(self, url, timeout=20000):
        return FakeResp(True, b"\xff\xd8\xff")  # minimal jpeg-ish bytes

def test_download_photos_limits_and_writes(tmp_path):
    ctx = FakeContext()
    urls = [f"http://x/{i}.jpg" for i in range(10)]
    paths = crawl.download_photos(ctx, urls, str(tmp_path), max_n=3)
    assert len(paths) == 3
    assert all(Path(p).exists() for p in paths)

def test_should_skip_existing(tmp_path):
    (tmp_path / "1.json").write_text("{}")
    assert crawl.already_scraped(str(tmp_path), "1") is True
    assert crawl.already_scraped(str(tmp_path), "2") is False
```

- [ ] **Step 2: Run test, verify it fails**

Run: `pytest tests/test_crawl.py -v`
Expected: FAIL (`ModuleNotFoundError: scraper.crawl`).

- [ ] **Step 3: Write `scraper/crawl.py`**

```python
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from scraper.browser import browser_page, fetch_html
from scraper import extract


def already_scraped(raw_dir: str, item_id: str) -> bool:
    return (Path(raw_dir) / f"{item_id}.json").exists()


def download_photos(context, photo_urls: list[str], dest_dir: str,
                    max_n: int = 5) -> list[str]:
    Path(dest_dir).mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    for i, url in enumerate(photo_urls[:max_n]):
        try:
            resp = context.request.get(url, timeout=20000)
            if resp.ok:
                p = os.path.join(dest_dir, f"{i}.jpg")
                Path(p).write_bytes(resp.body())
                paths.append(p)
        except Exception:
            continue
    return paths


def crawl(category_url: str, raw_dir: str, photos_dir: str, max_listings: int,
          delay: float = 2.0, headless: bool = True) -> int:
    Path(raw_dir).mkdir(parents=True, exist_ok=True)
    collected = 0
    with browser_page(headless=headless) as page:
        url = category_url
        while url and collected < max_listings:
            html = fetch_html(page, url)
            for item_url in extract.collect_listing_urls(html):
                if collected >= max_listings:
                    break
                item_id = extract.item_id(item_url)
                if already_scraped(raw_dir, item_id):
                    continue
                item_html = fetch_html(page, item_url)
                raw = extract.extract_listing(item_html, item_url)
                raw["scraped_at"] = datetime.now(timezone.utc).isoformat()
                photo_dir = os.path.join(photos_dir, item_id)
                raw["photo_paths"] = download_photos(
                    page.context, raw.get("photo_urls", []), photo_dir)
                (Path(raw_dir) / f"{item_id}.json").write_text(
                    json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
                collected += 1
                time.sleep(delay)
            url = extract.next_page_url(html, url)
    return collected


def main() -> None:
    from common.config import load_config
    from scraper.recon import CATEGORY_URL
    cfg = load_config()
    max_listings = int(os.environ.get("MAX_LISTINGS", "200"))
    n = crawl(CATEGORY_URL, cfg.raw_dir, cfg.photos_dir, max_listings)
    print(f"scraped {n} listings into {cfg.raw_dir}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test, verify it passes**

Run: `pytest tests/test_crawl.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Live smoke run (small cap)**

Run: `MAX_LISTINGS=5 python -m scraper.crawl`
Expected: writes ~5 files under `data/raw/*.json`, each with non-empty `attributes`/`price_text` and downloaded photos under `data/raw/photos/<id>/`. Open one JSON to confirm fields look right. If empty, revisit Task 10 selectors.

- [ ] **Step 6: Commit**

```bash
git add scraper/crawl.py tests/test_crawl.py
git commit -m "feat: crawl driver with photo download and resume"
```

---

### Task 12: README, .gitignore check, end-to-end integration test

**Files:**
- Create: `README.md`, `tests/test_integration.py`
- Verify: `.gitignore` already excludes `data/` artifacts and `.env` (created during brainstorming).

**Interfaces:**
- Consumes: all prior modules.

- [ ] **Step 1: Write failing integration test `tests/test_integration.py`**

```python
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
```

- [ ] **Step 2: Run test, verify it fails then passes**

Run: `pytest tests/test_integration.py -v`
Expected: PASS (all modules already exist). If it fails, fix the offending module.

- [ ] **Step 3: Write `README.md`**

````markdown
# Housing Chat

Telegram bot answering text/voice queries (RU/EN/HY) about Yerevan apartment
rentals, served from a local list.am snapshot in SQLite.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
python -m playwright install chromium
cp .env.example .env   # then fill in OPENAI_API_KEY and TELEGRAM_BOT_TOKEN
```

## Pipeline (run locally, in order)

```bash
# 1. Scrape a snapshot (run on your own machine — residential IP passes Cloudflare)
MAX_LISTINGS=200 python -m scraper.crawl

# 2. Normalize raw JSON into data/housing.db
python -m processor.process

# 3. Run the bot (long polling — no public IP needed)
python -m bot.main
```

Then message the bot in Telegram, e.g. "2-room flat in Kentron under 800$",
or send a voice message.

## Tests

```bash
pytest
```

## Notes

- list.am is behind Cloudflare; the scraper uses a real Chromium via Playwright.
- All AI is OpenAI: a chat model for query understanding, Whisper for STT.
- Re-running the scraper resumes (skips already-saved listing IDs).
````

- [ ] **Step 4: Run the full test suite**

Run: `pytest -v`
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add README.md tests/test_integration.py
git commit -m "docs: readme and end-to-end integration test"
```

---

## Self-Review notes (for the implementer)

- **Spec coverage:** scrape (Tasks 9–11), Cloudflare via Playwright (Task 9), process→SQLite (Tasks 2–4), data model (Task 2), query understanding (Task 6), parameterized SQL (Task 5), STT (Task 6), text+photo replies (Tasks 7–8), error handling (resume/skip in Tasks 4 & 11; no-results in Task 7; temp-file cleanup in Task 8), tests (every logic task), local hosting (README). All spec sections map to a task.
- **Known risk:** the exact list.am category URL and CSS selectors are confirmed in Task 9's recon and finalized in Task 10's red→green loop against the captured fixture. Treat selector tuning as expected work, not a deviation.
- **Photos:** downloaded during the crawl through the Playwright context (Task 11) so they reuse the Cloudflare cookie; the bot sends local files only (Tasks 7–8).
