"""Django admin registrations, split by model area."""

from dj_craft_tally.display import format_money, format_quantity
from dj_craft_tally.models import ProjectStatusChange

from . import activities, core, currency, equipment, inventory, materials  # noqa: F401
from .activities import (
    ActivityAdmin,
    ProjectStatusChangeAdmin,
    ProjectStatusChangeInline,
)
from .currency import CurrencyTransactionAdmin
from .materials import (
    BlueprintAdmin,
    BlueprintMaterialRequirementForm,
    MaterialAdmin,
)

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
