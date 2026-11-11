from decimal import Decimal
from http import HTTPStatus

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, override_settings
from django.utils.translation import override

import dj_craft_tally.admin as tally_admin
from dj_craft_tally.models import (
    Blueprint,
    BlueprintMaterialRequirement,
    InventoryTransaction,
    InventoryTransactionLine,
    Material,
    MaterialLot,
    Project,
    ProjectStep,
)


@pytest.mark.django_db
def test_material_admin_displays_stock_using_unit_precision(workshop, item, gram):
    material_admin = admin.site._registry[Material]
    assert "display_stock_balance" in material_admin.list_display
    for unit, quantity, shown in (
        (item, "96", "96"),
        (gram, "125.5", "125.50 g"),
        (gram, "0.004", "0.00 g"),
        (gram, "-0.005", "-0.01 g"),
    ):
        material = Material.objects.create(
            workshop=workshop, name=f"Stock {quantity}", unit=unit
        )
        movement = InventoryTransaction.objects.create(
            workshop=workshop, kind="adjust", occurred_at="2026-01-01T00:00Z"
        )
        InventoryTransactionLine.objects.create(
            transaction=movement, material=material, quantity=Decimal(quantity)
        )
        movement.post()
        with override("en"):
            rendered = str(material_admin.display_stock_balance(material))
        assert f">{shown}</span>" in rendered
        assert str(material.stock_balance()) in rendered
        assert material.stock_balance() == Decimal(quantity)


@pytest.mark.django_db
@override_settings(ROOT_URLCONF="tests.admin_urls", ALLOWED_HOSTS=["testserver"])
def test_material_admin_page_shows_unit_precision(client, workshop, item):
    user = get_user_model().objects.create_superuser(username="admin", password="test")
    material = Material.objects.create(workshop=workshop, name="Bolts", unit=item)
    movement = InventoryTransaction.objects.create(
        workshop=workshop, kind="adjust", occurred_at="2026-01-01T00:00Z"
    )
    InventoryTransactionLine.objects.create(
        transaction=movement, material=material, quantity=96
    )
    movement.post()
    client.force_login(user)
    response = client.get("/admin/crafttally/material/")
    assert response.status_code == HTTPStatus.OK
    assert b">96</span>" in response.content
    assert b"Exact: 96.000000" in response.content
    assert b"column-unit" not in response.content


@pytest.mark.django_db
def test_inventory_transaction_line_admin_orders_by_parent_occurrence(workshop, material):
    earlier = InventoryTransaction.objects.create(
        workshop=workshop,
        kind=InventoryTransaction.Kind.RECEIVE,
        occurred_at="2026-01-01T00:00Z",
    )
    later = InventoryTransaction.objects.create(
        workshop=workshop,
        kind=InventoryTransaction.Kind.RECEIVE,
        occurred_at="2026-01-02T00:00Z",
    )
    earlier_line = InventoryTransactionLine.objects.create(
        transaction=earlier, material=material, quantity=1
    )
    later_line = InventoryTransactionLine.objects.create(
        transaction=later, material=material, quantity=1
    )
    request = RequestFactory().get("/")
    request.user = get_user_model()(is_staff=True, is_superuser=True)

    lines = admin.site._registry[InventoryTransactionLine].get_queryset(request)

    assert list(lines.filter(pk__in=(earlier_line.pk, later_line.pk))) == [
        later_line,
        earlier_line,
    ]


@pytest.mark.django_db
@override_settings(ROOT_URLCONF="tests.admin_urls", ALLOWED_HOSTS=["testserver"])
def test_admin_changelists_use_human_labels_and_unit_precision(
    client, workshop, item, gram
):
    assert tally_admin.format_quantity(None, item) is None
    user = get_user_model().objects.create_superuser(username="admin", password="test")
    blueprint = Blueprint.objects.create(
        workshop=workshop,
        name="Clay batch",
        output_name="Clay",
        output_quantity=6,
        output_unit=gram,
    )
    material = Material.objects.create(workshop=workshop, name="Clay", unit=gram)
    bolts = Material.objects.create(workshop=workshop, name="M3 bolts", unit=item)
    filament = Material.objects.create(
        workshop=workshop, name="Blue PLA filament", unit=gram
    )
    MaterialLot.objects.create(
        material=filament, reference="PLA-BLUE-01", quantity_per_package=2000
    )
    BlueprintMaterialRequirement.objects.create(
        blueprint=blueprint, material=material, quantity=2
    )
    stock = InventoryTransaction.objects.create(
        workshop=workshop,
        kind=InventoryTransaction.Kind.RECEIVE,
        occurred_at="2026-01-01T00:00Z",
    )
    InventoryTransactionLine.objects.create(
        transaction=stock, material=material, quantity=4
    )
    stock.post()
    project = Project.objects.create(workshop=workshop, name="Kitchen tiles")
    project.set_status(Project.Status.ACTIVE)
    step = ProjectStep.objects.create(
        project=project,
        sequence=1,
        name="Press tiles",
        occurred_at="2026-01-02T00:00Z",
    )
    transaction = InventoryTransaction.objects.create(
        workshop=workshop,
        kind=InventoryTransaction.Kind.CONSUME,
        occurred_at="2026-01-02T12:30Z",
        project=project,
        project_step=step,
        reference="Clay for first batch",
    )
    InventoryTransactionLine.objects.create(
        transaction=transaction, material=bolts, quantity=-2
    )
    InventoryTransactionLine.objects.create(
        transaction=transaction, material=filament, quantity=-125
    )
    client.force_login(user)

    blueprint_response = client.get("/admin/crafttally/blueprint/")
    assert blueprint_response.status_code == HTTPStatus.OK
    assert b">6.00 g</span>" in blueprint_response.content
    assert b">12.00 g</span>" in blueprint_response.content
    assert b"column-output_unit" not in blueprint_response.content

    material_response = client.get("/admin/crafttally/material/")
    assert material_response.status_code == HTTPStatus.OK
    assert b">4.00 g</span>" in material_response.content
    assert b"column-unit" not in material_response.content

    lot_response = client.get("/admin/crafttally/materiallot/")
    assert lot_response.status_code == HTTPStatus.OK
    assert b">2000.00 g</span>" in lot_response.content

    step_response = client.get("/admin/crafttally/projectstep/")
    assert step_response.status_code == HTTPStatus.OK
    assert b"Kitchen tiles" in step_response.content
    assert b"Project object" not in step_response.content

    change_response = client.get("/admin/crafttally/projectstatuschange/")
    assert change_response.status_code == HTTPStatus.OK
    assert b"Kitchen tiles" in change_response.content
    assert b"Planned" in change_response.content
    assert b"Active" in change_response.content
    assert b"ProjectStatusChange object" not in change_response.content

    transaction_response = client.get("/admin/crafttally/inventorytransaction/")
    assert transaction_response.status_code == HTTPStatus.OK
    assert b"Kitchen tiles" in transaction_response.content
    assert b"Kitchen tiles \xc2\xb7 1: Press tiles" in transaction_response.content

    line_response = client.get("/admin/crafttally/inventorytransactionline/")
    assert line_response.status_code == HTTPStatus.OK
    assert str(transaction).encode() in line_response.content
    assert b">-2</span>" in line_response.content
    assert b">-2.000000</span>" not in line_response.content
    assert b">-125.00 g</span>" in line_response.content
