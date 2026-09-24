from decimal import Decimal

import pytest

from dj_craft_tally.models import Material, MaterialLot, Unit, Workshop


@pytest.mark.django_db
def test_material_lot_records_package_count_and_contents() -> None:
    workshop = Workshop.objects.create(name="Home workshop")
    material = Material.objects.create(
        name="BrandY red PLA", unit=Unit.objects.get(code="g"), workshop=workshop
    )
    lot = MaterialLot.objects.create(
        material=material, package_count=10, quantity_per_package=Decimal("500")
    )

    assert lot.reference == f"lot-{lot.id}"
    assert lot.total_quantity == Decimal("5000")
