from bot.filters import Filters, build_query, build_count_query

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

def test_default_intent_is_search():
    assert Filters().intent == "search"

def test_build_count_query_no_filters():
    sql, params = build_count_query(Filters())
    assert "count(*)" in sql.lower()
    assert "WHERE" not in sql and "ORDER BY" not in sql and "LIMIT" not in sql
    assert params == []

def test_build_count_query_with_filters():
    sql, params = build_count_query(Filters(district="Kentron", min_rooms=2))
    assert "count(*)" in sql.lower()
    assert "district = ?" in sql and "rooms >= ?" in sql
    assert "LIMIT" not in sql
    assert params == [2, "Kentron"]
