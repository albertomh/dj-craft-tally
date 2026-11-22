from typing import ClassVar

from django.contrib import admin
from django.db.models.fields import Field
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from dj_craft_tally.admin._utils import (
    _WIDE_TEXTAREA_MIN_WIDTH,
    DateTimeLayoutAdmin,
    textarea_overrides,
)
from dj_craft_tally.models import (
    Activity,
    ActivityMaterial,
    ActivityMeasurement,
    Process,
    ProcessStep,
    Project,
    ProjectSchedule,
    ProjectStatusChange,
    ProjectStockReservation,
)


class ProcessStepInline(admin.TabularInline):
    model = ProcessStep
    extra = 0


@admin.register(Process)
class ProcessAdmin(admin.ModelAdmin):
    inlines: ClassVar = (ProcessStepInline,)
    list_display: ClassVar = ("name", "workshop")
    list_filter: ClassVar = ("workshop",)
    search_fields: ClassVar = ("name", "description")


@admin.register(ProcessStep)
class ProcessStepAdmin(admin.ModelAdmin):
    list_display: ClassVar = ("name", "process", "sequence")
    list_filter: ClassVar = ("process__workshop", "process")
    search_fields: ClassVar = ("name", "process__name")
    formfield_overrides: ClassVar = textarea_overrides(
        rows=5, min_width=_WIDE_TEXTAREA_MIN_WIDTH
    )


class ProjectStatusChangeInline(admin.TabularInline):
    model = ProjectStatusChange
    can_delete = False
    extra = 0
    readonly_fields: ClassVar = (
        "previous_status",
        "status",
        "occurred_at",
        "recorded_at",
        "notes",
    )
    ordering: ClassVar = ("-occurred_at", "-recorded_at")

    def has_add_permission(self, request, obj=None) -> bool:
        return False


class ProjectScheduleInline(admin.TabularInline):
    model = ProjectSchedule
    extra = 0


@admin.register(Project)
class ProjectAdmin(DateTimeLayoutAdmin):
    inlines: ClassVar = (ProjectScheduleInline, ProjectStatusChangeInline)
    list_display: ClassVar = ("name", "workshop", "blueprint", "status", "completed_at")
    list_filter: ClassVar = ("workshop", "status")
    search_fields: ClassVar = ("name", "description")
    formfield_overrides: ClassVar = textarea_overrides(
        rows=2, min_width=_WIDE_TEXTAREA_MIN_WIDTH
    )

    class Media:
        css: ClassVar = {
            "all": (
                "dj_craft_tally/css/datetime_layout.css",
                "dj_craft_tally/css/project_status_history.css",
            )
        }


@admin.register(ProjectStatusChange)
class ProjectStatusChangeAdmin(admin.ModelAdmin):
    list_display: ClassVar = (
        "occurred_at",
        "project_link",
        "previous_status",
        "status",
        "notes",
    )
    list_filter: ClassVar = ("status",)
    list_select_related: ClassVar = ("project",)
    ordering: ClassVar = ("-occurred_at",)
    readonly_fields: ClassVar = (
        "project",
        "previous_status",
        "status",
        "occurred_at",
        "recorded_at",
        "notes",
    )

    @admin.display(description=_("Project"))
    def project_link(self, obj):
        project = obj.project
        if project:
            url = reverse("admin:crafttally_project_change", args=(project.pk,))
            return format_html(r'<a href="{}">{}</a>', url, project)
        return "-"

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return False


class ProjectStockReservationInline(admin.TabularInline):
    model = ProjectStockReservation
    extra = 0
    autocomplete_fields: ClassVar = ("material",)

    def formfield_for_dbfield(self, db_field: Field, request, **kwargs) -> Field | None:
        formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
        if db_field.name == "material" and formfield is not None:
            formfield.widget.can_add_related = False
            formfield.widget.can_delete_related = False
        return formfield


@admin.register(ProjectSchedule)
class ProjectScheduleAdmin(DateTimeLayoutAdmin):
    inlines: ClassVar = (ProjectStockReservationInline,)
    list_display: ClassVar = ("project", "starts_at", "status")
    list_filter: ClassVar = ("status", "project__workshop")
    list_select_related: ClassVar = ("project",)
    search_fields: ClassVar = ("project__name", "notes")
    formfield_overrides: ClassVar = textarea_overrides(
        rows=2, min_width=_WIDE_TEXTAREA_MIN_WIDTH
    )


@admin.register(ProjectStockReservation)
class ProjectStockReservationAdmin(admin.ModelAdmin):
    list_display: ClassVar = ("schedule_entry", "material", "quantity")
    list_filter: ClassVar = ("material",)
    formfield_overrides: ClassVar = textarea_overrides(
        rows=5, min_width=_WIDE_TEXTAREA_MIN_WIDTH
    )


class ActivityMeasurementInline(admin.TabularInline):
    model = ActivityMeasurement
    extra = 0
    formfield_overrides: ClassVar = textarea_overrides(rows=1, min_width=200)


class ActivityMaterialInline(admin.TabularInline):
    model = ActivityMaterial
    extra = 0


@admin.register(Activity)
class ActivityAdmin(DateTimeLayoutAdmin):
    fields: ClassVar = (
        "workshop",
        "project",
        "name",
        "process_step",
        "blueprint",
        "equipment",
        "reference",
        "cost",
        "outcome",
        "occurred_at",
        "notes",
    )
    inlines: ClassVar = (ActivityMaterialInline, ActivityMeasurementInline)
    list_display: ClassVar = (
        "reference",
        "project",
        "name",
        "workshop",
        "equipment",
        "outcome",
        "occurred_at",
    )
    list_select_related: ClassVar = ("workshop", "project", "equipment")
    list_filter: ClassVar = ("workshop", "outcome", "equipment")
    formfield_overrides: ClassVar = textarea_overrides(
        rows=2, min_width=_WIDE_TEXTAREA_MIN_WIDTH
    )
