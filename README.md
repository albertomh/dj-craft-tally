# dj-craft-tally

<!-- markdownlint-disable MD013 line-length -->
![python >= 3.10](https://img.shields.io/badge/Python>=3.10-4584b6?logo=python&logoColor=ffde57&style=flat-square)
[![Django >= 4.2](https://img.shields.io/badge/Django>=4.2-092E20?logo=django&logoColor=ffffff&style=flat-square)](https://docs.djangoproject.com/en/stable/)
[![prek](https://img.shields.io/badge/prek-CC5A23?logo=prek&logoColor=FFFFFF&style=flat-square)](https://github.com/j178/prek)
[![pytest](https://img.shields.io/badge/pytest-0A9EDC?logo=pytest&logoColor=white&style=flat-square)](https://github.com/pytest-dev/pytest)
[![nox](https://img.shields.io/badge/%F0%9F%A6%8A-Nox-D85E00.svg?style=flat-square)](https://github.com/wntrblm/nox)
[![coverage](https://img.shields.io/badge/😴_coverage-59aabd?style=flat-square)](https://coverage.readthedocs.io/)
[![GitHub Actions Workflow Status](https://img.shields.io/github/actions/workflow/status/albertomh/dj-craft-tally/ci.yaml?style=flat-square&logo=github&label=CI&labelColor=000000)](https://github.com/albertomh/dj-craft-tally/actions/workflows/ci.yaml)
<!--[![PyPI Version](https://img.shields.io/pypi/v/dj-craft-tally?style=flat-square&labelColor=0073b7&color=0073b7&label=📦%20PyPI)](https://pypi.org/project/dj-craft-tally/)-->
<!-- markdownlint-enable MD013 line-length -->

`dj-craft-tally` is a Django app to help makers track projects and inventory in their workshop.

## Prerequisites

- A Django webapp using Django >= 4.2

## Install

1. Add as a dependency:

    ```sh
    uv add dj-craft-tally`
    ```

1. In `settings.py`, add to `INSTALLED_APPS` after any first-party apps and before
`django.contrib` packages.

    ```python
    INSTALLED_APPS = [
        ...,
        'dj_craft_tally',
        ...,
    ]
    ```

## Features

<!-- TODO... -->

## Develop

### Development prerequisites

The following tools must be available locally to develop `dj-craft-tally`:

- [uv](https://docs.astral.sh/uv/)
- [prek](https://prek.j178.dev/)

### Run tests

The project aims for 100% test coverage. `nox` is used to run the test suite against
all supported Python/Django pairings (see [`noxfile.py`](./noxfile.py#L5)).

```sh
# run latest supported Python/Django pairing only
# (eg. Python 3.14 / Django 6.1)
uvx nox

# run all test sessions (ie. all supported Python/Django pairings)
uvx nox -s test
```

### Use the development version in projects

Build the package as a binary distribution (wheel) and install it in a Django project:

```sh
# from dj-craft-tally's root directory
uv build

# in the target Django webapp project
uv add ~/Projects/dj-craft-tally/dist/dj_craft_tally-M.m.p-py3-none-any.whl
```
