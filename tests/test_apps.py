import dj_craft_tally
from dj_craft_tally.apps import DjCraftTallyConfig


def test_app_config():
    """
    Temporary measure to avoid pytest emitting 'exit code 5' because there are no tests.
    """
    config = DjCraftTallyConfig("dj_craft_tally", dj_craft_tally)

    assert config.name == "dj_craft_tally"
