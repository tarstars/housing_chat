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


def _where_clause(f: Filters) -> tuple[str, list]:
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
    return where, params


def build_query(f: Filters, limit: int) -> tuple[str, list]:
    where, params = _where_clause(f)
    order = " ORDER BY " + _SORT_SQL.get(f.sort or "price_asc", "price ASC")
    return (f"SELECT * FROM listings{where}{order} LIMIT ?", params + [limit])


