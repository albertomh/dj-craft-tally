from __future__ import annotations

import nox

# <https://www.djangoproject.com/download/#:~:text=Supported%20Versions>
SUPPORTED = {
    "3.10": ("4.2", "5.2"),
    "3.11": ("4.2", "5.2"),
    "3.12": ("4.2", "5.2", "6.0", "6.1"),
    "3.13": ("5.2", "6.0", "6.1"),
    "3.14": ("6.0", "6.1"),
}

MATRIX = [(python, django) for python, djangos in SUPPORTED.items() for django in djangos]

nox.options.default_venv_backend = "uv|virtualenv"
nox.options.sessions = [f"test(python='{MATRIX[-1][0]}', django='{MATRIX[-1][1]}')"]


def _install_deps(session: nox.Session, django_version: str) -> None:
    session.run_install(
        "uv",
        "sync",
        "--group=test",
        f"--python={session.virtualenv.location}",
        env={"UV_PROJECT_ENVIRONMENT": session.virtualenv.location},
    )
    session.install(f"django~={django_version}.0")


@nox.session
@nox.parametrize(("python", "django"), MATRIX)
def test(session: nox.Session, python: str, django: str) -> None:
    _install_deps(session, django)

    session.run("coverage", "erase")

    session.run(
        "coverage",
        "run",
        "-m",
        "pytest",
        "tests/",
        *session.posargs,
        env={"PYTHONDEVMODE": "1"},
    )

    # combine data from parallel processes
    session.run("coverage", "combine")
    session.run("coverage", "report")
    session.run("coverage", "html")
