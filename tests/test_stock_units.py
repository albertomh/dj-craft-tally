from decimal import Decimal

import pytest
from django.core.exceptions import FieldDoesNotExist

from dj_craft_tally.models import (
    Blueprint,
    BlueprintMaterialRequirement,
    InventoryTransaction,
    InventoryTransactionLine,
    Material,
    Unit,
    Workshop,
)


def test_quantities_have_one_unit_and_describe_it():
    for model in (BlueprintMaterialRequirement, InventoryTransactionLine):
        with pytest.raises(FieldDoesNotExist):
            model._meta.get_field("unit")
        assert "stock unit" in str(model._meta.get_field("quantity").help_text)


@pytest.mark.django_db
def test_requirement_and_movement_quantities_use_the_material_stock_unit():
    workshop = Workshop.objects.create(name="Studio")
    material = Material.objects.create(
        workshop=workshop, name="Clay", unit=Unit.objects.get(code="g")
    )
    blueprint = Blueprint.objects.create(
        workshop=workshop,
        name="Cup",
        output_name="Cup",
        output_unit=Unit.objects.get(code="item"),
    )
    requirement = BlueprintMaterialRequirement.objects.create(
        blueprint=blueprint, material=material, quantity=Decimal("120.125")
    )
    movement = InventoryTransaction.objects.create(
        workshop=workshop, kind="receive", occurred_at="2026-01-01T00:00Z"
    )
    line = InventoryTransactionLine.objects.create(
        transaction=movement, material=material, quantity=Decimal("1000.25")
    )
    assert requirement.quantity == Decimal("120.125")
    assert line.quantity == Decimal("1000.25")
    assert requirement.material.unit.code == line.material.unit.code == "g"
