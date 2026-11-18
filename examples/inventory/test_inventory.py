from app import list_products


def test_catalog_contains_products():
    assert "desk-lamp" in list_products()
