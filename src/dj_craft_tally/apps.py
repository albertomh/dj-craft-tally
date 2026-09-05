from django.apps import AppConfig


class DjCraftTallyConfig(AppConfig):
    default_auto_field = "django.db.models.UUIDField"
    name = "dj_craft_tally"
    verbose_name = "dj-craft-tally"
    label = "craft_tally"

    def ready(self) -> None:
        print("Loaded 'dj-craft-tally'")  # noqa: T201
