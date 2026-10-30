COUPONS = {"SAVE10": 0.10, "HALF": 0.50}


def apply_coupon(subtotal, code):
    if code is None:
        return subtotal
    if code not in COUPONS:
        raise ValueError(f"unknown coupon {code!r}")
    return subtotal * (1 - COUPONS[code])


def bulk_discount(item_count):
    """5% off for 10 or more items."""
    return 0.05 if item_count >= 10 else 0.0
