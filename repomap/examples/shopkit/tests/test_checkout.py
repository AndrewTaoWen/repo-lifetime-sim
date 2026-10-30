import pytest

from shopkit.cart import Cart
from shopkit.catalog import Catalog
from shopkit.checkout import receipt, total


@pytest.fixture
def cart():
    catalog = Catalog()
    catalog.add("pen", 1.50)
    catalog.add("book", 12.00)
    c = Cart(catalog)
    c.add("book", 2)
    return c


def test_total_with_tax(cart):
    assert total(cart, "CA") == 25.74


def test_total_no_tax_region(cart):
    assert total(cart, "OR") == 24.00


def test_total_with_coupon(cart):
    assert total(cart, "OR", "HALF") == 12.00


def test_receipt(cart):
    assert receipt(cart, "NY") == "book x2\nTotal: $24.96"
