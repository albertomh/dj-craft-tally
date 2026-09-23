from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from dj_craft_tally.models import Unit


@pytest.mark.django_db
def test_initial_units_define_dimensions_and_base_scales() -> None:
    kilogram = Unit.objects.get(code="kg")

    assert kilogram.dimension == Unit.Dimension.MASS
    assert kilogram.scale_to_base == Decimal("1000")
    assert set(Unit.objects.values_list("code", flat=True)) == {
        "item",
        "g",
        "kg",
        "mL",
        "L",
        "mm",
        "cm",
        "m",
        "mm2",
        "cm2",
        "m2",
        "s",
        "min",
        "h",
    }


@pytest.mark.django_db
def test_unit_scale_cannot_exceed_the_supported_range() -> None:
    unit = Unit(
        code="large-unit",
        name="Large unit",
        symbol="large",
        dimension=Unit.Dimension.COUNT,
        scale_to_base=Decimal("1000000000"),
    )

    with pytest.raises(ValidationError, match="less than or equal"):
        unit.full_clean()
    with pytest.raises(IntegrityError):
        unit.save()
