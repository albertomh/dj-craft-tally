import pytest

from dj_craft_tally.models import (
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
