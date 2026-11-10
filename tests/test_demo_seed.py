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
    run("seed_demo")
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
        assert connection.execute(
            "select count(*) from crafttally_inventory_tx"
        ).fetchone()[0] == int("4")
        assert (
            connection.execute("select count(*) from crafttally_project").fetchone()[0]
            == 1
        )
