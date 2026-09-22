# dj-craft-tally contributor guide

## Purpose and scope

`dj-craft-tally` is a Django app that provides the domain core for tracking
workshop inventory and crafting projects to completion. It should be useful
on its own in a host Django project, chiefly through Django admin.

Model real-world materials and transformations clearly: what is on hand, where
it is stored, how much is available, and what inputs become which outputs. Keep
the data model capable of supporting estimates such as how many units of a
design can be made from remaining material. Defer unrelated SaaS concerns,
such as workflow visualisation, unless they need a small, stable domain
extension here.

## Design principles

- This is a reusable Django package, not a site. Do not add project-level
  settings, user/account assumptions, or a required custom UI.
- Prefer Django's conventions and a high-quality Django admin experience:
  useful labels, help text, list displays, search, filters, ordering, and
  validation.
- Keep public APIs intentionally small and documented. Favour explicit domain
  services and model methods over hidden signals or framework magic.
- Make stock changes auditable and avoid silently mutating quantities. Use
  precise units and `Decimal`-appropriate values rather than floats for
  measurements.
- Design for host-project extensibility: use relations and documented hooks in
  preference to assuming ownership of authentication or tenancy.
- Migrations are part of the public integration contract. Keep them focused,
  reversible where Django supports it, and accompanied by migration tests when
  risk warrants it.

## Supported versions and tooling

- Develop against Python 3.14 and Django 6.1 by default. The authoritative
  supported-version matrix remains `pyproject.toml`.
- Use `uv` for dependencies and commands. Do not hand-edit `uv.lock`.
- Tests use `pytest`; the project aims for 100% coverage. Run the focused tests
  during development, then run `uvx nox` for the latest supported pairing.
  Run `uvx nox -s test` when changing compatibility-sensitive or core behavior.
- Run the configured pre-commit checks with `prek run --all-files` when
  available before handing off a substantial change.

## Repository layout

- Package code: `src/dj_craft_tally/`
- Tests: `tests/`
- Packaging and lint configuration: `pyproject.toml`
- Cross-version test matrix: `noxfile.py`

Keep tests parallel to the package behavior they exercise. Tests must use
isolated data and must not require a consumer project.

## Change workflow

1. Read the existing model, migration, admin, and test conventions before
   adding a new domain concept.
2. Add or update tests that express the intended public behavior, including
   validation and edge cases for quantities, units, and transformations.
3. Implement the smallest coherent change, with admin support when it exposes
   a user-managed model.
4. Generate and review migrations; never edit an already-released migration.
5. Run relevant checks and report commands that could not be run.

## Boundaries

SaaS apps that consume this package may add accounts, billing, permissions,
collaboration, and proprietary workflow features.
Keep generic inventory/project capabilities in this package only when they are
valuable to independent Django adopters and can remain free of SaaS-specific
assumptions. Coordinate compatible releases rather than importing web-app code
or creating a circular dependency.

## Git

Keep commits small and single-purpose. Write conventional commit messages.
When Codex creates a commit, include:

```text
Co-authored-by: Codex <codex@openai.com>
```
