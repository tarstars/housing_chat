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


def connect_ro(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, check_same_thread=False)
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
