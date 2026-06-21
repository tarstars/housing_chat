from db import database
from bot import filters as filters_mod
from bot.openai_client import parse_query
from bot.format import format_listing, format_count


def answer(query_text: str, conn, client, model: str, limit: int) -> list[dict]:
    f = parse_query(query_text, client, model)
    if f.intent == "count":
        sql, params = filters_mod.build_count_query(f)
        n = database.query_listings(conn, sql, params)[0]["n"]
        return [{"text": format_count(n, bool(params)), "photos": []}]
    sql, params = filters_mod.build_query(f, limit)
    rows = database.query_listings(conn, sql, params)
    results: list[dict] = []
    for row in rows:
        photos = database.get_photos(conn, row["id"])
        paths = [p["local_path"] for p in photos if p.get("local_path")][:3]
        results.append({"text": format_listing(row), "photos": paths})
    return results
