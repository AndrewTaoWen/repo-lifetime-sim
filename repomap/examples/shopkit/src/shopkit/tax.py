from .money import round_cents

RATES = {"CA": 0.0725, "NY": 0.04, "OR": 0.0}


def tax_for(amount, region):
    return round_cents(amount * RATES.get(region, 0.05))
