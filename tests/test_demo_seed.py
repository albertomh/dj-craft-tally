import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path


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
    assert "material's stock unit" in result.stdout
    run("seed_demo")
    with closing(sqlite3.connect(db_path)) as connection:
        assert (
            connection.execute(
                "select count(*) from auth_user where username = 'demo'"
            ).fetchone()[0]
            == 1
        )
        assert (
            connection.execute("select count(*) from crafttally_workshop").fetchone()[0]
            == 2  # noqa: PLR2004
        )
        assert (
            connection.execute("select count(*) from crafttally_material_lot").fetchone()[
                0
            ]
            == 2  # noqa: PLR2004
        )
        tx_fields = {
            row[1]
            for row in connection.execute("pragma table_info(crafttally_inventory_tx)")
        }
        assert connection.execute(
            "select count(*) from crafttally_inventory_tx"
        ).fetchone()[0] == (5 if "posted" in tx_fields else 4)
        if "posted" in tx_fields:
            assert (
                connection.execute(
                    "select count(*) from crafttally_inventory_tx where posted = 1"
                ).fetchone()[0]
                == 4  # noqa: PLR2004
            )
        assert (
            connection.execute("select count(*) from crafttally_project").fetchone()[0]
            == 1
        )
        line_fields = {
            row[1]
            for row in connection.execute(
                "pragma table_info(crafttally_inventory_tx_line)"
            )
        }
        assert "unit_id" not in line_fields
        requirement_fields = {
            row[1]
            for row in connection.execute(
                "pragma table_info(crafttally_blueprint_material_req)"
            )
        }
        assert "unit_id" not in requirement_fields
        assert (
            connection.execute(
                "select quantity from crafttally_blueprint_material_req "
                "where material_id = (select id from crafttally_material "
                "where name = 'Blue PLA filament')"
            ).fetchone()[0]
            == 120  # noqa: PLR2004
        )
