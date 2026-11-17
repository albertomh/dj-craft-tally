"""Tests for purchase amounts recorded directly on material deliveries."""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from dj_craft_tally.models import Currency, MaterialLot


@pytest.mark.django_db
def test_lot_purchase_amount_is_optional_and_has_a_currency(material) -> None:
    unpriced_lot = MaterialLot.objects.create(material=material, quantity_per_package=1)
    priced_lot = MaterialLot.objects.create(
        material=material,
        quantity_per_package=1,
        purchase_amount=Decimal("12.50"),
        purchase_currency=Currency.objects.get(code="EUR"),
    )

    assert unpriced_lot.purchase_amount is None
    assert unpriced_lot.purchase_currency is None
    assert priced_lot.purchase_amount == Decimal("12.50")
    assert priced_lot.purchase_currency_id == "EUR"


@pytest.mark.django_db
def test_lot_purchase_amount_and_currency_must_be_recorded_together(material) -> None:
    with pytest.raises(ValidationError, match="Select the currency"):
        MaterialLot.objects.create(
            material=material,
            quantity_per_package=1,
            purchase_amount=Decimal("12.50"),
        )

    with pytest.raises(ValidationError, match="Enter the amount"):
        MaterialLot.objects.create(
            material=material,
            quantity_per_package=1,
            purchase_currency=Currency.objects.get(code="GBP"),
        )

    with pytest.raises(ValidationError, match="greater than or equal to"):
        MaterialLot.objects.create(
            material=material,
            quantity_per_package=1,
            purchase_amount=Decimal("-0.01"),
            purchase_currency=Currency.objects.get(code="GBP"),
        )
