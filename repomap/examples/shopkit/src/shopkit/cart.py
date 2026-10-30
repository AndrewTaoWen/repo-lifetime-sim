class Cart:
    def __init__(self, catalog):
        self.catalog = catalog
        self.lines = {}

    def add(self, sku, qty=1):
        if sku not in self.catalog:
            raise KeyError(sku)
        self.lines[sku] = self.lines.get(sku, 0) + qty

    def item_count(self):
        return sum(self.lines.values())

    def subtotal(self):
        return sum(self.catalog.price_of(sku) * qty for sku, qty in self.lines.items())
