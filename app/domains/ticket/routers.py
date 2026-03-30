from fastapi import APIRouter
from starlette.responses import JSONResponse

from app.core.dependencies import ResponseFactoryDep
from app.domains.auth import CurrentUserSessionDep, require_permission
from app.domains.ticket.dependencies import TicketServiceDep
from app.domains.ticket.schemas import CreateTicketDTO

ticket_router = APIRouter()


@ticket_router.post(
    "/",
    tags=["ticket"],
    dependencies=[require_permission("ticket:create")]
)
async def create_ticket(
    dto: CreateTicketDTO,
    auth: CurrentUserSessionDep,
    service: TicketServiceDep,
    response: ResponseFactoryDep
) -> JSONResponse:
    ...
