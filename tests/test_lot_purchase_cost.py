"""Tests for purchase amounts recorded directly on material deliveries."""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from dj_craft_tally.models import BlueprintMaterialRequirement, Currency, MaterialLot


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


@pytest.mark.django_db
def test_blueprint_cost_uses_newest_lots_and_previous_lot_for_shortfall(
    blueprint, material
) -> None:
    blueprint.output_quantity = Decimal("2")
    blueprint.save(update_fields=["output_quantity"])
    BlueprintMaterialRequirement.objects.create(
        blueprint=blueprint, material=material, quantity=Decimal("500")
    )
    currency = Currency.objects.get(code="GBP")
    MaterialLot.objects.create(
        material=material,
        quantity_per_package=100,
        received_at="2026-01-01T00:00Z",
        purchase_amount=Decimal("10"),
        purchase_currency=currency,
    )
    MaterialLot.objects.create(
        material=material,
        package_count=4,
        quantity_per_package=100,
        received_at="2026-02-01T00:00Z",
        purchase_amount=Decimal("40"),
        purchase_currency=currency,
    )

    assert blueprint.cost_per_output_unit() == {"GBP": Decimal("25")}


@pytest.mark.django_db
def test_blueprint_cost_returns_empty_when_lots_cannot_cover_requirement(
    blueprint, material
) -> None:
    BlueprintMaterialRequirement.objects.create(
        blueprint=blueprint, material=material, quantity=Decimal("500")
    )
    MaterialLot.objects.create(
        material=material,
        quantity_per_package=100,
        purchase_amount=Decimal("10"),
        purchase_currency=Currency.objects.get(code="GBP"),
    )

    assert blueprint.cost_per_output_unit() == {}
