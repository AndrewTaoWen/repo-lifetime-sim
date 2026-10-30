import pytest

from shopkit.cart import Cart
from shopkit.catalog import Catalog


class TestCart:
    @classmethod
    def setup_class(cls):
        # built once for the whole class: every test below depends on Catalog.add
        cls.catalog = Catalog()
        cls.catalog.add("pen", 1.50)
        cls.catalog.add("book", 12.00)

    def test_item_count(self):
        cart = Cart(self.catalog)
        cart.add("pen", 3)
        assert cart.item_count() == 3

    def test_subtotal(self):
        cart = Cart(self.catalog)
        cart.add("pen", 2)
        cart.add("book")
        assert cart.subtotal() == 15.00

    def test_unknown_sku(self):
        with pytest.raises(KeyError):
            Cart(self.catalog).add("lamp")
