from app.core.event_dispatcher import EventDispatcher
from app.core.event_dispatcher.decorators import event_handler
from app.core.event_dispatcher.enums import AppEvent
from app.core.event_dispatcher.schemas import TicketClosedEventSchema
from app.db.mongo.db import mongo_db
from app.domains.chatbot.repositories.chatbot_repository import ChatbotRepository
from app.domains.chatbot.services.chatbot_service import ChatbotService


class ChatbotListener:
    def __init__(self, chatbot_service: ChatbotService) -> None:
        self.service = chatbot_service

    @event_handler(TicketClosedEventSchema)
    async def on_ticket_closed(self, schema: TicketClosedEventSchema) -> None:
        await self.service.finish_attendance_pending_evaluation(str(schema.triage_id))


def register_chatbot_listener(dispatcher: EventDispatcher) -> None:
    repo = ChatbotRepository(mongo_db.get_db())
    service = ChatbotService(repo, dispatcher)
    listener = ChatbotListener(service)

    dispatcher.subscribe(AppEvent.TICKET_CLOSED, listener.on_ticket_closed)