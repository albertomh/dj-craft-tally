from decimal import Decimal

import pytest

from dj_craft_tally.models import (
    Blueprint,
    BlueprintMaterialRequirement,
    InventoryTransaction,
    InventoryTransactionLine,
    Material,
    Unit,
    Workshop,
)


@pytest.mark.django_db
def test_balances_and_complete_blueprint_runs() -> None:
    studio = Workshop.objects.create(name="Studio")
    gram = Unit.objects.get(code="g")
    clay = Material.objects.create(name="Clay", unit=gram, workshop=studio)
    glaze = Material.objects.create(name="Glaze", unit=gram, workshop=studio)
    blueprint = Blueprint.objects.create(
        name="Cup",
        output_name="Cup",
        output_unit=Unit.objects.get(code="item"),
        output_quantity=2,
        workshop=studio,
    )
    assert clay.stock_balance() == 0
    assert blueprint.available_runs() is None
    assert blueprint.available_output() is None
    for item, quantity in [(clay, 100), (clay, -10), (glaze, 12)]:
        movement = InventoryTransaction.objects.create(
            workshop=studio, kind="adjust", occurred_at="2026-01-01T00:00Z"
        )
        InventoryTransactionLine.objects.create(
            transaction=movement, material=item, quantity=quantity
        )
        movement.post()
    BlueprintMaterialRequirement.objects.create(
        blueprint=blueprint, material=clay, quantity=Decimal("20")
    )
    BlueprintMaterialRequirement.objects.create(
        blueprint=blueprint, material=glaze, quantity=Decimal("5")
    )
    assert clay.stock_balance() == Decimal("90")
    assert blueprint.available_runs() == int("2")
    assert blueprint.available_output() == Decimal("4")

    movement = InventoryTransaction.objects.create(
        workshop=studio, kind="adjust", occurred_at="2026-01-01T00:00Z"
    )
    InventoryTransactionLine.objects.create(
        transaction=movement, material=glaze, quantity=-20
    )
    movement.post()
    assert blueprint.available_runs() == 0
