from datetime import UTC, datetime
from decimal import Decimal
from http import HTTPStatus

import pytest
from django.test import override_settings

from dj_craft_tally.models import CurrencyTransaction, Equipment, Workshop


@pytest.mark.django_db
def test_equipment_supports_generic_technology() -> None:
    printer = Equipment.objects.create(
        workshop=Workshop.objects.create(name="Home workshop"),
        name="Resin printer",
        kind=Equipment.Kind.THREE_D_PRINTER,
        technology="resin",
    )

    assert printer.technology == "resin"


@pytest.mark.django_db
def test_equipment_admin_shows_linked_purchase(client, django_user_model):
    user = django_user_model.objects.create_superuser(username="admin", password="pw")
    client.force_login(user)
    workshop = Workshop.objects.create(name="Workshop")
    equipment = Equipment.objects.create(workshop=workshop, name="Caliper")
    CurrencyTransaction.objects.create(
        workshop=workshop,
        equipment=equipment,
        description="Caliper purchase",
        created_at=datetime(2026, 1, 3, 12, tzinfo=UTC),
        amount=Decimal("-112.28"),
        currency_id="GBP",
    )
    with override_settings(ROOT_URLCONF="tests.admin_urls", ALLOWED_HOSTS=["testserver"]):
        response = client.get(f"/admin/crafttally/equipment/{equipment.pk}/change/")
    assert response.status_code == HTTPStatus.OK
    assert b"Caliper purchase" in response.content
    assert b"112.28" in response.content
    assert b"2026-01-03" in response.content
