"""Shared, isolated objects for domain tests."""

import pytest

from dj_craft_tally.models import Blueprint, Material, Unit, Workshop


@pytest.fixture
def workshop(db):
    return Workshop.objects.create(name="Studio")


@pytest.fixture
def gram(db):
    return Unit.objects.get(code="g")


@pytest.fixture
def item(db):
    return Unit.objects.get(code="item")


@pytest.fixture
def material(workshop, gram):
    return Material.objects.create(workshop=workshop, name="Clay", unit=gram)


@pytest.fixture
def blueprint(workshop, item):
    return Blueprint.objects.create(
        workshop=workshop, name="Cup", output_name="Cup", output_unit=item
    )
