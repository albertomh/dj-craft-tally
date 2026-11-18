import pytest
from django.core.exceptions import ValidationError

from dj_craft_tally.models import (
    Activity,
    ActivityMeasurement,
    Blueprint,
    Equipment,
    Project,
    Unit,
    Workshop,
)


@pytest.mark.django_db
def test_activity_measurements_are_flexible() -> None:
    project = Project.objects.create(
        name="Tray", workshop=Workshop.objects.create(name="Home")
    )
    step = Activity.objects.create(
        project=project, name="print", occurred_at="2026-01-01T12:00Z"
    )
    measurement = ActivityMeasurement.objects.create(
        activity=step,
        name="actual duration",
        quantity=900,
        unit=Unit.objects.get(code="s"),
    )
    assert step.reference == f"step-{step.id}"
    assert list(project.activities.all()) == [step]
    assert list(step.measurements.all()) == [measurement]


@pytest.mark.django_db
def test_project_can_have_multiple_activities_without_order_numbers(workshop):
    project = Project.objects.create(name="Dragon", workshop=workshop)
    first = Activity.objects.create(project=project, name="Print")
    second = Activity.objects.create(project=project, name="Wash")
    assert list(project.activities.all()) == [second, first]
    assert str(first) == "Dragon: Print"


@pytest.mark.django_db
def test_activity_rejects_foreign_blueprint_and_equipment(workshop, item) -> None:
    project = Project.objects.create(name="Mug", workshop=workshop)
    other = Workshop.objects.create(name="Other")
    blueprint = Blueprint.objects.create(
        name="Other blueprint", output_name="Other", output_unit=item, workshop=other
    )
    equipment = Equipment.objects.create(
        name="Kiln", workshop=other, kind=Equipment.Kind.OTHER
    )
    step = Activity(
        project=project,
        blueprint=blueprint,
        equipment=equipment,
        name="Fire",
        occurred_at="2026-01-01T12:00Z",
    )
    with pytest.raises(ValidationError, match="activity's workshop"):
        step.full_clean()


def test_activity_ownership_guards_bulk_writes_and_project_moves(workshop):
    other = Workshop.objects.create(name="Other")
    project = Project.objects.create(name="Dice tower", workshop=workshop)
    activity = Activity.objects.create(project=project, name="Print")
    assert activity.workshop_id == workshop.pk
    with pytest.raises(ValidationError):
        Activity.objects.filter(pk=activity.pk).update(workshop=other)
    with pytest.raises(ValidationError):
        Activity.objects.bulk_update([activity], ["project"])
    with pytest.raises(ValidationError):
        Activity.objects.bulk_create(
            [Activity(workshop=other, project=project, name="Bad")]
        )
    with pytest.raises(ValidationError):
        Project.objects.filter(pk=project.pk).update(workshop=other)
    with pytest.raises(ValidationError):
        Project.objects.bulk_update([project], ["workshop"])
    project.workshop = other
    with pytest.raises(ValidationError, match="cannot change workshop"):
        project.save()


def test_bulk_updates_allow_non_ownership_fields(workshop):
    project = Project.objects.create(name="Dice tower", workshop=workshop)
    activity = Activity.objects.create(project=project, name="Print")

    assert Project.objects.filter(pk=project.pk).update(description="First") == 1
    project.name = "Dice tower print"
    assert Project.objects.bulk_update([project], ["name"]) == 1
    project.refresh_from_db()
    assert (project.name, project.description) == ("Dice tower print", "First")

    assert Activity.objects.filter(pk=activity.pk).update(notes="First") == 1
    activity.name = "Print dice tower"
    assert Activity.objects.bulk_update([activity], ["name"]) == 1
    activity.refresh_from_db()
    assert (activity.name, activity.notes) == ("Print dice tower", "First")
