from typing import Annotated

from fastapi import APIRouter, Body, Depends, status
from fastapi.responses import JSONResponse

from app.core.dependencies import ResponseFactoryDep
from app.domains.auth.dependencies import CurrentUserSessionDep
from app.domains.chatbot.dependencies import ChatbotServiceDep
from app.domains.chatbot.schemas import (
    AttendanceClient,
    AttendanceSearchFiltersDTO,
    EvaluationRequest,
    TriageInputDTO,
)
from app.domains.chatbot.swagger_utils import (
    create_attendance_swagger,
    evaluation_swagger,
    get_attendance_swagger,
    list_attendances_swagger,
    webhook_swagger,
)

router = APIRouter()


@router.post(
    "/",
    # dependencies=[require_permission("chatbot:create")],
    **create_attendance_swagger,
)
async def create_triage(
    auth: CurrentUserSessionDep,
    service: ChatbotServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    user = auth[0]
    c = AttendanceClient(
        id=user.id,
        name=user.name or user.email,
        email=user.email,
    )
    res = await service.create_attendance(c)
    return response.success(
        data=res,
        status_code=status.HTTP_201_CREATED,
    )


@router.get(
    "/",
    # dependencies=[require_permission("chatbot:list")],
    **list_attendances_swagger,
)
async def get_attendances(
    filters: Annotated[AttendanceSearchFiltersDTO, Depends()],
    auth: CurrentUserSessionDep,
    service: ChatbotServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    ...


@router.post(
    "/webhook",
    # dependencies=[require_permission("chatbot:interact")],
    **webhook_swagger,
)
async def send_message(
    service: ChatbotServiceDep,
    response: ResponseFactoryDep,
    payload: TriageInputDTO = Body(...),
) -> JSONResponse:
    data = await service.process_message(payload)
    return response.success(
        data = data,
        status_code=status.HTTP_200_OK
    )


@router.get(
    "/{triage_id}",
    # dependencies=[require_permission("chatbot:read")],
    **get_attendance_swagger,
)
async def get_attendance(
    triage_id: str,
    auth: CurrentUserSessionDep,
    service: ChatbotServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    ...


@router.post(
    "/{triage_id}/evaluation",
    # dependencies=[require_permission("chatbot:evaluate")],
    **evaluation_swagger,
)
async def set_evaluation(
    auth: CurrentUserSessionDep,
    payload: EvaluationRequest,
    service: ChatbotServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    ...

