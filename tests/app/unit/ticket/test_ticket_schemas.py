from uuid import uuid4

from app.domains.ticket.models import TicketCriticality, TicketStatus, TicketType
from app.domains.ticket.schemas import (
    AssignTicketRequest,
    CreateTicketDTO,
    EscalateTicketRequest,
    TicketClosedEventPayload,
    TicketEscalatedEventPayload,
    TicketQueueFiltersDTO,
    TicketSearchFiltersDTO,
    TriageFinishedEventPayload,
    UpdateTicketDTO,
)


def test_create_ticket_dto_accepts_existing_contract() -> None:
    dto = CreateTicketDTO(
        triage_id="67f0c9b8e4b0b1a2c3d4e5f6",
        type=TicketType.ISSUE,
        criticality=TicketCriticality.HIGH,
        product="Sistema Financeiro",
        description="Erro ao emitir boleto",
        chat_ids=["67f0c9b8e4b0b1a2c3d4e5f7"],
        client_id=uuid4(),
    )

    assert dto.type == TicketType.ISSUE
    assert dto.criticality == TicketCriticality.HIGH


def test_ticket_search_filters_use_official_pagination_defaults() -> None:
    filters = TicketSearchFiltersDTO(status=TicketStatus.AWAITING_ASSIGNMENT, page=2, page_size=10)

    assert filters.page == 2
    assert filters.page_size == 10


def test_queue_filters_accept_provisional_department_fields() -> None:
    filters = TicketQueueFiltersDTO(
        department_id="dept-finance",
        level="N2",
        unassigned_only=True,
        page=1,
        page_size=20,
    )

    assert filters.department_id == "dept-finance"
    assert filters.level == "N2"
    assert filters.unassigned_only is True


def test_update_ticket_dto_accepts_awaiting_assignment_status() -> None:
    dto = UpdateTicketDTO(status=TicketStatus.AWAITING_ASSIGNMENT)

    assert dto.status == TicketStatus.AWAITING_ASSIGNMENT


def test_assign_request_is_importable_and_validatable() -> None:
    dto = AssignTicketRequest(agent_id=uuid4(), reason="Primeira atribuicao.")

    assert dto.reason == "Primeira atribuicao."


def test_escalate_request_marks_department_reference_as_string_contract() -> None:
    dto = EscalateTicketRequest(
        target_department_id="dept-finance",
        target_department_name="Financeiro",
        target_level="N3",
        reason="Subir para especialista",
    )

    assert dto.target_department_id == "dept-finance"
    assert dto.target_level == "N3"


def test_triage_finished_event_payload_is_valid() -> None:
    payload = TriageFinishedEventPayload(
        triage_id="67f0c9b8e4b0b1a2c3d4e5f6",
        type=TicketType.ISSUE,
        criticality=TicketCriticality.HIGH,
        product="Sistema Financeiro",
        description="Erro ao emitir boleto",
        chat_ids=["67f0c9b8e4b0b1a2c3d4e5f7"],
        client_id=uuid4(),
    )

    assert payload.type == TicketType.ISSUE
    assert payload.criticality == TicketCriticality.HIGH


def test_ticket_closed_event_payload_uses_new_status_contract() -> None:
    payload = TicketClosedEventPayload(
        ticket_id="67f0ca60e4b0b1a2c3d4e601",
        triage_id="67f0c9b8e4b0b1a2c3d4e5f6",
        client_id=uuid4(),
        status=TicketStatus.FINISHED,
        occurred_at="2026-04-14T12:30:00Z",
        previous_status=TicketStatus.IN_PROGRESS,
        closed_at="2026-04-14T12:30:00Z",
    )

    assert payload.event_name == "ticket.closed"
    assert payload.status == TicketStatus.FINISHED


def test_ticket_escalated_event_payload_is_valid() -> None:
    payload = TicketEscalatedEventPayload(
        ticket_id="67f0ca60e4b0b1a2c3d4e601",
        triage_id="67f0c9b8e4b0b1a2c3d4e5f6",
        client_id=uuid4(),
        status=TicketStatus.AWAITING_ASSIGNMENT,
        occurred_at="2026-04-14T12:40:00Z",
        previous_agent_id=uuid4(),
        source_department_id="dept-finance",
        source_level="N1",
        target_department_id="dept-specialists",
        target_level="N2",
        reason="Escalar para especialista",
    )

    assert payload.event_name == "ticket.escalated"
    assert payload.status == TicketStatus.AWAITING_ASSIGNMENT
