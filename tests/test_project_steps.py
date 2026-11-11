import pytest
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.test import RequestFactory

from dj_craft_tally.models import (
    Blueprint,
    Equipment,
    Project,
    ProjectStep,
    ProjectStepMeasurement,
    Unit,
    Workshop,
)


@pytest.mark.django_db
def test_project_steps_are_ordered_and_measurements_are_flexible() -> None:
    project = Project.objects.create(
        name="Tray", workshop=Workshop.objects.create(name="Home")
    )
    step = ProjectStep.objects.create(
        project=project, sequence=1, name="print", occurred_at="2026-01-01T12:00Z"
    )
    measurement = ProjectStepMeasurement.objects.create(
        project_step=step,
        name="actual duration",
        quantity=900,
        unit=Unit.objects.get(code="s"),
    )
    assert step.reference == f"step-{step.id}"
    assert list(project.steps.all()) == [step]
    assert list(step.measurements.all()) == [measurement]


@pytest.mark.django_db
def test_project_step_rejects_foreign_blueprint_and_equipment(workshop, item) -> None:
    project = Project.objects.create(name="Mug", workshop=workshop)
    other = Workshop.objects.create(name="Other")
    blueprint = Blueprint.objects.create(
        name="Other blueprint", output_name="Other", output_unit=item, workshop=other
    )
    equipment = Equipment.objects.create(
        name="Kiln", workshop=other, kind=Equipment.Kind.OTHER
    )
    step = ProjectStep(
        project=project,
        blueprint=blueprint,
        equipment=equipment,
        sequence=1,
        name="Fire",
        occurred_at="2026-01-01T12:00Z",
    )
    with pytest.raises(ValidationError, match="project's workshop"):
        step.full_clean()


def test_project_step_admin_requires_a_positive_sequence():
    step_admin = admin.site._registry[ProjectStep]
    field = step_admin.formfield_for_dbfield(
        ProjectStep._meta.get_field("sequence"), RequestFactory().get("/")
    )
    assert field.widget.attrs["min"] == 1
