from decimal import ROUND_HALF_UP, Decimal


def round_cents(amount):
    """Round a dollar amount to whole cents, halves up."""
    return float(Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def format_price(amount, currency="USD"):
    symbol = {"USD": "$", "EUR": "€"}.get(currency, currency + " ")
    return f"{symbol}{amount:,.2f}"
