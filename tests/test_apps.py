from django.contrib import admin

import dj_craft_tally
from dj_craft_tally.apps import DjCraftTallyConfig
from dj_craft_tally.models import Unit


def test_app_config():
    """
    Temporary measure to avoid pytest emitting 'exit code 5' because there are no tests.
    """
    config = DjCraftTallyConfig("dj_craft_tally", dj_craft_tally)

    assert config.name == "dj_craft_tally"


def test_unit_is_registered_in_django_admin():
    assert admin.site.is_registered(Unit)
