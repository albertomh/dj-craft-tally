"""Tests for purchase amounts recorded directly on material deliveries."""

from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from dj_craft_tally.models import (
    Blueprint,
    BlueprintMaterialRequirement,
    Currency,
    InventoryTransaction,
    InventoryTransactionLine,
    Material,
    MaterialLot,
)


@pytest.mark.django_db
def test_zero_output_has_no_cost_estimate(blueprint: Blueprint):
    blueprint.output_quantity = Decimal("0")

    result = blueprint.cost_per_output_unit()

    assert result.cost_per_unit == {}
    assert result.usages == ()


@pytest.mark.django_db
def test_lot_purchase_amount_is_optional_and_has_a_currency(material: Material) -> None:
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
def test_lot_purchase_amount_and_currency_must_be_recorded_together(
    material: Material,
) -> None:
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
def test_blueprint_cost_uses_oldest_lot_then_newer_lot_for_shortfall(
    blueprint: Blueprint, material: Material
) -> None:
    blueprint.output_quantity = Decimal("2")
    blueprint.save(update_fields=["output_quantity"])
    BlueprintMaterialRequirement.objects.create(
        blueprint=blueprint, material=material, quantity=Decimal("500")
    )
    currency = Currency.objects.get(code="GBP")
    oldest = MaterialLot.objects.create(
        material=material,
        quantity_per_package=100,
        received_at="2026-01-01T00:00Z",
        purchase_amount=Decimal("10"),
        purchase_currency=currency,
    )
    newer = MaterialLot.objects.create(
        material=material,
        package_count=4,
        quantity_per_package=100,
        received_at="2026-02-01T00:00Z",
        purchase_amount=Decimal("80"),
        purchase_currency=currency,
    )

    result = blueprint.cost_per_output_unit()
    assert result.cost_per_unit == {"GBP": Decimal("45")}
    assert [usage.lot for usage in result.usages] == [oldest, newer]
    assert [usage.quantity for usage in result.usages] == [Decimal("100"), Decimal("400")]


@pytest.mark.django_db
def test_blueprint_cost_returns_empty_when_lots_cannot_cover_requirement(
    blueprint: Blueprint, material: Material
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

    assert blueprint.cost_per_output_unit().cost_per_unit == {}


@pytest.mark.django_db
def test_oldest_lot_fully_covering_requirement_excludes_newer_lot(
    blueprint: Blueprint, material: Material
):
    BlueprintMaterialRequirement.objects.create(
        blueprint=blueprint, material=material, quantity=Decimal("5")
    )
    oldest = MaterialLot.objects.create(
        material=material,
        quantity_per_package=10,
        received_at="2026-01-01T00:00Z",
        purchase_amount=Decimal("100"),
        purchase_currency_id="GBP",
    )
    MaterialLot.objects.create(
        material=material,
        quantity_per_package=10,
        received_at="2026-02-01T00:00Z",
        purchase_amount=Decimal("20"),
        purchase_currency_id="GBP",
    )

    result = blueprint.cost_per_output_unit()

    assert result.cost_per_unit == {"GBP": Decimal("50")}
    assert len(result.usages) == 1
    assert result.usages[0].lot == oldest
    assert result.usages[0].quantity == Decimal("5")


@pytest.mark.django_db
def test_lots_without_receipt_dates_follow_dated_lots(blueprint, material):
    BlueprintMaterialRequirement.objects.create(
        blueprint=blueprint, material=material, quantity=Decimal("2")
    )
    undated = MaterialLot.objects.create(
        material=material,
        quantity_per_package=1,
        purchase_amount=Decimal("9"),
        purchase_currency_id="GBP",
    )
    dated = MaterialLot.objects.create(
        material=material,
        quantity_per_package=1,
        received_at="2026-01-01T00:00Z",
        purchase_amount=Decimal("1"),
        purchase_currency_id="GBP",
    )
    result = blueprint.cost_per_output_unit()
    assert [usage.lot for usage in result.usages] == [dated, undated]
    assert result.cost_per_unit == {"GBP": Decimal("10")}


def record_movement(material, quantity, *, lot=None, posted=True):
    movement = InventoryTransaction.objects.create(
        workshop=material.workshop, kind="adjust", occurred_at="2026-03-01T00:00Z"
    )
    InventoryTransactionLine.objects.create(
        transaction=movement, material=material, material_lot=lot, quantity=quantity
    )
    if posted:
        movement.post()
    return movement


@pytest.mark.django_db
def test_cost_uses_remaining_posted_stock_and_skips_exhausted_lots(blueprint, material):
    BlueprintMaterialRequirement.objects.create(
        blueprint=blueprint, material=material, quantity=Decimal("6")
    )
    oldest = MaterialLot.objects.create(
        material=material,
        quantity_per_package=10,
        received_at="2026-01-01T00:00Z",
        purchase_amount=Decimal("10"),
        purchase_currency_id="GBP",
    )
    newer = MaterialLot.objects.create(
        material=material,
        quantity_per_package=10,
        received_at="2026-02-01T00:00Z",
        purchase_amount=Decimal("40"),
        purchase_currency_id="GBP",
    )
    record_movement(material, -8, lot=oldest)
    record_movement(material, -9, lot=newer, posted=False)
    result = blueprint.cost_per_output_unit()
    assert result.cost_per_unit == {"GBP": Decimal("18")}
    assert [usage.quantity for usage in result.usages] == [Decimal("2"), Decimal("4")]
    record_movement(material, -2, lot=oldest)
    result = blueprint.cost_per_output_unit()
    assert result.cost_per_unit == {"GBP": Decimal("24")}
    assert [usage.lot for usage in result.usages] == [newer]
    record_movement(material, -5, lot=newer)
    assert blueprint.cost_per_output_unit().cost_per_unit == {}


@pytest.mark.django_db
def test_unallocated_posted_movement_makes_lot_cost_uncertain(blueprint, material):
    BlueprintMaterialRequirement.objects.create(
        blueprint=blueprint, material=material, quantity=Decimal("1")
    )
    lot = MaterialLot.objects.create(
        material=material,
        quantity_per_package=10,
        purchase_amount=Decimal("10"),
        purchase_currency_id="GBP",
    )
    draft = record_movement(material, -1, posted=False)
    assert blueprint.cost_per_output_unit().cost_per_unit == {"GBP": Decimal("1")}
    draft.post()
    result = blueprint.cost_per_output_unit()
    assert result.cost_per_unit == {}
    assert result.usages == ()
    # Correct the unallocated movement with explicit, auditable entries.
    record_movement(material, 1)
    record_movement(material, -1, lot=lot)
    assert blueprint.cost_per_output_unit().cost_per_unit == {"GBP": Decimal("1")}
