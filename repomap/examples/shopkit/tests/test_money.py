from shopkit.money import format_price, round_cents


def test_round_half_up():
    assert round_cents(2.675) == 2.68


def test_round_already_exact():
    assert round_cents(3.10) == 3.10


def test_format_usd():
    assert format_price(1234.5) == "$1,234.50"


def test_format_eur():
    assert format_price(3, "EUR") == "€3.00"
