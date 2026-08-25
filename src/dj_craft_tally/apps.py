from django.apps import AppConfig


class DjCraftTallyConfig(AppConfig):
    name = "dj_craft_tally"
    verbose_name = "dj-craft-tally"

    def ready(self) -> None:
        print("Loaded 'dj-craft-tally'")  # noqa: T201
