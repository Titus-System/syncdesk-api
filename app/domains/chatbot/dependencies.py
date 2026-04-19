from typing import Annotated

from fastapi import Depends

from app.db.mongo.dependencies import MongoSessionDep
from app.domains.chatbot.repositories.chatbot_repository import ChatbotRepository
from app.domains.chatbot.services.chatbot_service import ChatbotService
from app.domains.live_chat.dependencies import ConversationServiceDep
from app.domains.ticket.repositories import TicketRepository


def get_chatbot_repo(db: MongoSessionDep) -> ChatbotRepository:
    return ChatbotRepository(db)


def get_ticket_repo(db: MongoSessionDep) -> TicketRepository:
    return TicketRepository(db)


ChatbotRepositoryDep = Annotated[ChatbotRepository, Depends(get_chatbot_repo)]
TicketRepositoryDep = Annotated[TicketRepository, Depends(get_ticket_repo)]


def get_chatbot_service(
    chatbot_repo: ChatbotRepositoryDep,
    ticket_repo: TicketRepositoryDep,
    conversation_service: ConversationServiceDep,
) -> ChatbotService:
    return ChatbotService(chatbot_repo, ticket_repo, conversation_service)


ChatbotServiceDep = Annotated[ChatbotService, Depends(get_chatbot_service)]