from decimal import Decimal

import pytest

from dj_craft_tally.models import (
    BlueprintMaterialRequirement,
    InventoryTransaction,
    InventoryTransactionLine,
    Material,
)


@pytest.mark.django_db
def test_balances_and_complete_blueprint_runs(
    workshop, gram, blueprint, material
) -> None:
    clay = material
    glaze = Material.objects.create(name="Glaze", unit=gram, workshop=workshop)
    blueprint.output_quantity = 2
    assert clay.stock_balance() == 0
    assert blueprint.available_runs() is None
    assert blueprint.available_output() is None
    for stock_material, quantity in [(clay, 100), (clay, -10), (glaze, 12)]:
        movement = InventoryTransaction.objects.create(
            workshop=workshop, kind="adjust", occurred_at="2026-01-01T00:00Z"
        )
        InventoryTransactionLine.objects.create(
            transaction=movement, material=stock_material, quantity=quantity
        )
    BlueprintMaterialRequirement.objects.create(
        blueprint=blueprint, material=clay, quantity=Decimal("20")
    )
    BlueprintMaterialRequirement.objects.create(
        blueprint=blueprint, material=glaze, quantity=Decimal("5")
    )
    assert clay.stock_balance() == Decimal("90")
    assert blueprint.available_runs() == 2  # noqa: PLR2004
    assert blueprint.available_output() == Decimal("4")

    movement = InventoryTransaction.objects.create(
        workshop=workshop, kind="adjust", occurred_at="2026-01-01T00:00Z"
    )
    InventoryTransactionLine.objects.create(
        transaction=movement, material=glaze, quantity=-20
    )
    assert blueprint.available_runs() == 0
