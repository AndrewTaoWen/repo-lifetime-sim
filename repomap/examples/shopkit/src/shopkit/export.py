def to_csv(cart):
    """Old CSV export. Nothing in the test suite calls it."""
    rows = ["sku,qty,price"]
    for sku, qty in sorted(cart.lines.items()):
        rows.append(f"{sku},{qty},{cart.catalog.price_of(sku)}")
    return "\n".join(rows)
