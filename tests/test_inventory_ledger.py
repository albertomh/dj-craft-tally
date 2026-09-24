from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from dj_craft_tally.models import (
    InventoryTransaction,
    InventoryTransactionLine,
    Material,
    Unit,
    Workshop,
)


@pytest.mark.django_db
def test_inventory_line_tracks_signed_stock_movement() -> None:
    workshop = Workshop.objects.create(name="Home")
    material = Material.objects.create(
        name="PLA", unit=Unit.objects.get(code="g"), workshop=workshop
    )
    transaction = InventoryTransaction.objects.create(
        workshop=workshop,
        kind=InventoryTransaction.Kind.CONSUME,
        occurred_at="2026-01-01T12:00Z",
    )
    line = InventoryTransactionLine.objects.create(
        transaction=transaction, material=material, quantity=Decimal("-42.5")
    )
    assert line.quantity == Decimal("-42.500000")


@pytest.mark.django_db
def test_inventory_line_rejects_foreign_workshop_material() -> None:
    transaction = InventoryTransaction.objects.create(
        workshop=Workshop.objects.create(name="Home"),
        kind=InventoryTransaction.Kind.CONSUME,
        occurred_at="2026-01-01T12:00Z",
    )
    material = Material.objects.create(
        name="PLA",
        unit=Unit.objects.get(code="g"),
        workshop=Workshop.objects.create(name="Other"),
    )
    with pytest.raises(ValidationError, match="transaction's workshop"):
        InventoryTransactionLine.objects.create(
            transaction=transaction, material=material, quantity=-1
        )


@pytest.mark.django_db
def test_material_unit_cannot_change_after_inventory_use() -> None:
    workshop = Workshop.objects.create(name="Home")
    material = Material.objects.create(
        name="PLA", unit=Unit.objects.get(code="g"), workshop=workshop
    )
    transaction = InventoryTransaction.objects.create(
        workshop=workshop,
        kind=InventoryTransaction.Kind.RECEIVE,
        occurred_at="2026-01-01T12:00Z",
    )
    InventoryTransactionLine.objects.create(
        transaction=transaction, material=material, quantity=100
    )
    material.unit = Unit.objects.get(code="kg")

    with pytest.raises(ValidationError, match="cannot change"):
        material.save()
