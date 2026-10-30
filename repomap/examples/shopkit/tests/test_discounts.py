import pytest

from shopkit.discounts import apply_coupon, bulk_discount


def test_coupon():
    assert apply_coupon(100, "SAVE10") == 90


def test_no_coupon():
    assert apply_coupon(100, None) == 100


def test_bad_coupon():
    with pytest.raises(ValueError):
        apply_coupon(100, "FREE")


def test_bulk_threshold():
    assert bulk_discount(9) == 0.0
    assert bulk_discount(10) == 0.05
