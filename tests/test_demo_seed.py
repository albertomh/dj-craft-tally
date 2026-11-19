import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path


def seeded_table_counts(connection):
    tables = [
        row[0]
        for row in connection.execute(
            "select name from sqlite_master where type = 'table' "
            "and name glob 'crafttally_*' order by name"
        )
    ]
    return {
        table: connection.execute(f'select count(*) from "{table}"').fetchone()[0]
        for table in tables
    }


def test_demo_seed_creates_repeatable_sample_data(tmp_path):
    root = Path(__file__).resolve().parent.parent
    db_path = tmp_path / "demo.sqlite3"
    (tmp_path / "seed_test_settings.py").write_text(
        "from demo_project.settings import *\n"
        "DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', "
        f"'NAME': {str(db_path)!r}}}}}\n"
    )
    env = os.environ.copy()
    env["DJANGO_SETTINGS_MODULE"] = "seed_test_settings"
    env["PYTHONPATH"] = os.pathsep.join([str(tmp_path), str(root / "demo")])

    def run(*args):
        return subprocess.run(
            [sys.executable, str(root / "demo" / "manage.py"), *args],
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )

    run("migrate", "--noinput")
    result = run("seed_demo")
    assert "Created demo data" in result.stdout
    assert "material's stock unit" in result.stdout
    with closing(sqlite3.connect(db_path)) as connection:
        first_counts = seeded_table_counts(connection)
        assert first_counts["crafttally_workshop"] > 0
        assert first_counts["crafttally_material"] > 0
        assert first_counts["crafttally_material_lot"] > 0
        assert first_counts["crafttally_blueprint"] > 0
        assert first_counts["crafttally_project"] > 0
        assert first_counts["crafttally_currency"] > 0
        assert first_counts["crafttally_inventory_tx"] > 0
        assert first_counts["crafttally_inventory_tx_line"] > 0

        assert (
            connection.execute(
                "select count(*) from crafttally_inventory_tx_line as line "
                "join crafttally_inventory_tx as tx on tx.id = line.transaction_id "
                "join crafttally_material as material on material.id = line.material_id "
                "where tx.workshop_id != material.workshop_id"
            ).fetchone()[0]
            == 0
        )
        assert (
            connection.execute(
                "select count(*) from crafttally_blueprint_material_req as requirement "
                "join crafttally_blueprint as blueprint "
                "on blueprint.id = requirement.blueprint_id "
                "join crafttally_material as material "
                "on material.id = requirement.material_id "
                "where blueprint.workshop_id != material.workshop_id"
            ).fetchone()[0]
            == 0
        )
        assert (
            connection.execute(
                "select count(distinct status) from crafttally_project"
            ).fetchone()[0]
            > 1
        )
        assert (
            connection.execute(
                "select count(*) from crafttally_currencytransaction "
                "where material_lot_id is not null"
            ).fetchone()[0]
            > 0
        )

    result = run("seed_demo")
    assert "already exists" in result.stdout
    with closing(sqlite3.connect(db_path)) as connection:
        assert seeded_table_counts(connection) == first_counts
