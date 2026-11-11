from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError

from dj_craft_tally.models import (
    InventoryTransaction,
    InventoryTransactionLine,
)


@pytest.mark.django_db
def test_posting_locks_the_transaction_and_its_lines(workshop, material):
    entry = InventoryTransaction.objects.create(
        workshop=workshop, kind="receive", occurred_at="2026-01-01T00:00Z"
    )
    with pytest.raises(ValidationError, match="at least one line"):
        entry.post()
    line = InventoryTransactionLine.objects.create(
        transaction=entry, material=material, quantity=Decimal("10")
    )
    assert material.stock_balance() == 0
    stale = InventoryTransaction.objects.get(pk=entry.pk)
    entry.post()
    assert material.stock_balance() == Decimal("10")
    for operation in [
        entry.save,
        stale.delete,
        line.save,
        line.delete,
        lambda: InventoryTransactionLine.objects.create(
            transaction=entry, material=material, quantity=1
        ),
        lambda: InventoryTransaction.objects.filter(pk=entry.pk).update(notes="changed"),
        lambda: InventoryTransactionLine.objects.filter(pk=line.pk).delete(),
    ]:
        with pytest.raises(ValidationError):
            operation()
    assert material.stock_balance() == Decimal("10")
