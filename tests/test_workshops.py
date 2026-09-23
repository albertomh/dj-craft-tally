import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError

from dj_craft_tally.models import Workshop, WorkshopMembership


@pytest.mark.django_db
def test_workshop_membership_uses_the_host_projects_user_model() -> None:
    workshop = Workshop.objects.create(name="Home workshop")
    user = get_user_model().objects.create_user(username="maker")
    membership = WorkshopMembership.objects.create(
        workshop=workshop, user=user, role=WorkshopMembership.Role.OWNER
    )

    assert membership.user == user
    with pytest.raises(IntegrityError):
        WorkshopMembership.objects.create(workshop=workshop, user=user)
