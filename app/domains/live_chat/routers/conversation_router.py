from uuid import UUID

from beanie import PydanticObjectId
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.core.dependencies import ResponseFactoryDep
from app.core.exceptions import AppHTTPException
from app.db.exceptions import ResourceAlreadyExistsError, ResourceNotFoundError
from app.domains.auth import CurrentUserSessionDep, UserServiceDep, require_permission

from ..dependencies import ConversationServiceDep
from ..schemas import CreateConversationDTO

conversation_router = APIRouter()


@conversation_router.get(
    "/service_session/{service_session_id}",
    tags=["Conversations"],
    dependencies=[require_permission("chat:read")]
)
async def get_conversations(
    service_session_id: PydanticObjectId,
    _auth: CurrentUserSessionDep,
    service: ConversationServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    chats = await service.get_chats_from_service_session(service_session_id)
    data = [chat.model_dump(mode="json") for chat in chats]
    return response.success(data=data, status_code=status.HTTP_200_OK)


@conversation_router.post(
    "/",
    tags=["Conversations"],
    dependencies=[require_permission("chat:create")]
)
async def create_conversation(
    dto: CreateConversationDTO,
    auth: CurrentUserSessionDep,
    service: ConversationServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    try:
        user = auth[0]
        if dto.client_id != user.id:
            raise AppHTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User cannot open a chat in the name of another user.",
            )
        chat = await service.create(dto)
        return response.success(
            data=chat.model_dump(mode="json"),
            status_code=status.HTTP_201_CREATED
        )

    except ResourceAlreadyExistsError as e:
        raise AppHTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Chat already exists.",
        ) from e


@conversation_router.patch(
    "/{chat_id}/set-agent/{agent_id}",
    tags=["Conversations"],
    dependencies=[require_permission("chat:update")],
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
        roles = await user_service.get_user_roles(agent_id)
        if "agent" not in [r.name for r in roles]:
            raise AppHTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="agent_id provided does not correspond to a valid user.",
            )

        await service.attribute_agent(chat_id, agent_id)
        return response.success(data=None, status_code=status.HTTP_200_OK)

    except ResourceNotFoundError as err:
        raise AppHTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{err.resource_name} {err.identifier} does not exist.",
        ) from err
