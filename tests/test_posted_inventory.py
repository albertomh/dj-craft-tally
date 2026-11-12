from decimal import Decimal

import pytest
from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import RequestFactory
from django.utils import timezone

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


@pytest.mark.django_db
def test_inventory_transaction_admin_displays_associated_lines(workshop):
    request = RequestFactory().get("/")
    request.user = get_user_model()(is_staff=True, is_superuser=True)
    entry = InventoryTransaction.objects.create(
        workshop=workshop, kind="receive", occurred_at="2026-01-01T00:00Z"
    )
    transaction_admin = admin.site._registry[InventoryTransaction]
    inline = transaction_admin.get_inline_instances(request, entry)[0]

    assert inline.model is InventoryTransactionLine
    assert inline.fields == ("material", "material_lot", "quantity", "notes")
    assert inline.readonly_fields == inline.fields
    assert not inline.has_add_permission(request, entry)
    assert not inline.has_delete_permission(request, entry)


@pytest.mark.django_db
def test_posting_an_already_posted_transaction_is_rejected(workshop, material):
    entry = InventoryTransaction.objects.create(
        workshop=workshop, kind="receive", occurred_at="2026-01-01T00:00Z"
    )
    InventoryTransactionLine.objects.create(
        transaction=entry, material=material, quantity=Decimal("10")
    )
    entry.post()
    with pytest.raises(ValidationError, match="already posted"):
        entry.post()


@pytest.mark.django_db
def test_line_cannot_be_added_through_an_in_memory_posted_transaction(workshop, material):
    entry = InventoryTransaction.objects.create(
        workshop=workshop, kind="receive", occurred_at="2026-01-01T00:00Z"
    )
    entry.posted = True
    with pytest.raises(ValidationError, match="posted transaction"):
        InventoryTransactionLine.objects.create(
            transaction=entry, material=material, quantity=1
        )


@pytest.mark.django_db
def test_ledger_queryset_bulk_methods_are_rejected(workshop):
    queryset = InventoryTransaction.objects.filter(workshop=workshop)
    for operation in (
        lambda: queryset.bulk_update([], []),
        lambda: queryset.bulk_create([]),
    ):
        with pytest.raises(ValidationError, match="Bulk"):
            operation()


@pytest.mark.django_db
def test_inventory_admin_protects_posted_records(workshop, material):
    request = RequestFactory().get("/")
    request.user = get_user_model()(is_staff=True, is_superuser=True)
    transaction_admin = admin.site._registry[InventoryTransaction]
    posted = InventoryTransaction.objects.create(
        workshop=workshop,
        kind=InventoryTransaction.Kind.RECEIVE,
        occurred_at=timezone.now(),
    )
    posted.posted = True
    assert "kind" in transaction_admin.get_readonly_fields(request, posted)
    assert transaction_admin.get_readonly_fields(request) == ("posted",)
    assert "delete_selected" not in transaction_admin.get_actions(request)
    line_admin = admin.site._registry[InventoryTransactionLine]
    line = InventoryTransactionLine.objects.create(
        transaction=InventoryTransaction.objects.create(
            workshop=workshop,
            kind=InventoryTransaction.Kind.RECEIVE,
            occurred_at=timezone.now(),
        ),
        material=material,
        quantity=1,
    )
    line.transaction.posted = True
    assert "quantity" in line_admin.get_readonly_fields(request, line)
    assert line_admin.get_readonly_fields(request) == ()
    assert "delete_selected" not in line_admin.get_actions(request)


@pytest.mark.django_db
def test_post_transactions_reports_validation_errors(workshop, monkeypatch):
    request = RequestFactory().get("/")
    entry = InventoryTransaction.objects.create(
        workshop=workshop,
        kind=InventoryTransaction.Kind.RECEIVE,
        occurred_at=timezone.now(),
    )
    reported = []
    transaction_admin = admin.site._registry[InventoryTransaction]
    monkeypatch.setattr(
        transaction_admin,
        "message_user",
        lambda request, message, level: reported.append((message, level)),
    )
    transaction_admin.post_transactions(request, [entry])
    assert reported == [
        ("['An inventory transaction needs at least one line.']", messages.ERROR)
    ]
