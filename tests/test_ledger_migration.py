import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


@pytest.mark.django_db(transaction=True)
def test_existing_transactions_are_posted_on_upgrade():
    before = [("crafttally", "0008_inventory_ledger")]
    after = [("crafttally", "0009_inventorytransaction_posted")]
    executor = MigrationExecutor(connection)
    try:
        executor.migrate(before)
        old = executor.loader.project_state(before).apps
        workshop = old.get_model("crafttally", "Workshop").objects.create(name="Studio")
        entry = old.get_model("crafttally", "InventoryTransaction").objects.create(
            workshop=workshop, kind="receive", occurred_at="2026-01-01T00:00Z"
        )
        executor = MigrationExecutor(connection)
        executor.migrate(after)
        new = executor.loader.project_state(after).apps
        assert (
            new.get_model("crafttally", "InventoryTransaction")
            .objects.get(pk=entry.pk)
            .posted
        )
    finally:
        MigrationExecutor(connection).migrate(after)
