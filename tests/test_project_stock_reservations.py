"""Tests for calendar-backed project stock reservations."""

from datetime import datetime
from decimal import Decimal

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import RequestFactory

from dj_craft_tally.admin.activities import ProjectStockReservationInline
from dj_craft_tally.models import (
    Activity,
    Equipment,
    EquipmentMaterial,
    InventoryTransaction,
    InventoryTransactionLine,
    MaterialLot,
    Project,
    ProjectSchedule,
    ProjectStockReservation,
    Workshop,
)
from dj_craft_tally.services import consumable_forecast


@pytest.mark.django_db
def test_material_reservation_balance_without_queryset_annotation(material, workshop):
    assert material.scheduled_reservation_balance() == Decimal("0")

    project = Project.objects.create(workshop=workshop, name="Miniatures")
    schedule_entry = ProjectSchedule.objects.create(
        project=project,
        starts_at="2026-04-01T09:00Z",
    )
    ProjectStockReservation.objects.create(
        schedule_entry=schedule_entry, material=material, quantity=Decimal("12")
    )

    assert material.scheduled_reservation_balance() == Decimal("12")


@pytest.mark.django_db
def test_stock_reservation_must_use_the_projects_workshop_material(material, workshop):
    project = Project.objects.create(workshop=workshop, name="Miniatures")
    schedule_entry = ProjectSchedule.objects.create(
        project=project,
        starts_at="2026-04-01T09:00Z",
    )
    other_material = type(material).objects.create(
        workshop=Workshop.objects.create(name="Other studio"),
        name="Other resin",
        unit=material.unit,
    )

    reservation = ProjectStockReservation(
        schedule_entry=schedule_entry, material=other_material, quantity=1
    )
    with pytest.raises(ValidationError, match="project's workshop"):
        reservation.full_clean()


@pytest.mark.django_db
def test_active_scheduled_stock_reservations_reduce_forecast_available_stock(
    material, workshop
):
    equipment = Equipment.objects.create(workshop=workshop, name="Printer")
    association = EquipmentMaterial.objects.create(
        equipment=equipment, material=material, reserve_quantity=Decimal("10")
    )
    MaterialLot.objects.create(
        material=material,
        quantity_per_package=Decimal("100"),
        received_at="2026-01-01T00:00Z",
    )
    activity = Activity.objects.create(
        workshop=workshop, name="Print", equipment=equipment
    )
    transaction = InventoryTransaction.objects.create(
        workshop=workshop,
        activity=activity,
        kind=InventoryTransaction.Kind.CONSUME,
        occurred_at="2026-03-01T00:00Z",
    )
    InventoryTransactionLine.objects.create(
        transaction=transaction, material=material, quantity=Decimal("-31")
    )
    transaction.post()
    project = Project.objects.create(workshop=workshop, name="Miniatures")
    schedule_entry = ProjectSchedule.objects.create(
        project=project,
        starts_at="2026-04-01T09:00Z",
    )
    ProjectStockReservation.objects.create(
        schedule_entry=schedule_entry, material=material, quantity=Decimal("50")
    )
    cancelled_entry = ProjectSchedule.objects.create(
        project=project,
        starts_at="2026-04-02T09:00Z",
        status=ProjectSchedule.Status.CANCELLED,
    )
    ProjectStockReservation.objects.create(
        schedule_entry=cancelled_entry,
        material=material,
        quantity=Decimal("10"),
    )

    forecast = consumable_forecast(
        association, months=1, as_of=datetime.fromisoformat("2026-03-31T00:00:00+00:00")
    )

    assert forecast.stock_quantity == Decimal("69")
    assert forecast.scheduled_reservation_quantity == Decimal("50")
    assert forecast.available_quantity == Decimal("19")


@pytest.mark.django_db
def test_reservation_inline_disables_material_related_actions(material):
    inline = ProjectStockReservationInline(ProjectSchedule, admin.site)
    request = RequestFactory().get("/")
    request.user = get_user_model().objects.create_superuser(
        username="admin", password="test"
    )
    field = inline.formfield_for_dbfield(
        ProjectStockReservation._meta.get_field("material"), request
    )

    assert field.widget.can_add_related is False
    assert field.widget.can_delete_related is False
