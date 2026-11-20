from http import HTTPStatus

import pytest
from django.core.exceptions import ValidationError
from django.test import override_settings

from dj_craft_tally.models import Equipment, EquipmentMaterial, Material, Workshop


@pytest.mark.django_db
def test_equipment_can_have_multiple_material_roles(material, item):
    equipment = Equipment.objects.create(workshop=material.workshop, name="Printer")
    replacement = Material.objects.create(
        workshop=material.workshop, name="FEP film", unit=item
    )

    EquipmentMaterial.objects.create(
        equipment=equipment, material=material, role=EquipmentMaterial.Role.INPUT
    )
    EquipmentMaterial.objects.create(
        equipment=equipment,
        material=replacement,
        role=EquipmentMaterial.Role.REPLACEMENT,
    )

    assert list(equipment.material_associations.values_list("role", flat=True)) == [
        EquipmentMaterial.Role.INPUT,
        EquipmentMaterial.Role.REPLACEMENT,
    ]


@pytest.mark.django_db
def test_equipment_material_rejects_cross_workshop_links(material):
    other_workshop = Workshop.objects.create(name="Other workshop")
    equipment = Equipment.objects.create(workshop=other_workshop, name="Printer")
    association = EquipmentMaterial(equipment=equipment, material=material)

    with pytest.raises(ValidationError, match="same workshop"):
        association.full_clean()


@pytest.mark.django_db
def test_equipment_admin_displays_material_inline(client, django_user_model, material):
    user = django_user_model.objects.create_superuser(username="admin", password="pw")
    client.force_login(user)
    equipment = Equipment.objects.create(workshop=material.workshop, name="Printer")
    EquipmentMaterial.objects.create(
        equipment=equipment, material=material, role=EquipmentMaterial.Role.INPUT
    )

    with override_settings(ROOT_URLCONF="tests.admin_urls", ALLOWED_HOSTS=["testserver"]):
        response = client.get(f"/admin/crafttally/equipment/{equipment.pk}/change/")

    assert response.status_code == HTTPStatus.OK
    assert material.name.encode() in response.content
    assert b"Input" in response.content
