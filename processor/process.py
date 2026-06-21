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
        "description": raw.get("description"), "posted_at": raw.get("posted_at"),
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
