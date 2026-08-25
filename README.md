# dj-craft-tally

`dj-craft-tally` is a Django app to help makers track projects and inventory in their workshop.

## Prerequisites

- A Django webapp using Django >= 4.2

## Install

1. Add as a dependency with `uv add dj-craft-tally`
2. In `settings.py`, add to `INSTALLED_APPS` after any first-party apps and before `django.contrib`
   packages.

## Develop

### Run tests

```sh
# run latest supported python/django pairing eg. 3.14/6.1
uvx nox

# run all test sessions
uvx nox -s test
```
