from typing import Annotated

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, status
from starlette.responses import JSONResponse

from app.core.dependencies import ResponseFactoryDep
from app.core.exceptions import AppHTTPException
from app.domains.auth import CurrentUserSessionDep, require_permission
from app.domains.ticket.dependencies import TicketServiceDep
from app.domains.ticket.schemas import (
    AddTicketCommentDTO,
    AssignTicketRequest,
    CreateTicketDTO,
    CreateTicketResponseDTO,
    EscalateTicketRequest,
    TicketPaginatedList,
    TicketQueueFiltersDTO,
    TicketQueueListResponse,
    TicketResponse,
    TicketSearchFiltersDTO,
    TransferTicketRequest,
    UpdateTicketDTO,
)
from app.domains.ticket.swagger_utils import (
    comment_on_ticket_swagger,
    get_ticket_comments_swagger,
)
from app.schemas.response import GenericSuccessContent

ticket_router = APIRouter()


def _contract_not_implemented(feature_name: str) -> None:
    raise AppHTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail=(
            f"{feature_name} contract is available in this sprint, "
            "but its business implementation is still pending."
        ),
        title="Contract Stub",
    )


@ticket_router.get(
    "/",
    tags=["Tickets"],
    response_model=GenericSuccessContent[TicketPaginatedList[TicketResponse]],
    dependencies=[require_permission("ticket:read")],
    summary="List tickets",
    description=(
        "Official paginated ticket listing endpoint. "
        "Returns items, page, page_size, and total."
    ),
)
async def get_tickets(
    filters: Annotated[TicketSearchFiltersDTO, Depends()],
    _auth: CurrentUserSessionDep,
    service: TicketServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    """
    HTTP GET /api/tickets/

    Purpose:
    - List tickets with the official paginated response contract.

    Query params:
    - ticket_id, client_id, triage_id, status, criticality, type, product, page, page_size

    Response:
    - GenericSuccessContent[TicketPaginatedList[TicketResponse]]

    Permissions:
    - ticket:read
    """
    result = await service.list_tickets(filters)
    return response.success(
        data=result.model_dump(mode="json"),
        status_code=status.HTTP_200_OK,
    )


@ticket_router.get(
    "/queue",
    tags=["Tickets", "Queue"],
    response_model=GenericSuccessContent[TicketQueueListResponse],
    dependencies=[require_permission("ticket:queue")],
    summary="List ticket queue",
    description=(
        "Queue contract for open/active tickets ordered by criticality and creation date. "
        "The contract is available now; the full queue business implementation remains pending."
    ),
)
async def get_ticket_queue(
    filters: Annotated[TicketQueueFiltersDTO, Depends()],
    _auth: CurrentUserSessionDep,
) -> JSONResponse:
    """
    HTTP GET /api/tickets/queue

    Purpose:
    - Expose the queue contract for tickets awaiting assignment or active handling.

    Query params:
    - status, type, department_id, unassigned_only, level, assignee_id, page, page_size

    Response:
    - GenericSuccessContent[TicketQueueListResponse]

    Permissions:
    - ticket:queue

    Business notes:
    - Sorting is contractually defined as criticality first, then creation date.
    - department_id and level are provisional cross-domain contract fields.
    - This route will emit no event by itself.
    """
    _ = filters
    _contract_not_implemented("Ticket queue")


@ticket_router.post(
    "/",
    tags=["Tickets"],
    response_model=GenericSuccessContent[CreateTicketResponseDTO],
    dependencies=[require_permission("ticket:create")],
    summary="Create ticket",
    description="Official ticket creation endpoint.",
)
async def create_ticket(
    dto: CreateTicketDTO,
    _auth: CurrentUserSessionDep,
    service: TicketServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    """
    HTTP POST /api/tickets/

    Purpose:
    - Create a new ticket.

    Body:
    - CreateTicketDTO

    Response:
    - GenericSuccessContent[CreateTicketResponseDTO]

    Permissions:
    - ticket:create

    Events:
    - Ticket creation may later be triggered from 'triage.finished' in addition to HTTP.
    """
    result = await service.create_ticket(dto)
    return response.success(
        data=result.model_dump(mode="json"),
        status_code=status.HTTP_201_CREATED,
    )


@ticket_router.get(
    "/{ticket_id}",
    tags=["Tickets"],
    response_model=GenericSuccessContent[TicketResponse],
    dependencies=[require_permission("ticket:read")],
    summary="Get ticket by id",
    description="Returns a single ticket using the canonical response contract.",
)
async def get_ticket(
    ticket_id: PydanticObjectId,
    _auth: CurrentUserSessionDep,
    service: TicketServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    """
    HTTP GET /api/tickets/{ticket_id}

    Purpose:
    - Read a single ticket by identifier.

    Response:
    - GenericSuccessContent[TicketResponse]

    Permissions:
    - ticket:read
    """
    result = await service.get_ticket(ticket_id)
    return response.success(
        data=result.model_dump(mode="json"),
        status_code=status.HTTP_200_OK,
    )


@ticket_router.patch(
    "/{ticket_id}",
    tags=["Tickets"],
    response_model=GenericSuccessContent[TicketResponse],
    dependencies=[require_permission("ticket:update")],
    summary="Partially update a ticket",
    description=(
        "Official partial update endpoint for editable ticket fields. "
        "Use this endpoint for product, description, criticality, and status changes. "
        "If the resulting status becomes 'finished', the ticket domain emits "
        "the 'ticket.closed' business event contract."
    ),
)
async def update_ticket(
    ticket_id: PydanticObjectId,
    dto: UpdateTicketDTO,
    _auth: CurrentUserSessionDep,
    service: TicketServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    """
    HTTP PATCH /api/tickets/{ticket_id}

    Purpose:
    - Update official editable fields of a ticket.

    Allowed body fields:
    - status
    - criticality
    - product
    - description

    Excluded actions:
    - assign, transfer, and escalate remain dedicated routes.

    Permissions:
    - ticket:update

    Events:
    - ticket.closed when the resulting status becomes finished
    """
    result = await service.update_ticket(ticket_id, dto)
    return response.success(data=result.model_dump(mode="json"), status_code=status.HTTP_200_OK)


@ticket_router.post(
    "/{ticket_id}/assign",
    tags=["Tickets", "Queue"],
    response_model=GenericSuccessContent[TicketResponse],
    dependencies=[require_permission("ticket:assign")],
    summary="Assign a ticket to an agent",
    description=(
        "Assignment contract for queue handling. "
        "This route is expected to emit 'ticket.assignee_updated' after "
        "the business implementation is added."
    ),
)
async def assign_ticket(
    ticket_id: PydanticObjectId,
    dto: AssignTicketRequest,
    _auth: CurrentUserSessionDep,
) -> JSONResponse:
    """
    HTTP POST /api/tickets/{ticket_id}/assign

    Purpose:
    - Assign an agent to a ticket and register assignment history.

    Body:
    - AssignTicketRequest

    Response:
    - GenericSuccessContent[TicketResponse]

    Permissions:
    - ticket:assign

    Events:
    - ticket.assignee_updated
    """
    _ = (ticket_id, dto)
    _contract_not_implemented("Ticket assignment")


@ticket_router.post(
    "/{ticket_id}/escalate",
    tags=["Tickets", "Queue"],
    response_model=GenericSuccessContent[TicketResponse],
    dependencies=[require_permission("ticket:escalate")],
    summary="Escalate a ticket",
    description=(
        "Escalation contract for moving a ticket to a higher support level or target department. "
        "This route is expected to emit 'ticket.escalated' after the "
        "business implementation is added."
    ),
)
async def escalate_ticket(
    ticket_id: PydanticObjectId,
    dto: EscalateTicketRequest,
    _auth: CurrentUserSessionDep,
) -> JSONResponse:
    """
    HTTP POST /api/tickets/{ticket_id}/escalate

    Purpose:
    - Move a ticket upward in the support hierarchy.

    Body:
    - EscalateTicketRequest

    Response:
    - GenericSuccessContent[TicketResponse]

    Permissions:
    - ticket:escalate

    Business notes:
    - target_department_id and target_level are provisional contract fields.
    - Only upward level transitions are valid once the rule implementation lands.

    Events:
    - ticket.escalated
    """
    _ = (ticket_id, dto)
    _contract_not_implemented("Ticket escalation")


@ticket_router.post(
    "/{ticket_id}/transfer",
    tags=["Tickets", "Queue"],
    response_model=GenericSuccessContent[TicketResponse],
    dependencies=[require_permission("ticket:transfer")],
    summary="Transfer a ticket",
    description=(
        "Transfer contract for moving a ticket between agents on the same level/department. "
        "This route is expected to emit 'ticket.assignee_updated' after "
        "the business implementation is added."
    ),
)
async def transfer_ticket(
    ticket_id: PydanticObjectId,
    dto: TransferTicketRequest,
    _auth: CurrentUserSessionDep,
) -> JSONResponse:
    """
    HTTP POST /api/tickets/{ticket_id}/transfer

    Purpose:
    - Transfer a ticket to another agent without changing its support level.

    Body:
    - TransferTicketRequest

    Response:
    - GenericSuccessContent[TicketResponse]

    Permissions:
    - ticket:transfer

    Events:
    - ticket.assignee_updated
    """
    _ = (ticket_id, dto)
    _contract_not_implemented("Ticket transfer")


@ticket_router.post(
    "/{ticket_id}/comments",
    dependencies=[require_permission("ticket:comment")],
    tags=["Tickets"],
    **comment_on_ticket_swagger,
)
async def comment_on_ticket(
    ticket_id: PydanticObjectId,
    dto: AddTicketCommentDTO,
    auth: CurrentUserSessionDep,
    service: TicketServiceDep,
    response: ResponseFactoryDep
) -> JSONResponse:
    user = auth[0]
    comment = await service.add_comment_to_ticket(
        ticket_id,
        user.name or user.username or user.email,
        dto
    )

    if comment is None:
        raise AppHTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ticket {ticket_id} does not exist.",
        )

    return response.success(
        data=comment.model_dump(mode="json"),
        status_code=status.HTTP_201_CREATED,
    )


@ticket_router.get(
    "/{ticket_id}/comments",
    dependencies=[require_permission("ticket:read")],
    tags=["Tickets"],
    **get_ticket_comments_swagger,
)
async def get_ticket_comments(
    ticket_id: PydanticObjectId,
    _auth: CurrentUserSessionDep,
    service: TicketServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    comments = await service.list_ticket_comments(ticket_id)
    if comments is None:
        raise AppHTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Ticket {ticket_id} does not exist.",
        )

    return response.success(
        data=[comment.model_dump(mode="json") for comment in comments],
        status_code=status.HTTP_200_OK,
    )
