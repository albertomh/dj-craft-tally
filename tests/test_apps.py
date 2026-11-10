from django.contrib import admin

from dj_craft_tally.models import Unit


def test_unit_is_registered_in_django_admin():
    assert admin.site.is_registered(Unit)
