from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from dj_craft_tally.models import (
    BlueprintMaterialRequirement,
    Material,
    Workshop,
)


@pytest.mark.django_db
def test_blueprint_rejects_material_from_another_workshop(blueprint, gram) -> None:
    material = Material.objects.create(
        name="PLA",
        unit=gram,
        workshop=Workshop.objects.create(name="Elsewhere"),
    )
    with pytest.raises(ValidationError, match="blueprint's workshop"):
        BlueprintMaterialRequirement.objects.create(
            blueprint=blueprint, material=material, quantity=Decimal("1")
        )
