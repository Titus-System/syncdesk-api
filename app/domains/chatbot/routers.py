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
    **create_attendance_swagger,
)
async def create_triage(
    auth: CurrentUserSessionDep,
    service: ChatbotServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    user = auth[0]

    client = AttendanceClient(
        id=user.id,
        name=user.name or user.email,
        email=user.email,
    )

    data = await service.create_attendance(client)

    return response.success(
        data=data.model_dump(mode="json"),
        status_code=status.HTTP_201_CREATED,
    )


@router.get(
    "/",
    **list_attendances_swagger,
)
async def get_attendances(
    filters: Annotated[AttendanceSearchFiltersDTO, Depends()],
    auth: CurrentUserSessionDep,
    service: ChatbotServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    data = await service.list_attendances(filters)

    return response.success(
        data=[item.model_dump(mode="json") for item in data],
        status_code=status.HTTP_200_OK,
    )


@router.post(
    "/webhook",
    **webhook_swagger,
)
async def send_message(
    service: ChatbotServiceDep,
    response: ResponseFactoryDep,
    payload: TriageInputDTO = Body(...),
) -> JSONResponse:
    data = await service.process_message(payload)

    return response.success(
        data=data.model_dump(mode="json"),
        status_code=status.HTTP_200_OK,
    )


@router.get(
    "/{triage_id}",
    **get_attendance_swagger,
)
async def get_attendance(
    triage_id: str,
    auth: CurrentUserSessionDep,
    service: ChatbotServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    data = await service.get_attendance(triage_id)

    return response.success(
        data=data.model_dump(mode="json"),
        status_code=status.HTTP_200_OK,
    )


@router.post(
    "/{triage_id}/evaluation",
    **evaluation_swagger,
)
async def set_evaluation(
    triage_id: str,
    auth: CurrentUserSessionDep,
    payload: EvaluationRequest,
    service: ChatbotServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    data = await service.set_evaluation(triage_id, payload)

    return response.success(
        data=data.model_dump(mode="json"),
        status_code=status.HTTP_200_OK,
    )