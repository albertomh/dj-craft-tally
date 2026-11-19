"""Shared, isolated objects for domain tests."""

import pytest
from django.utils import timezone

from dj_craft_tally.models import (
    Blueprint,
    CurrencyTransaction,
    Material,
    MaterialLot,
    Unit,
    Workshop,
)


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


def create_priced_lot(
    *, purchase_amount=None, purchase_currency=None, purchase_currency_id=None, **kwargs
):
    lot = MaterialLot.objects.create(**kwargs)
    if purchase_amount is not None:
        CurrencyTransaction.objects.create(
            workshop=lot.material.workshop,
            material_lot=lot,
            description="Material purchase",
            amount=-purchase_amount,
            currency=purchase_currency,
            currency_id=purchase_currency_id
            or (purchase_currency.pk if purchase_currency else None),
            created_at=lot.received_at or timezone.now(),
        )
    return lot
