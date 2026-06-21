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
_FILTER_KEYS = ("min_price", "max_price", "currency", "period", "min_rooms",
                "max_rooms", "min_area", "max_area", "district")
_ROW_COLS = ("id", "price", "currency", "period", "rooms", "area_sqm", "floor",
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
        "period": {"type": "string", "enum": ["monthly", "daily", "weekly"]},
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
