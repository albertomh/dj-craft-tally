from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from dj_craft_tally.models import (
    Blueprint,
    BlueprintMaterialRequirement,
    Material,
    Unit,
    Workshop,
)


@pytest.mark.django_db
def test_blueprint_rejects_material_from_another_workshop() -> None:
    workshop = Workshop.objects.create(name="Home")
    material = Material.objects.create(
        name="PLA",
        unit=Unit.objects.get(code="g"),
        workshop=Workshop.objects.create(name="Elsewhere"),
    )
    blueprint = Blueprint.objects.create(
        name="Guide",
        output_name="Guide",
        output_unit=Unit.objects.get(code="item"),
        workshop=workshop,
    )

    with pytest.raises(ValidationError, match="blueprint's workshop"):
        BlueprintMaterialRequirement.objects.create(
            blueprint=blueprint, material=material, quantity=Decimal("1")
        )
