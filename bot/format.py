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


def format_count(n: int, filtered: bool = False) -> str:
    noun = "apartment listing" if n == 1 else "apartment listings"
    if filtered:
        return f"I have {n} {noun} matching your criteria."
    return f"I currently have {n} {noun} in the database."
