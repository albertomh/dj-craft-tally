from decimal import Decimal

import pytest
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.test import RequestFactory

from dj_craft_tally.models import Material, MaterialLot


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
def test_safe_bulk_mutations_and_lot_bulk_creation_rules(material):
    Material.objects.filter(pk=material.pk).update(name="Porcelain")
    material.name = "Stoneware"
    Material.objects.bulk_update([material], ["name"])
    lot = MaterialLot.objects.create(material=material, quantity_per_package=1)
    MaterialLot.objects.filter(pk=lot.pk).update(supplier="Clay Co")
    lot.supplier = "Another supplier"
    MaterialLot.objects.bulk_update([lot], ["supplier"])
    with pytest.raises(ValidationError, match="individually"):
        MaterialLot.objects.bulk_create([])


@pytest.mark.django_db
def test_material_lot_admin_locks_receipt_fields_after_creation(material):
    lot = MaterialLot.objects.create(material=material, quantity_per_package=1)
    lot_admin = admin.site._registry[MaterialLot]
    request = RequestFactory().get("/")
    assert "material" in lot_admin.get_readonly_fields(request, lot)
    assert lot_admin.get_readonly_fields(request) == ()
