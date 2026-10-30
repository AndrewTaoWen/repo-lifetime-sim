import pytest

from shopkit.catalog import Catalog


def test_add_and_price():
    c = Catalog()
    c.add("pen", 1.5)
    assert c.price_of("pen") == 1.5


def test_negative_price_rejected():
    with pytest.raises(ValueError):
        Catalog().add("pen", -1)


def test_unknown_product():
    with pytest.raises(KeyError):
        Catalog().price_of("nope")
