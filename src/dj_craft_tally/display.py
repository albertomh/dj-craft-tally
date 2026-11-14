"""Display helpers for rendering quantities.

Kept separate from :mod:`dj_craft_tally.admin` so non-admin entry points
(such as the custom admin site) can use them without importing the admin
module, which would otherwise create a circular import.
"""

from decimal import ROUND_HALF_UP, Decimal, localcontext
from typing import TYPE_CHECKING

from django.utils import formats
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

if TYPE_CHECKING:
    from dj_craft_tally.models import Unit


def format_quantity(
    value: Decimal | None, unit: "Unit", *, include_unit_code: bool = False
):
    """Render a quantity using the display precision of its unit."""
    if value is None:
        return None

    places = unit.display_decimal_places
    with localcontext() as context:
        context.prec = max(context.prec, len(value.as_tuple().digits) + places + 1)
        rounded = value.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)
    if not rounded:
        rounded = rounded.copy_abs()
    shown = formats.number_format(rounded, decimal_pos=places, use_l10n=True)
    if include_unit_code and unit.code != "item":
        shown = f"{shown} {unit.code}"
    return format_html(
        '<span title="{}">{}</span>',
        _("Exact: %(value)s") % {"value": value},
        shown,
    )
