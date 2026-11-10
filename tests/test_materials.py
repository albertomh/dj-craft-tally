from decimal import Decimal
from http import HTTPStatus

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import override_settings
from django.utils.translation import override

from dj_craft_tally.models import (
    InventoryTransaction,
    InventoryTransactionLine,
    Material,
    MaterialLot,
)


@pytest.mark.django_db
def test_material_lot_records_package_count_and_contents(material) -> None:
    lot = MaterialLot.objects.create(
        material=material, package_count=10, quantity_per_package=Decimal("500")
    )

    assert lot.reference == f"lot-{lot.id}"
    assert lot.total_quantity == Decimal("5000")
    line = lot.inventory_lines.get()
    assert line.quantity == Decimal("5000")
    assert line.transaction.posted
    assert line.transaction.kind == "receive"
    assert material.stock_balance() == Decimal("5000")
    lot.supplier = "Supplier"
    lot.save()
    assert lot.inventory_lines.count() == 1
    lot.package_count = 11
    with pytest.raises(ValidationError, match="cannot be changed"):
        lot.save()
    with pytest.raises(ValidationError, match="cannot be changed"):
        MaterialLot.objects.filter(pk=lot.pk).update(package_count=11)
    with pytest.raises(ValidationError, match="cannot be changed"):
        MaterialLot.objects.bulk_update([lot], ["package_count"])


@pytest.mark.django_db
def test_invalid_lot_does_not_record_a_receipt(material):
    with pytest.raises(ValidationError):
        MaterialLot.objects.create(
            material=material, package_count=0, quantity_per_package=1
        )
    assert not MaterialLot.objects.exists()
    assert material.stock_balance() == 0
    with pytest.raises(ValidationError):
        MaterialLot.objects.create(
            material=material,
            package_count=100000000,
            quantity_per_package=Decimal("100000000"),
        )
    assert not MaterialLot.objects.exists()
    assert material.stock_balance() == 0


@pytest.mark.django_db
def test_material_admin_displays_stock_using_unit_precision(workshop, item, gram):
    material_admin = admin.site._registry[Material]
    assert "display_stock_balance" in material_admin.list_display
    for unit, quantity, shown in (
        (item, "96", "96"),
        (gram, "125.5", "125.50"),
        (gram, "0.004", "0.00"),
        (gram, "-0.005", "-0.01"),
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
