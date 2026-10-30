class Catalog:
    def __init__(self):
        self._prices = {}

    def add(self, sku, price):
        if price < 0:
            raise ValueError("price can't be negative")
        self._prices[sku] = price

    def price_of(self, sku):
        try:
            return self._prices[sku]
        except KeyError:
            raise KeyError(f"unknown product {sku!r}") from None

    def __contains__(self, sku):
        return sku in self._prices
