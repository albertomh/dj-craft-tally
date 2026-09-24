import pytest
from django.core.exceptions import ValidationError

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
