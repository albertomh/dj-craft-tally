import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import RequestFactory

import dj_craft_tally.admin as tally_admin
from dj_craft_tally.models import Blueprint, Project, Unit, Workshop


@pytest.mark.django_db
def test_project_records_immutable_status_history() -> None:
    workshop = Workshop.objects.create(name="Home")
    project = Project.objects.create(name="Tray", workshop=workshop)
    project.set_status(Project.Status.STALLED, notes="Waiting")
    assert list(project.status_changes.values_list("status", flat=True)) == [
        "planned",
        "stalled",
    ]
    with pytest.raises(ValidationError):
        project.status_changes.first().delete()


@pytest.mark.django_db
def test_project_rejects_foreign_workshop_blueprint() -> None:
    blueprint = Blueprint.objects.create(
        name="Guide",
        output_name="Guide",
        output_unit=Unit.objects.get(code="item"),
        workshop=Workshop.objects.create(name="Other"),
    )
    with pytest.raises(ValidationError, match="project's workshop"):
        Project.objects.create(
            name="Bad", workshop=Workshop.objects.create(name="Home"), blueprint=blueprint
        )


@pytest.mark.django_db
def test_project_status_history_entries_cannot_be_changed() -> None:
    project = Project.objects.create(
        name="Tray", workshop=Workshop.objects.create(name="Home")
    )
    change = project.status_changes.first()
    change.notes = "Changed"
    with pytest.raises(ValidationError, match="cannot be changed"):
        change.save()


def test_project_status_history_inline_cannot_add_records():
    request = RequestFactory().get("/")
    assert not tally_admin.ProjectStatusChangeInline(
        Project, admin.site
    ).has_add_permission(request)


@pytest.mark.django_db
def test_project_status_history_inline_orders_newest_first():
    project = Project.objects.create(
        name="Tray",
        workshop=Workshop.objects.create(name="Home"),
        created_at="2026-01-01T00:00Z",
    )
    project.set_status(Project.Status.ACTIVE, occurred_at="2026-01-02T00:00Z")
    project.set_status(Project.Status.COMPLETE, occurred_at="2026-01-03T00:00Z")
    request = RequestFactory().get("/")
    request.user = get_user_model()(is_staff=True, is_superuser=True)

    changes = tally_admin.ProjectStatusChangeInline(Project, admin.site).get_queryset(
        request
    )

    assert list(changes.filter(project=project).values_list("status", flat=True)) == [
        Project.Status.COMPLETE,
        Project.Status.ACTIVE,
        Project.Status.PLANNED,
    ]
