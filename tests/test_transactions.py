from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from dj_craft_tally.models import (
    Activity,
    Blueprint,
    BlueprintMaterialRequirement,
    CurrencyTransaction,
    Equipment,
    InventoryTransaction,
    InventoryTransactionLine,
    MaterialLot,
    Project,
    Workshop,
)
from dj_craft_tally.services import expenditure_periods


@pytest.mark.django_db
def test_transaction_rejects_other_workshop_project():
    workshop = Workshop.objects.create(name="Workshop")
    other = Workshop.objects.create(name="Other")
    project = Project.objects.create(workshop=other, name="Model")
    transaction = CurrencyTransaction(
        workshop=workshop,
        project=project,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        description="Test",
        amount=Decimal("-1"),
        currency_id="GBP",
    )
    with pytest.raises(ValidationError) as exc:
        transaction.full_clean()
    assert "project" in exc.value.message_dict


@pytest.mark.django_db
def test_linked_lot_cost_is_used_for_estimates_and_expenses_are_counted_once(material):
    lot = MaterialLot.objects.create(
        material=material,
        reference="purchase",
        quantity_per_package=10,
    )
    transaction = CurrencyTransaction.objects.create(
        workshop=material.workshop,
        created_at=datetime(2026, 2, 11, tzinfo=UTC),
        description="Material",
        amount=Decimal("-20"),
        currency_id="GBP",
        material_lot=lot,
    )
    blueprint = Blueprint.objects.create(
        workshop=material.workshop,
        name="Design",
        output_name="Item",
        output_unit=material.unit,
    )
    BlueprintMaterialRequirement.objects.create(
        blueprint=blueprint,
        material=material,
        quantity=2,
    )
    assert blueprint.cost_per_output_unit().cost_per_unit == {"GBP": Decimal("4")}
    assert expenditure_periods(as_of=date(2026, 2, 12))[2]["totals"] == {
        "GBP": Decimal("20")
    }
    transaction.amount = Decimal("-30")
    transaction.save()
    assert blueprint.cost_per_output_unit().cost_per_unit == {"GBP": Decimal("6")}
    movement = InventoryTransaction.objects.create(
        workshop=material.workshop, kind="consume", occurred_at="2026-02-12T00:00Z"
    )
    InventoryTransactionLine.objects.create(
        transaction=movement, material=material, material_lot=lot, quantity=-9
    )
    movement.post()
    assert blueprint.cost_per_output_unit().cost_per_unit == {}


@pytest.mark.django_db
def test_rejects_resources_from_other_workshop(material):
    other = Workshop.objects.create(name="Other")
    lot = MaterialLot.objects.create(material=material, quantity_per_package=1)
    equipment = Equipment.objects.create(workshop=material.workshop, name="Tool")
    transaction = CurrencyTransaction(
        workshop=other,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        description="Purchase",
        amount=Decimal("1"),
        currency_id="GBP",
        material_lot=lot,
        equipment=equipment,
    )
    with pytest.raises(ValidationError) as exc:
        transaction.save()
    assert {"material_lot", "equipment"} <= exc.value.message_dict.keys()


@pytest.mark.django_db
def test_expense_reporting_uses_utc_days_and_excludes_future_expenses(workshop):
    for stamp, amount in (
        ("2025-12-31T23:59:59Z", "100"),
        ("2026-01-01T00:00:00Z", "1"),
        ("2026-11-09T00:00:00Z", "2"),
        ("2026-11-16T23:59:59Z", "4"),
        ("2026-11-17T00:00:00Z", "100"),
    ):
        CurrencyTransaction.objects.create(
            workshop=workshop,
            created_at=stamp,
            description=stamp,
            amount=-Decimal(amount),
            currency_id="GBP",
        )

    periods = expenditure_periods(as_of=date(2026, 11, 16))
    assert [period["totals"] for period in periods] == [
        {"GBP": Decimal("6")},
        {"GBP": Decimal("6")},
        {"GBP": Decimal("7")},
    ]


@pytest.mark.django_db
def test_activity_rejects_expense_from_other_workshop(workshop):
    other = Workshop.objects.create(name="Other")
    transaction = CurrencyTransaction.objects.create(
        workshop=other, description="Purchase", amount=Decimal("1"), currency_id="GBP"
    )
    with pytest.raises(ValidationError, match="cost must belong"):
        Activity.objects.create(workshop=workshop, name="Print", cost=transaction)


@pytest.mark.django_db
def test_income_is_recorded_and_excluded_from_expenditure(workshop):
    CurrencyTransaction.objects.create(
        workshop=workshop,
        description="Sale",
        amount=Decimal("100"),
        currency_id="GBP",
        created_at=datetime(2026, 2, 12, tzinfo=UTC),
    )
    assert expenditure_periods(as_of=date(2026, 2, 12))[2]["totals"] == {}


@pytest.mark.django_db
def test_income_cannot_be_a_lot_purchase(material):
    lot = MaterialLot.objects.create(material=material, quantity_per_package=1)
    with pytest.raises(ValidationError, match="cannot be income"):
        CurrencyTransaction.objects.create(
            workshop=material.workshop,
            material_lot=lot,
            description="Sale",
            amount=Decimal("1"),
            currency_id="GBP",
        )
