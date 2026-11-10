from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from dj_craft_tally.models import MaterialLot


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
