"""Tests for equipment-material replenishment forecasts."""

from datetime import datetime
from decimal import Decimal

import pytest

from dj_craft_tally.models import (
    Activity,
    Equipment,
    EquipmentMaterial,
    InventoryTransaction,
    InventoryTransactionLine,
    MaterialLot,
)
from dj_craft_tally.services import consumable_forecast


def _consume(*, workshop, material, equipment, occurred_at, quantity):
    activity = Activity.objects.create(
        workshop=workshop, name="Print", equipment=equipment, occurred_at=occurred_at
    )
    transaction = InventoryTransaction.objects.create(
        workshop=workshop,
        activity=activity,
        kind=InventoryTransaction.Kind.CONSUME,
        occurred_at=occurred_at,
    )
    InventoryTransactionLine.objects.create(
        transaction=transaction, material=material, quantity=-quantity
    )
    transaction.post()


@pytest.mark.django_db
def test_consumable_forecast_uses_posted_equipment_consumption(material, workshop):
    equipment = Equipment.objects.create(workshop=workshop, name="Printer")
    association = EquipmentMaterial.objects.create(
        equipment=equipment,
        material=material,
        reserve_quantity=Decimal("10"),
    )
    MaterialLot.objects.create(
        material=material,
        quantity_per_package=Decimal("100"),
        received_at="2026-01-01T00:00Z",
    )
    _consume(
        workshop=workshop,
        material=material,
        equipment=equipment,
        occurred_at="2026-03-01T00:00Z",
        quantity=Decimal("30"),
    )
    _consume(
        workshop=workshop,
        material=material,
        equipment=equipment,
        occurred_at="2026-03-16T00:00Z",
        quantity=Decimal("10"),
    )
    other_equipment = Equipment.objects.create(workshop=workshop, name="Other printer")
    _consume(
        workshop=workshop,
        material=material,
        equipment=other_equipment,
        occurred_at="2026-03-16T00:00Z",
        quantity=Decimal("20"),
    )

    forecast = consumable_forecast(
        association, months=1, as_of=datetime.fromisoformat("2026-03-31T00:00:00+00:00")
    )

    assert forecast.period_start == datetime.fromisoformat("2026-02-28T00:00:00+00:00")
    assert forecast.consumed_quantity == Decimal("40")
    assert forecast.stock_quantity == Decimal("40")
    assert forecast.average_daily_consumption == Decimal("40") / Decimal("31")
    assert forecast.depletion_at == datetime.fromisoformat("2026-05-01T00:00:00+00:00")


@pytest.mark.django_db
def test_consumable_forecast_has_no_dates_without_recent_consumption(workshop, material):
    equipment = Equipment.objects.create(workshop=workshop, name="Printer")
    association = EquipmentMaterial.objects.create(equipment=equipment, material=material)

    forecast = consumable_forecast(
        association, as_of=datetime.fromisoformat("2026-03-31T00:00:00+00:00")
    )

    assert forecast.consumed_quantity == 0
    assert forecast.average_daily_consumption == 0
    assert forecast.depletion_at is None


def test_consumable_forecast_rejects_an_invalid_window(material):
    association = EquipmentMaterial(equipment=Equipment(), material=material)

    with pytest.raises(ValueError, match="at least 1"):
        consumable_forecast(association, months=0)


def test_consumable_forecast_rejects_a_naive_as_of(material):
    association = EquipmentMaterial(equipment=Equipment(), material=material)

    with pytest.raises(ValueError, match="must be timezone-aware"):
        consumable_forecast(association, as_of=datetime(2026, 1, 1))
