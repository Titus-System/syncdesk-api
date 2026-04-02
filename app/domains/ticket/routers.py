from beanie import PydanticObjectId
from fastapi import APIRouter, status
from starlette.responses import JSONResponse

from app.core.dependencies import ResponseFactoryDep
from app.domains.auth import CurrentUserSessionDep, require_permission
from app.domains.ticket.dependencies import TicketServiceDep
from app.domains.ticket.schemas import (
    CreateTicketDTO,
    CreateTicketResponseDTO,
    UpdateTicketStatusDTO,
    UpdateTicketStatusResponseDTO,
)
from app.schemas.response import GenericSuccessContent

ticket_router = APIRouter()


@ticket_router.post(
    "/",
    tags=["Tickets"],
    response_model=GenericSuccessContent[CreateTicketResponseDTO],
    dependencies=[require_permission("ticket:create")],
)
async def create_ticket(
    dto: CreateTicketDTO,
    _auth: CurrentUserSessionDep,
    service: TicketServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    result = await service.create_ticket(dto)
    return response.success(data=result.model_dump(mode="json"), status_code=status.HTTP_201_CREATED)


@ticket_router.patch(
    "/{ticket_id}/status",
    tags=["Tickets"],
    response_model=GenericSuccessContent[UpdateTicketStatusResponseDTO],
    dependencies=[require_permission("ticket:update_status")],
)
async def update_ticket_status(
    ticket_id: PydanticObjectId,
    dto: UpdateTicketStatusDTO,
    _auth: CurrentUserSessionDep,
    service: TicketServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    result = await service.update_status(ticket_id, dto)
    return response.success(data=result.model_dump(mode="json"), status_code=status.HTTP_200_OK)
