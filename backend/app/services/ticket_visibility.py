"""Tier visibility and portfolio-counting rules.

Balanced is an observation-only cohort while ``settings.balanced_tier_admin_only``
is on. It is still generated, published and settled, but:

* only administrators may read it from the daily, history, ticket-detail and
  match-history APIs;
* it is excluded from public-facing surfaces (the landing-page record); and
* it is excluded from every portfolio ROI/P&L/calibration aggregate.

The flag is the single switch for the policy. Turning it off restores Balanced
as a normal public tier without touching generation.
"""

from __future__ import annotations

from app.config import settings
from app.models import TicketType

def _active_public_ticket_types() -> tuple[TicketType, ...]:
    # Imported lazily: the builder imports performance, which imports this
    # module. The builder's PUBLIC_TICKET_TYPES stays the single source of truth
    # for the active daily tiers.
    from app.services.accumulator_builder import PUBLIC_TICKET_TYPES

    return tuple(PUBLIC_TICKET_TYPES)


def admin_only_ticket_types() -> frozenset[TicketType]:
    """Return the tiers reserved for administrator monitoring right now."""
    if settings.balanced_tier_admin_only:
        return frozenset({TicketType.BALANCED})
    return frozenset()


def is_admin_only(ticket_type: TicketType | None) -> bool:
    return ticket_type in admin_only_ticket_types()


def is_admin_only_value(ticket_type: str | None) -> bool:
    """String variant for ledgers that store the tier as a plain string."""
    if not ticket_type:
        return False
    return any(item.value == ticket_type for item in admin_only_ticket_types())


def public_ticket_types() -> list[TicketType]:
    """Active public tiers that may be shown to every signed-in user."""
    hidden = admin_only_ticket_types()
    return [ticket_type for ticket_type in _active_public_ticket_types() if ticket_type not in hidden]


def admin_visible_ticket_types(include_internal: bool) -> list[TicketType]:
    """Tiers an administrator may read; ``include_internal`` adds research tiers."""
    if include_internal:
        return [ticket_type for ticket_type in TicketType if ticket_type != TicketType.HIGH_ODDS]
    return list(_active_public_ticket_types())


def reader_ticket_types(include_internal: bool, *, admin: bool) -> list[TicketType]:
    """Tiers one reader may see, applying the admin-only filter last."""
    ticket_types = admin_visible_ticket_types(include_internal) if admin else public_ticket_types()
    if admin:
        return ticket_types
    hidden = admin_only_ticket_types()
    return [ticket_type for ticket_type in ticket_types if ticket_type not in hidden]
