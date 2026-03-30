from uuid import UUID

from beanie import PydanticObjectId
from fastapi import APIRouter, Query, status
from fastapi.responses import JSONResponse

from app.core.dependencies import ResponseFactoryDep
from app.core.exceptions import AppHTTPException
from app.db.exceptions import ResourceAlreadyExistsError, ResourceNotFoundError
from app.domains.auth import CurrentUserSessionDep, UserServiceDep, require_permission

from ..dependencies import ConversationServiceDep
from ..schemas import CreateConversationDTO
from .swagger_utils import (
    get_convs_swagger,
    get_messages_swagger,
    post_conv_swagger,
    set_agent_swagger,
)

conversation_router = APIRouter()


@conversation_router.get(
    "/ticket/{ticket_id}",
    tags=["Conversations"],
    dependencies=[require_permission("chat:read")],
    **get_convs_swagger,
)
async def get_conversations(
    ticket_id: PydanticObjectId,
    _auth: CurrentUserSessionDep,
    service: ConversationServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    chats = await service.get_chats_from_ticket(ticket_id)
    if not chats:
        return response.success(data=[], status_code=status.HTTP_200_OK)

    user = _auth[0]
    roles_names = user.roles_names()
    if "admin" not in roles_names and user.id not in chats[-1].participants():
        raise AppHTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not a current participant in this ticket.",
        )

    data = [chat.model_dump(mode="json") for chat in chats]
    return response.success(data=data, status_code=status.HTTP_200_OK)


@conversation_router.get(
    "/ticket/{ticket_id}/messages",
    tags=["Conversations", "Messages"],
    dependencies=[require_permission("chat:read")],
    **get_messages_swagger,
)
async def get_paginated_messages(
    ticket_id: PydanticObjectId,
    _auth: CurrentUserSessionDep,
    service: ConversationServiceDep,
    response: ResponseFactoryDep,
    page: int = Query(default=1, ge=1, description="Page number (1-indexed)."),
    limit: int = Query(default=10, ge=1, le=100, description="Number of messages per page."),
) -> JSONResponse:
    participants = await service.get_current_ticket_participants(ticket_id)
    if participants is None:
        return response.success(data=[], status_code=status.HTTP_200_OK)

    user = _auth[0]
    roles_names = user.roles_names()
    if "admin" not in roles_names and user.id not in participants:
        raise AppHTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User is not a current participant in this ticket.",
        )

    res = await service.get_paginated_messages(ticket_id, page, limit)
    return response.success(data=res.model_dump(mode="json"), status_code=status.HTTP_200_OK)


@conversation_router.post(
    "/",
    tags=["Conversations"],
    dependencies=[require_permission("chat:create")],
    **post_conv_swagger,
)
async def create_conversation(
    dto: CreateConversationDTO,
    auth: CurrentUserSessionDep,
    service: ConversationServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    try:
        user = auth[0]
        roles_names = user.roles_names()
        if "agent" not in roles_names and "admin" not in roles_names and dto.client_id != user.id:
            raise AppHTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User can't create a conversation in the name of another user.",
            )

        chat = await service.create(dto)
        return response.success(
            data=chat.model_dump(mode="json"), status_code=status.HTTP_201_CREATED
        )

    except ResourceAlreadyExistsError as e:
        raise AppHTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Chat already exists.",
        ) from e


@conversation_router.patch(
    "/{chat_id}/set-agent/{agent_id}",
    tags=["Conversations"],
    dependencies=[require_permission("chat:set_agent")],
    **set_agent_swagger,
)
async def set_conversation_agent(
    chat_id: PydanticObjectId,
    agent_id: UUID,
    _auth: CurrentUserSessionDep,
    service: ConversationServiceDep,
    user_service: UserServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    try:
        user = _auth[0]

        chat = await service.get_by_id(chat_id)
        if chat is None:
            raise AppHTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Conversation {chat_id} does not exist.",
            )

        if chat.agent_id is not None and (
            "admin" not in user.roles_names() and user.id != chat.agent_id
        ):
            raise AppHTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins or currently assigned agent can reassign this conversation.",
            )

        roles = await user_service.get_user_roles(agent_id)
        if "agent" not in [r.name for r in roles]:
            raise AppHTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="agent_id provided does not correspond to a valid agent.",
            )

        await service.attribute_agent(chat_id, agent_id)
        return response.success(data=None, status_code=status.HTTP_200_OK)

    except ResourceNotFoundError as err:
        raise AppHTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{err.resource_name} {err.identifier} does not exist.",
        ) from err
