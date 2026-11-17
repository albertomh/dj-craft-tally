"""Tests for reusable domain services."""

from datetime import date
from decimal import Decimal

import pytest

from dj_craft_tally.models import Currency, MaterialLot
from dj_craft_tally.services import expenditure_periods


@pytest.mark.django_db
def test_expenditure_periods_group_purchase_amounts_by_currency_and_window(material):
    gbp = Currency.objects.get(code="GBP")
    eur = Currency.objects.get(code="EUR")
    lots = [
        ("2026-01-01T00:00Z", "1.00", gbp),
        ("2026-04-01T00:00Z", "2.00", gbp),
        ("2026-11-08T00:00Z", "4.00", eur),
        ("2026-11-09T00:00Z", "8.00", gbp),
    ]
    for received_at, amount, currency in lots:
        MaterialLot.objects.create(
            material=material,
            quantity_per_package=1,
            received_at=received_at,
            purchase_amount=Decimal(amount),
            purchase_currency=currency,
        )

    periods = expenditure_periods(as_of=date(2026, 11, 16))

    assert periods == [
        {"key": "last_week", "label": "Last week", "totals": {"GBP": Decimal("8.00")}},
        {
            "key": "quarter",
            "label": "Current quarter",
            "totals": {"EUR": Decimal("4.00"), "GBP": Decimal("8.00")},
        },
        {
            "key": "ytd",
            "label": "Year to date",
            "totals": {
                "EUR": Decimal("4.00"),
                "GBP": Decimal("11.00"),
            },
        },
    ]


@pytest.mark.django_db
def test_expenditure_periods_ignore_unpriced_and_zero_value_lots(material):
    gbp = Currency.objects.get(code="GBP")
    MaterialLot.objects.create(
        material=material,
        quantity_per_package=1,
        received_at="2026-11-16T00:00Z",
    )
    MaterialLot.objects.create(
        material=material,
        quantity_per_package=1,
        received_at="2026-11-16T00:00Z",
        purchase_amount=Decimal("0.00"),
        purchase_currency=gbp,
    )

    periods = expenditure_periods(as_of=date(2026, 11, 16))
    assert all(not period["totals"] for period in periods)
