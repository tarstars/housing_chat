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
