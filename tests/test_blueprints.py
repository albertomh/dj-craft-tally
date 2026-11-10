from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

import dj_craft_tally.admin as tally_admin
from dj_craft_tally.models import (
    BlueprintMaterialRequirement,
    Material,
    Unit,
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


@pytest.mark.django_db
def test_requirement_form_preserves_significant_digits(material, blueprint):
    requirement = BlueprintMaterialRequirement.objects.create(
        blueprint=blueprint, material=material, quantity=Decimal("1.2345")
    )
    form = tally_admin.BlueprintMaterialRequirementForm(instance=requirement)
    assert str(form.initial["quantity"]) == "1.2345"
    assert form.fields["quantity"].widget.attrs["step"] == "0.0001"
    requirement.quantity = Decimal("1.200000")
    requirement.save()
    form = tally_admin.BlueprintMaterialRequirementForm(instance=requirement)
    assert str(form.initial["quantity"]) == "1.20"
    assert 'value="1.20"' in str(form["quantity"])
    assert form.fields["quantity"].widget.attrs["step"] == "0.01"
    bound = tally_admin.BlueprintMaterialRequirementForm(
        instance=requirement,
        data={
            "blueprint": str(blueprint.pk),
            "material": str(material.pk),
            "quantity": "1.20",
            "notes": "",
        },
    )
    assert bound.is_valid()
    assert not bound.has_changed()
    requirement.quantity = Decimal("NaN")
    tally_admin.BlueprintMaterialRequirementForm(instance=requirement)


@pytest.mark.django_db
def test_requirement_form_uses_stock_unit_precision(workshop, blueprint, item):
    tally_admin.BlueprintMaterialRequirementForm()
    tally_admin.BlueprintMaterialRequirementForm(
        instance=BlueprintMaterialRequirement(quantity=Decimal("1"))
    )
    material = Material.objects.create(
        workshop=workshop, name="Clay", unit=Unit.objects.get(code="kg")
    )
    requirement = BlueprintMaterialRequirement.objects.create(
        blueprint=blueprint, material=material, quantity=Decimal("0.0025")
    )
    form = tally_admin.BlueprintMaterialRequirementForm(instance=requirement)
    assert str(form.initial["quantity"]) == "0.0025"
    assert form.fields["quantity"].widget.attrs["step"] == "0.0001"
    count_material = Material.objects.create(workshop=workshop, name="Bolts", unit=item)
    count_requirement = BlueprintMaterialRequirement.objects.create(
        blueprint=blueprint, material=count_material, quantity=Decimal("2")
    )
    count_form = tally_admin.BlueprintMaterialRequirementForm(instance=count_requirement)
    assert str(count_form.initial["quantity"]) == "2"
    assert count_form.fields["quantity"].widget.attrs["step"] == "1"
