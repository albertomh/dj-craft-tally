from typing import ClassVar

from django.contrib import admin
from django.db import models
from django.forms import Textarea

_WIDE_TEXTAREA_MIN_WIDTH = 500


class DateTimeLayoutAdmin(admin.ModelAdmin):
    class Media:
        css: ClassVar = {"all": ("dj_craft_tally/css/datetime_layout.css",)}


def textarea_overrides(*, rows: int, min_width: int) -> dict:
    return {
        models.TextField: {
            "widget": Textarea(
                attrs={"rows": rows, "style": f"min-width: {min_width}px;"}
            )
        },
    }
