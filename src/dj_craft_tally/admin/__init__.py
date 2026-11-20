"""Django admin registrations, split by model area."""

from dj_craft_tally.admin import (  # noqa: F401
    activities,
    core,
    currency,
    equipment,
    inventory,
    materials,
)
from dj_craft_tally.admin.activities import (
    ActivityAdmin,
    ProjectStatusChangeAdmin,
    ProjectStatusChangeInline,
)
from dj_craft_tally.admin.currency import CurrencyTransactionAdmin
from dj_craft_tally.admin.materials import (
    BlueprintAdmin,
    BlueprintMaterialRequirementForm,
    MaterialAdmin,
)
from dj_craft_tally.display import format_money, format_quantity
from dj_craft_tally.models import ProjectStatusChange

__all__ = [
    "ActivityAdmin",
    "BlueprintAdmin",
    "BlueprintMaterialRequirementForm",
    "CurrencyTransactionAdmin",
    "MaterialAdmin",
    "ProjectStatusChange",
    "ProjectStatusChangeAdmin",
    "ProjectStatusChangeInline",
    "format_money",
    "format_quantity",
]
