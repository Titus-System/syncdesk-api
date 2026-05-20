from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.domains.ticket.models import TicketCriticality, TicketStatus
from app.domains.ticket.sla import (
    SLA_BY_CRITICALITY,
    TERMINAL_STATUSES,
    compute_due_date,
    is_overdue,
)


def test_sla_table_matches_agreed_durations() -> None:
    assert SLA_BY_CRITICALITY == {
        TicketCriticality.HIGH: timedelta(days=1),
        TicketCriticality.MEDIUM: timedelta(days=3),
        TicketCriticality.LOW: timedelta(days=5),
    }


def test_terminal_statuses_cover_finished_and_cancelled() -> None:
    assert TERMINAL_STATUSES == frozenset(
        {TicketStatus.FINISHED, TicketStatus.CANCELLED}
    )


@pytest.mark.parametrize(
    "criticality,expected_delta",
    [
        (TicketCriticality.HIGH, timedelta(days=1)),
        (TicketCriticality.MEDIUM, timedelta(days=3)),
        (TicketCriticality.LOW, timedelta(days=5)),
    ],
)
def test_compute_due_date_adds_sla_window_for_tz_aware_input(
    criticality: TicketCriticality, expected_delta: timedelta
) -> None:
    created = datetime(2026, 5, 18, 12, 0, tzinfo=UTC)

    due = compute_due_date(created, criticality)

    assert due == created + expected_delta
    assert due.tzinfo is UTC


def test_compute_due_date_promotes_naive_input_to_utc() -> None:
    naive = datetime(2026, 5, 18, 12, 0)

    due = compute_due_date(naive, TicketCriticality.MEDIUM)

    assert due == datetime(2026, 5, 21, 12, 0, tzinfo=UTC)
    assert due.tzinfo is UTC


@pytest.mark.parametrize("terminal", [TicketStatus.FINISHED, TicketStatus.CANCELLED])
def test_is_overdue_returns_false_for_terminal_statuses_even_when_ancient(
    terminal: TicketStatus,
) -> None:
    ticket = SimpleNamespace(
        status=terminal,
        creation_date=datetime(2020, 1, 1, tzinfo=UTC),
        criticality=TicketCriticality.HIGH,
    )

    assert is_overdue(ticket, datetime(2026, 5, 18, tzinfo=UTC)) is False


def test_is_overdue_returns_true_when_open_ticket_past_sla() -> None:
    ticket = SimpleNamespace(
        status=TicketStatus.IN_PROGRESS,
        creation_date=datetime(2026, 5, 10, tzinfo=UTC),
        criticality=TicketCriticality.HIGH,
    )

    assert is_overdue(ticket, datetime(2026, 5, 18, tzinfo=UTC)) is True


def test_is_overdue_returns_false_when_open_ticket_within_sla() -> None:
    now = datetime(2026, 5, 18, 12, 0, tzinfo=UTC)
    ticket = SimpleNamespace(
        status=TicketStatus.AWAITING_ASSIGNMENT,
        creation_date=now - timedelta(hours=1),
        criticality=TicketCriticality.HIGH,
    )

    assert is_overdue(ticket, now) is False


def test_is_overdue_returns_false_at_exact_sla_boundary() -> None:
    creation = datetime(2026, 5, 18, 12, 0, tzinfo=UTC)
    now = creation + SLA_BY_CRITICALITY[TicketCriticality.HIGH]
    ticket = SimpleNamespace(
        status=TicketStatus.IN_PROGRESS,
        creation_date=creation,
        criticality=TicketCriticality.HIGH,
    )

    assert is_overdue(ticket, now) is False
