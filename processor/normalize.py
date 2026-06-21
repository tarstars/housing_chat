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
