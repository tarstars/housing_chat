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

def test_period_filter():
    sql, params = build_query(Filters(period="daily"), 5)
    assert "period = ?" in sql
    assert params == ["daily", 5]

def test_area_bounds():
    f = Filters(min_area=50.0, max_area=90.0)
    sql, params = build_query(f, 5)
    assert "area_sqm >= ?" in sql and "area_sqm <= ?" in sql
    assert params == [50.0, 90.0, 5]
