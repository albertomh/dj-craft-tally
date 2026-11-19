from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from dj_craft_tally.models import (
    Activity,
    ActivityMaterial,
    Equipment,
    InventoryTransaction,
    InventoryTransactionLine,
    Material,
    Process,
    ProcessStep,
    Project,
    Unit,
    Workshop,
)


@pytest.mark.django_db
def test_process_and_material_observations_support_other_crafts():
    workshop = Workshop.objects.create(name="Woodshop")
    process = Process.objects.create(workshop=workshop, name="Finish panels")
    drying = ProcessStep.objects.create(process=process, sequence=1, name="Dry")
    ProcessStep.objects.create(process=process, sequence=2, name="Varnish")
    other_process = Process.objects.create(workshop=workshop, name="Finish frames")
    ProcessStep.objects.create(process=other_process, sequence=1, name="Dry")
    project = Project.objects.create(workshop=workshop, name="Shelves")
    step = Activity.objects.create(
        project=project,
        name="Dry oak",
        process_step=drying,
        occurred_at="2026-01-01T12:00Z",
    )
    panel = Material.objects.create(
        workshop=workshop,
        name="Oak panels",
        unit=Unit.objects.get(code="item"),
        kind=Material.Kind.OUTPUT,
    )
    yield_record = ActivityMaterial.objects.create(
        activity=step,
        material=panel,
        role=ActivityMaterial.Role.OUTPUT,
        quantity=Decimal("2"),
        unit=panel.unit,
    )
    assert yield_record.quantity == Decimal("2")
    assert list(process.steps.values_list("name", flat=True)) == [
        "Dry",
        "Varnish",
    ]
    assert panel.stock_balance() == 0
    with pytest.raises(ValidationError):
        ProcessStep.objects.create(process=process, sequence=1, name="Dry")
    with pytest.raises(IntegrityError), transaction.atomic():
        ProcessStep.objects.bulk_create(
            [ProcessStep(process=process, sequence=1, name="Dry")]
        )


@pytest.mark.django_db
def test_observations_and_processes_validate_workshop_and_quantities():
    workshop = Workshop.objects.create(name="One")
    other = Workshop.objects.create(name="Two")
    project = Project.objects.create(workshop=workshop, name="Project")
    process = Process.objects.create(workshop=other, name="Other process")
    operation = ProcessStep.objects.create(process=process, sequence=1, name="Dry")
    step = Activity(
        project=project,
        name="Dry",
        process_step=operation,
        occurred_at="2026-01-01T12:00Z",
    )
    with pytest.raises(ValidationError, match="process"):
        step.save()
    step.process_step = None
    step.cost_amount = Decimal("1")
    with pytest.raises(ValidationError, match="currency"):
        step.save()
    step.cost_amount = None
    step.save()
    material = Material.objects.create(
        workshop=other, name="Glass", unit=Unit.objects.get(code="g")
    )
    observation = ActivityMaterial(
        activity=step,
        material=material,
        role=ActivityMaterial.Role.INPUT,
        quantity=Decimal("-1"),
    )
    with pytest.raises(ValidationError) as exc:
        observation.save()
    assert {"material", "unit", "quantity"} <= set(exc.value.message_dict)


@pytest.mark.django_db
def test_occurrence_accepts_timestamp_or_date_notes():
    project = Project.objects.create(
        workshop=Workshop.objects.create(name="Studio"), name="Bowl"
    )
    activity = Activity.objects.create(
        project=project, name="Shape", occurred_at="2025-12-30T12:00Z"
    )
    activity.refresh_from_db()
    assert activity.occurred_at.isoformat().startswith("2025-12-30T12:00")
    activity.occurred_at = None
    activity.save()
    activity.refresh_from_db()
    assert activity.occurred_at is None


@pytest.mark.django_db
def test_observations_can_link_only_matching_posted_inventory_lines():
    workshop = Workshop.objects.create(name="Pottery")
    project = Project.objects.create(workshop=workshop, name="Bowl")
    step = Activity.objects.create(
        project=project, name="Shape", occurred_at="2025-12-30T12:00Z"
    )
    material = Material.objects.create(
        workshop=workshop, name="Clay", unit=Unit.objects.get(code="g")
    )
    entry = InventoryTransaction.objects.create(
        workshop=workshop,
        project=project,
        activity=step,
        kind=InventoryTransaction.Kind.CONSUME,
        occurred_at="2025-12-30T12:00Z",
    )
    line = InventoryTransactionLine.objects.create(
        transaction=entry, material=material, quantity=Decimal("-10")
    )
    observed = ActivityMaterial(
        activity=step,
        material=material,
        role=ActivityMaterial.Role.INPUT,
        inventory_line=line,
    )
    with pytest.raises(ValidationError, match="posted"):
        observed.save()
    entry.post()
    observed.save()
    observed.role = ActivityMaterial.Role.OUTPUT
    with pytest.raises(ValidationError, match="direction"):
        observed.save()
    observed.role = ActivityMaterial.Role.INPUT
    observed.material = Material.objects.create(
        workshop=workshop, name="Glaze", unit=material.unit
    )
    with pytest.raises(ValidationError, match="match"):
        observed.save()
    observed.material = material
    other_step = Activity.objects.create(
        project=project, name="Glaze", occurred_at="2025-12-31T12:00Z"
    )
    observed.activity = other_step
    with pytest.raises(ValidationError, match="match"):
        observed.save()


@pytest.mark.django_db
def test_standalone_activity_validates_workshop():
    workshop = Workshop.objects.create(name="Woodshop")
    other = Workshop.objects.create(name="Other")
    equipment = Equipment.objects.create(workshop=workshop, name="Plane")
    activity = Activity.objects.create(
        workshop=workshop,
        name="Sharpen plane blade",
        equipment=equipment,
        outcome="success",
    )
    assert activity.project is None
    activity.equipment = Equipment.objects.create(workshop=other, name="Other plane")
    with pytest.raises(ValidationError, match="workshop"):
        activity.save()


@pytest.mark.django_db
def test_activity_rejects_missing_or_mismatched_workshop():
    workshop = Workshop.objects.create(name="Studio")
    other = Workshop.objects.create(name="Other studio")
    project = Project.objects.create(workshop=workshop, name="Bowl")
    activity = Activity(name="Shape")
    with pytest.raises(ValidationError) as exc:
        activity.save()
    assert "workshop" in exc.value.message_dict
    activity.project = project
    activity.workshop = other
    with pytest.raises(ValidationError) as exc:
        activity.save()
    assert "project" in exc.value.message_dict


@pytest.mark.django_db
def test_activity_cost_and_material_unit_require_corresponding_amounts(
    workshop, material
):
    activity = Activity(workshop=workshop, name="Shape", cost_currency_id="GBP")
    with pytest.raises(ValidationError) as exc:
        activity.save()
    assert "cost_amount" in exc.value.message_dict
    activity.cost_currency_id = None
    activity.save()
    observation = ActivityMaterial(
        activity=activity,
        material=material,
        role=ActivityMaterial.Role.INPUT,
        unit=material.unit,
    )
    with pytest.raises(ValidationError) as exc:
        observation.save()
    assert "quantity" in exc.value.message_dict
