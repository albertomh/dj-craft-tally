from decimal import Decimal

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import RequestFactory

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
    assert Unit.objects.get(code="item").display_decimal_places == 0


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


@pytest.mark.django_db
def test_unit_display_precision_is_editable_and_bounded(gram):
    gram.display_decimal_places = 3
    gram.full_clean()
    gram.save()
    gram.refresh_from_db()
    assert gram.display_decimal_places == 3  # noqa: PLR2004
    gram.display_decimal_places = 7
    with pytest.raises(ValidationError):
        gram.full_clean()
    unit_admin = admin.site._registry[Unit]
    request = RequestFactory().get("/")
    request.user = get_user_model().objects.create_superuser(
        username="admin", password="test"
    )
    assert "display_decimal_places" in unit_admin.get_form(request).base_fields
