from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from dj_craft_tally.models import (
    InventoryTransaction,
    InventoryTransactionLine,
    Material,
    MaterialLot,
    Project,
    ProjectStep,
    Unit,
    Workshop,
)


@pytest.mark.django_db
def test_inventory_line_tracks_signed_stock_movement(workshop, material) -> None:
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
def test_inventory_line_rejects_foreign_workshop_material(workshop, gram) -> None:
    transaction = InventoryTransaction.objects.create(
        workshop=workshop,
        kind=InventoryTransaction.Kind.CONSUME,
        occurred_at="2026-01-01T12:00Z",
    )
    material = Material.objects.create(
        name="PLA",
        unit=gram,
        workshop=Workshop.objects.create(name="Other"),
    )
    with pytest.raises(ValidationError, match="transaction's workshop"):
        InventoryTransactionLine.objects.create(
            transaction=transaction, material=material, quantity=-1
        )


@pytest.mark.django_db
def test_material_unit_cannot_change_after_inventory_use(workshop, material) -> None:
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


@pytest.mark.django_db
def test_material_unit_queryset_mutations_are_rejected(workshop, material) -> None:
    kilogram = Unit.objects.get(code="kg")

    with pytest.raises(
        ValidationError, match="must be changed through the model instance"
    ):
        Material.objects.filter(pk=material.pk).update(unit=kilogram)
    material.unit = kilogram
    with pytest.raises(
        ValidationError, match="must be changed through the model instance"
    ):
        Material.objects.bulk_update([material], ["unit"])


@pytest.mark.django_db
def test_transaction_rejects_foreign_projects_and_steps(workshop, material):
    other = Workshop.objects.create(name="Other")
    other_project = Project.objects.create(name="Other project", workshop=other)
    project = Project.objects.create(name="Project", workshop=workshop)
    step = ProjectStep.objects.create(
        project=project,
        sequence=1,
        name="Step",
        occurred_at="2026-01-01T12:00Z",
    )
    with pytest.raises(ValidationError, match="transaction's workshop"):
        InventoryTransaction(
            workshop=workshop,
            kind=InventoryTransaction.Kind.RECEIVE,
            occurred_at="2026-01-01T12:00Z",
            project=other_project,
            project_step=step,
        ).full_clean()
    foreign_step = ProjectStep.objects.create(
        project=other_project,
        sequence=1,
        name="Foreign step",
        occurred_at="2026-01-01T12:00Z",
    )
    with pytest.raises(ValidationError, match="project step must belong"):
        InventoryTransaction(
            workshop=workshop,
            kind=InventoryTransaction.Kind.RECEIVE,
            occurred_at="2026-01-01T12:00Z",
            project_step=foreign_step,
        ).full_clean()
    with pytest.raises(ValidationError, match="Use post"):
        InventoryTransaction(
            workshop=workshop,
            kind=InventoryTransaction.Kind.RECEIVE,
            occurred_at="2026-01-01T12:00Z",
            posted=True,
        ).save()


@pytest.mark.django_db
def test_draft_transaction_and_lines_can_be_deleted(workshop, material):
    transaction = InventoryTransaction.objects.create(
        workshop=workshop,
        kind=InventoryTransaction.Kind.RECEIVE,
        occurred_at="2026-01-01T12:00Z",
    )
    InventoryTransactionLine.objects.create(
        transaction=transaction, material=material, quantity=1
    ).delete()
    transaction.delete()


@pytest.mark.django_db
def test_line_rejects_mismatched_lot_and_moving_transactions(workshop, material):
    transaction = InventoryTransaction.objects.create(
        workshop=workshop,
        kind=InventoryTransaction.Kind.RECEIVE,
        occurred_at="2026-01-01T12:00Z",
    )
    other_material = Material.objects.create(
        workshop=workshop, name="Other material", unit=material.unit
    )
    lot = MaterialLot.objects.create(material=other_material, quantity_per_package=1)
    with pytest.raises(ValidationError, match="lot must belong"):
        InventoryTransactionLine.objects.create(
            transaction=transaction, material=material, material_lot=lot, quantity=1
        )
    line = InventoryTransactionLine.objects.create(
        transaction=transaction, material=material, quantity=1
    )
    line.transaction = InventoryTransaction.objects.create(
        workshop=workshop,
        kind=InventoryTransaction.Kind.RECEIVE,
        occurred_at="2026-01-01T12:00Z",
    )
    with pytest.raises(ValidationError, match="cannot be moved"):
        line.save()
