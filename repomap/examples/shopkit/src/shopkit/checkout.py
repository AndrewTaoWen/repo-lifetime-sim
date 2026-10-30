from .discounts import apply_coupon, bulk_discount
from .money import format_price, round_cents
from .tax import tax_for


def total(cart, region, coupon=None):
    amount = apply_coupon(cart.subtotal(), coupon)
    amount *= 1 - bulk_discount(cart.item_count())
    return round_cents(amount + tax_for(amount, region))


def receipt(cart, region, coupon=None):
    lines = [f"{sku} x{qty}" for sku, qty in sorted(cart.lines.items())]
    lines.append(f"Total: {format_price(total(cart, region, coupon))}")
    return "\n".join(lines)
