from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from beanie import PydanticObjectId
from bson import ObjectId
from fastapi import status

from app.core.exceptions import AppHTTPException
from app.domains.chatbot.enums import AttendanceStatus, TriageState
from app.domains.chatbot.fsm import ChatbotFSM, MENU_MAP
from app.domains.chatbot.models import AttendanceClient, AttendanceEvaluation, AttendanceResult
from app.domains.chatbot.repositories.chatbot_repository import ChatbotRepository
from app.domains.chatbot.schemas import (
    AttendanceResponse,
    AttendanceSearchFiltersDTO,
    CreateAttendanceDTO,
    EvaluationRequest,
    EvaluationResponse,
    InternalBotResponseDTO,
    QuickReply,
    TriageData,
    TriageInputDef,
    TriageInputDTO,
    TriageResult,
    TriageStepSchema,
)
from app.domains.live_chat.schemas import CreateConversationDTO
from app.domains.live_chat.services.conversation_service import ConversationService
from app.domains.ticket.models import (
    Ticket,
    TicketClient,
    TicketCompany,
    TicketCriticality,
    TicketStatus,
    TicketType,
)
from app.domains.ticket.repositories import TicketRepository


class ChatbotService:
    def __init__(
        self,
        repository: ChatbotRepository,
        ticket_repo: TicketRepository,
        conversation_service: ConversationService,
    ) -> None:
        self.repo = repository
        self.ticket_repo = ticket_repo
        self.conversation_service = conversation_service

    async def create_attendance(self, client: AttendanceClient) -> TriageData:
        triage_id = str(ObjectId())
        first_step = ChatbotFSM.process_interaction(None, "")

        dto = CreateAttendanceDTO(client=client)
        attendance = dto.model_dump(mode="json")
        attendance["current_step_id"] = TriageState.MAIN_MENU.value
        attendance["current_message"] = first_step.response_text
        attendance["current_input_mode"] = "quick_replies"
        attendance["current_quick_replies"] = first_step.quick_replies or []

        await self.repo.create_attendance(CreateAttendanceDTO(client=client), triage_id)

        persisted = await self.repo.find_attendance(triage_id)
        if persisted is None:
          raise AppHTTPException(
              status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
              detail="Could not initialize attendance.",
          )

        persisted["current_step_id"] = attendance["current_step_id"]
        persisted["current_message"] = attendance["current_message"]
        persisted["current_input_mode"] = attendance["current_input_mode"]
        persisted["current_quick_replies"] = attendance["current_quick_replies"]
        await self.repo.save_attendance(triage_id, persisted)

        return TriageData(
            triage_id=triage_id,
            step_id=TriageState.MAIN_MENU.value,
            message=first_step.response_text,
            input=self._build_input_definition(first_step),
            finished=False,
        )

    async def process_message(self, payload: TriageInputDTO) -> TriageData:
        attendance = await self.repo.find_attendance(payload.triage_id)
        if attendance is None:
            raise AppHTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Attendance {payload.triage_id} not found.",
            )

        source_step_id = attendance.get("current_step_id") or payload.step_id

        try:
            current_state = TriageState(source_step_id)
        except ValueError as err:
            raise AppHTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid step_id '{source_step_id}'.",
            ) from err

        current_question = attendance.get("current_message") or MENU_MAP[current_state]["message"]
        answer_raw = payload.answer_value or payload.answer_text or ""
        answer_label = self._resolve_answer_label(current_state, payload.answer_value, payload.answer_text)

        attendance["triage"].append(
            {
                "step": current_state.value,
                "question": current_question,
                "answer_value": payload.answer_value,
                "answer_text": answer_label,
            }
        )

        bot_response = ChatbotFSM.process_interaction(current_state, answer_raw)

        if bot_response.new_state == TriageState.TICKET_CREATED:
            created = await self._create_ticket_and_conversation(payload.triage_id, attendance)

            attendance["status"] = AttendanceStatus.IN_PROGRESS.value
            attendance["result"] = {
                "type": "Ticket",
                "closure_message": bot_response.response_text,
            }
            attendance["current_step_id"] = None
            attendance["current_message"] = None
            attendance["current_input_mode"] = None
            attendance["current_quick_replies"] = []

            await self.repo.save_attendance(payload.triage_id, attendance)

            return TriageData(
                triage_id=payload.triage_id,
                step_id=TriageState.TICKET_CREATED.value,
                finished=True,
                closure_message=bot_response.response_text,
                result=TriageResult(
                    type="ticket",
                    id=created["ticket_id"],
                    ticket_id=created["ticket_id"],
                    chat_id=created["chat_id"],
                ),
            )

        if bot_response.new_state == TriageState.SERVICE_FINISHED:
            attendance["status"] = AttendanceStatus.FINISHED.value
            attendance["end_date"] = datetime.now(UTC).isoformat()
            attendance["result"] = {
                "type": "Resolved",
                "closure_message": bot_response.response_text,
            }
            attendance["current_step_id"] = None
            attendance["current_message"] = None
            attendance["current_input_mode"] = None
            attendance["current_quick_replies"] = []

            await self.repo.save_attendance(payload.triage_id, attendance)

            return TriageData(
                triage_id=payload.triage_id,
                step_id=TriageState.SERVICE_FINISHED.value,
                finished=True,
                closure_message=bot_response.response_text,
                result=TriageResult(
                    type="resolved",
                    id=payload.triage_id,
                ),
            )

        attendance["status"] = AttendanceStatus.IN_PROGRESS.value
        attendance["current_step_id"] = bot_response.new_state.value
        attendance["current_message"] = bot_response.response_text
        attendance["current_input_mode"] = "free_text" if bot_response.is_free_text else "quick_replies"
        attendance["current_quick_replies"] = bot_response.quick_replies or []

        await self.repo.save_attendance(payload.triage_id, attendance)

        return TriageData(
            triage_id=payload.triage_id,
            step_id=bot_response.new_state.value,
            message=bot_response.response_text,
            input=self._build_input_definition(bot_response),
            finished=False,
        )

    async def list_attendances(
        self, filters: AttendanceSearchFiltersDTO
    ) -> list[AttendanceResponse]:
        docs = await self.repo.list_attendances(filters)
        return [self._map_attendance_response(doc) for doc in docs]

    async def get_attendance(self, triage_id: str) -> AttendanceResponse:
        attendance = await self.repo.find_attendance(triage_id)
        if attendance is None:
            raise AppHTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Attendance {triage_id} not found.",
            )
        return self._map_attendance_response(attendance)

    async def set_evaluation(
        self, triage_id: str, payload: EvaluationRequest
    ) -> EvaluationResponse:
        attendance = await self.repo.find_attendance(triage_id)
        if attendance is None:
            raise AppHTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Attendance {triage_id} not found.",
            )

        if attendance.get("status") != AttendanceStatus.FINISHED.value:
            raise AppHTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Attendance is not finished yet.",
            )

        if attendance.get("evaluation") is not None:
            raise AppHTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Attendance has already been evaluated.",
            )

        evaluated_at = datetime.now(UTC)
        attendance["evaluation"] = AttendanceEvaluation(rating=payload.rating).model_dump(mode="json")
        attendance["end_date"] = attendance.get("end_date") or evaluated_at.isoformat()

        await self.repo.save_attendance(triage_id, attendance)

        return EvaluationResponse(
            triage_id=triage_id,
            rating=payload.rating,
            evaluated_at=evaluated_at,
        )

    async def _create_ticket_and_conversation(
        self, triage_id: str, attendance: dict[str, Any]
    ) -> dict[str, str]:
        client_raw = attendance["client"]

        client_id = UUID(client_raw["id"])
        client_name = client_raw["name"]
        client_email = client_raw["email"]
        company_raw = client_raw.get("company") or {}

        ticket_type = self._infer_ticket_type(attendance)
        product = self._infer_product(attendance)
        description = self._infer_description(attendance)
        criticality = self._infer_criticality(description)

        ticket = Ticket(
            triage_id=PydanticObjectId(triage_id) if ObjectId.is_valid(triage_id) else PydanticObjectId(),
            type=ticket_type,
            criticality=criticality,
            product=product,
            status=TicketStatus.OPEN,
            creation_date=datetime.now(UTC),
            description=description,
            chat_ids=[],
            agent_history=[],
            client=TicketClient(
                id=client_id,
                name=client_name,
                email=client_email,
                company=TicketCompany(
                    id=UUID(company_raw["id"]) if company_raw.get("id") else client_id,
                    name=company_raw.get("name") or f"{client_name} account",
                ),
            ),
            comments=[],
        )

        created_ticket = await self.repo.create_ticket(ticket)

        conversation = await self.conversation_service.create(
            CreateConversationDTO(
                ticket_id=created_ticket.id,
                client_id=client_id,
                agent_id=None,
                sequential_index=0,
                parent_id=None,
            )
        )

        created_ticket.chat_ids.append(conversation.id)
        await created_ticket.save()

        return {
            "ticket_id": str(created_ticket.id),
            "chat_id": str(conversation.id),
        }

    def _build_input_definition(
        self, internal: InternalBotResponseDTO
    ) -> TriageInputDef | None:
        if internal.is_finished:
            return None

        if internal.is_free_text:
            return TriageInputDef(mode="free_text")

        return TriageInputDef(
            mode="quick_replies",
            quick_replies=[
                QuickReply(label=item["label"], value=item["value"])
                for item in (internal.quick_replies or [])
            ],
        )

    def _resolve_answer_label(
        self,
        state: TriageState,
        answer_value: str | None,
        answer_text: str | None,
    ) -> str:
        if answer_text:
            return answer_text.strip()

        if not answer_value:
            return ""

        options = MENU_MAP[state].get("options", [])
        for option in options:
            if option["value"] == answer_value:
                return option["label"]

        return answer_value

    def _infer_ticket_type(self, attendance: dict[str, Any]) -> TicketType:
        steps = {item["step"] for item in attendance.get("triage", [])}

        if TriageState.REQUESTING_ACCESS.value in steps:
            return TicketType.ACCESS
        if TriageState.WAITING_FEATURE_TEXT.value in steps:
            return TicketType.NEW_FEATURE
        return TicketType.ISSUE

    def _infer_product(self, attendance: dict[str, Any]) -> str:
        for item in attendance.get("triage", []):
            if item["step"] == TriageState.MAIN_MENU.value and item.get("answer_text"):
                label = item["answer_text"]
                if label in {"Produto A", "Produto B", "Produto C"}:
                    return label
        return "Atendimento Geral"

    def _infer_description(self, attendance: dict[str, Any]) -> str:
        free_text_steps = {
            TriageState.REQUESTING_ACCESS.value,
            TriageState.WAITING_FAILURE_TEXT.value,
            TriageState.WAITING_FEATURE_TEXT.value,
        }

        for item in reversed(attendance.get("triage", [])):
            if item["step"] in free_text_steps and item.get("answer_text"):
                return item["answer_text"]

        return "Solicitação encaminhada automaticamente pela URA."

    def _infer_criticality(self, description: str) -> TicketCriticality:
        normalized = description.lower()
        high_keywords = ["urgente", "crítico", "critico", "parado", "indisponível", "indisponivel"]

        if any(keyword in normalized for keyword in high_keywords):
            return TicketCriticality.HIGH
        return TicketCriticality.MEDIUM

    def _map_attendance_response(self, attendance: dict[str, Any]) -> AttendanceResponse:
        client_raw = attendance["client"]
        result_raw = attendance.get("result")
        evaluation_raw = attendance.get("evaluation")

        current_input = None
        if attendance.get("current_input_mode") == "free_text":
            current_input = TriageInputDef(mode="free_text")
        elif attendance.get("current_input_mode") == "quick_replies":
            current_input = TriageInputDef(
                mode="quick_replies",
                quick_replies=[
                    QuickReply(label=item["label"], value=item["value"])
                    for item in attendance.get("current_quick_replies", [])
                ]
            )

        return AttendanceResponse(
            triage_id=str(attendance["_id"]),
            status=AttendanceStatus(attendance["status"]),
            start_date=datetime.fromisoformat(attendance["start_date"]),
            end_date=datetime.fromisoformat(attendance["end_date"]) if attendance.get("end_date") else None,
            client=AttendanceClient(
                id=UUID(client_raw["id"]),
                name=client_raw["name"],
                email=client_raw["email"],
                company=client_raw.get("company"),
            ),
            triage=[
                TriageStepSchema(
                    step=item["step"],
                    question=item["question"],
                    answer_value=item.get("answer_value"),
                    answer_text=item.get("answer_text"),
                )
                for item in attendance.get("triage", [])
            ],
            result=AttendanceResult(**result_raw) if result_raw else None,
            evaluation=AttendanceEvaluation(**evaluation_raw) if evaluation_raw else None,
            current_step_id=attendance.get("current_step_id"),
            current_message=attendance.get("current_message"),
            current_input=current_input,
        )