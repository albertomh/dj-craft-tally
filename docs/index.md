# dj-craft-tally

`dj-craft-tally` is a reusable Django app for recording workshop materials and
crafting projects. It provides models and Django admin pages for a host project;
it does not provide a standalone site.

## Supported versions

| Python | Django |
| --- | --- |
| 3.10–3.11 | 5.2 |
| 3.12–3.13 | 5.2, 6.0, 6.1 |
| 3.14 | 6.0, 6.1 |

## Installation

In an existing Django project, add the package to your dependencies. Once it is
available on PyPI, you can use:

```sh
uv add dj-craft-tally
```

Until then, you can build a wheel from the source checkout with `uv build` and
install it in the host project with `uv add /path/to/the/most/recent.whl`.

Add the app to your host project's `INSTALLED_APPS`:

```python
INSTALLED_APPS = [
    # ... your other apps ...
    "dj_craft_tally",
]
```

Then run the migrations from the host project:

```sh
python manage.py migrate
```

The initial migration adds common units of count, mass, volume, length, area,
and time. Configure Django admin in the host project and sign in as a staff user
with permission to manage the app's models.

## Getting started in Django admin

1. Create a **Workshop**. Optionally add workshop memberships linked to users
   from the host project. Memberships record roles; they do not by themselves
   configure admin permissions.
2. Create a **Material**, selecting the workshop and its stock unit, such as
   grams for filament. Create a **Material lot** to record package count,
   quantity per package, supplier, and receipt details where relevant. Creating
   a lot automatically posts a receipt for the total package contents. Correct
   the quantity with a separate transaction rather than editing the receipt.
   Lots created before this feature are not backfilled, to avoid double counting
   receipts that were already entered manually.
3. To record a stock movement, create an **Inventory transaction** with its
   workshop, kind, and occurrence date. Then create an **Inventory transaction
   line** linked to it and the material. Quantities are signed: for example,
   enter `500` for stock received or `-42.5` for stock consumed, in the
   material's stock unit. A line may also reference a lot of that material.
   To use a different unit, first convert the amount to the material's stock
   unit before entering it.
   Post the transaction from its admin list after entering its lines. Drafts do
   not affect stock. Posted transactions and lines cannot be changed or deleted
   through the app; record corrections as new transactions. In Python, call
   `transaction.post()` after saving its lines.
4. Create a **Blueprint** for a repeatable output, and add its material
   requirements in the inline form. Each requirement is the amount needed for
   one run, in that material's stock unit. The admin shows stock balances,
   complete available runs, and the resulting output. Capacity is unknown when
   a blueprint has no requirements; it does not reserve stock for other work.
5. Create a **Project**, optionally linked to a blueprint in the same workshop.
   Record work as ordered **Project steps**, with optional equipment and
   measurements. Change the project status as work progresses; status changes
   appear in its history.

## Stability

The project is in early development and uses 0.x versions. Models, APIs, and
workflows may change between releases, including incompatibly. Review the
changelog and test upgrades on a backup before updating a host project.

## Development

Install the documentation tools and preview the site locally:

```sh
uv sync --group docs
uv run zensical serve
```

Build the static site with:

```sh
uv run zensical build --clean
```
