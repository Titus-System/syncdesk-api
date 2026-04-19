from typing import Annotated

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, status
from starlette.responses import JSONResponse

from app.core.dependencies import ResponseFactoryDep
from app.domains.auth import CurrentUserSessionDep, require_permission
from app.domains.ticket.dependencies import TicketServiceDep
from app.domains.ticket.schemas import (
    CreateTicketDTO,
    CreateTicketResponseDTO,
    TicketResponseDTO,
    TicketSearchFiltersDTO,
    UpdateTicketStatusDTO,
    UpdateTicketStatusResponseDTO,
)
from app.schemas.response import GenericSuccessContent

ticket_router = APIRouter()


@ticket_router.get(
    "/",
    tags=["Tickets"],
    response_model=GenericSuccessContent[list[TicketResponseDTO]],
    dependencies=[require_permission("ticket:read")],
)
async def get_tickets(
    filters: Annotated[TicketSearchFiltersDTO, Depends()],
    _auth: CurrentUserSessionDep,
    service: TicketServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    result = await service.search_tickets(filters)
    return response.success(
        data=[ticket.model_dump(mode="json") for ticket in result],
        status_code=status.HTTP_200_OK,
    )


@ticket_router.get(
    "/{ticket_id}",
    tags=["Tickets"],
    response_model=GenericSuccessContent[TicketResponseDTO],
    dependencies=[require_permission("ticket:read")],
)
async def get_ticket_by_id(
    ticket_id: PydanticObjectId,
    _auth: CurrentUserSessionDep,
    service: TicketServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    result = await service.get_ticket_by_id(ticket_id)
    return response.success(
        data=result.model_dump(mode="json"),
        status_code=status.HTTP_200_OK,
    )


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
    return response.success(
        data=result.model_dump(mode="json"),
        status_code=status.HTTP_201_CREATED,
    )


@ticket_router.post(
    "/{ticket_id}/take",
    tags=["Tickets"],
    response_model=GenericSuccessContent[TicketResponseDTO],
    dependencies=[require_permission("ticket:update_status")],
)
async def take_ticket(
    ticket_id: PydanticObjectId,
    auth: CurrentUserSessionDep,
    service: TicketServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    user = auth[0]
    result = await service.take_ticket(ticket_id, user)
    return response.success(
        data=result.model_dump(mode="json"),
        status_code=status.HTTP_200_OK,
    )


@ticket_router.patch(
    "/{ticket_id}/status",
    tags=["Tickets"],
    response_model=GenericSuccessContent[UpdateTicketStatusResponseDTO],
    dependencies=[require_permission("ticket:update_status")],
)
async def update_ticket_status(
    ticket_id: PydanticObjectId,
    dto: UpdateTicketStatusDTO,
    auth: CurrentUserSessionDep,
    service: TicketServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    user = auth[0]
    result = await service.update_status(ticket_id, dto, user)
    return response.success(
        data=result.model_dump(mode="json"),
        status_code=status.HTTP_200_OK,
    )