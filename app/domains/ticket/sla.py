from datetime import UTC, datetime, timedelta

from app.domains.ticket.models import Ticket, TicketCriticality, TicketStatus

SLA_BY_CRITICALITY: dict[TicketCriticality, timedelta] = {
    TicketCriticality.HIGH: timedelta(days=1),
    TicketCriticality.MEDIUM: timedelta(days=3),
    TicketCriticality.LOW: timedelta(days=5),
}

TERMINAL_STATUSES: frozenset[TicketStatus] = frozenset(
    {TicketStatus.FINISHED, TicketStatus.CANCELLED}
)


def compute_due_date(
    creation_date: datetime, criticality: TicketCriticality
) -> datetime:
    base = creation_date if creation_date.tzinfo is not None else creation_date.replace(tzinfo=UTC)
    return base + SLA_BY_CRITICALITY[criticality]


def is_overdue(ticket: Ticket, now: datetime) -> bool:
    if ticket.status in TERMINAL_STATUSES:
        return False
    return compute_due_date(ticket.creation_date, ticket.criticality) < now
