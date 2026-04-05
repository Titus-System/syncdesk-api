from fastapi import APIRouter, Depends, Body, status
from fastapi.responses import JSONResponse

from app.core.dependencies import ResponseFactoryDep
from app.db.mongo.dependencies import MongoSessionDep
from app.domains.auth.dependencies import CurrentUserSessionDep
from app.domains.chatbot.schemas import AttendanceClient, TriageInputDTO, TriageResponseDTO
from app.domains.chatbot.repositories.chatbot_repository import ChatbotRepository
from app.domains.chatbot.services.chatbot_service import ChatbotService

router = APIRouter(prefix="/chatbot", tags=["Chatbot URA"])

def get_chatbot_service(db: MongoSessionDep) -> ChatbotService:
    repository = ChatbotRepository(db)
    return ChatbotService(repository)

@router.post("/")
async def create_triage(
    auth: CurrentUserSessionDep,
    response: ResponseFactoryDep,
    service: ChatbotService = Depends(get_chatbot_service),
) -> JSONResponse:
    user = auth[0]
    c = AttendanceClient(
        id=user.id,
        name = user.name or user.email,
        email = user.email,
    )
    res = await service.create_attendance(c)
    return response.success(
        data = res,
        status_code = status.HTTP_201_CREATED
    )


@router.post("/webhook", response_model=TriageResponseDTO)
async def send_message(
    payload: TriageInputDTO = Body(...),
    service: ChatbotService = Depends(get_chatbot_service)
) -> TriageResponseDTO:
    """
    Endpoint para interagir com o Chatbot da URA de Triagem.
    """
    return await service.process_message(payload)