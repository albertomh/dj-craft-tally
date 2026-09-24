import pytest

from dj_craft_tally.models import Equipment, Workshop


@pytest.mark.django_db
def test_equipment_supports_generic_technology() -> None:
    printer = Equipment.objects.create(
        workshop=Workshop.objects.create(name="Home workshop"),
        name="Resin printer",
        kind=Equipment.Kind.THREE_D_PRINTER,
        technology="resin",
    )

    assert printer.technology == "resin"
