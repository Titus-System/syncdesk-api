import uuid
from typing import Any, cast
from datetime import datetime, timezone
from uuid import UUID, uuid4

from beanie import PydanticObjectId
from bson import ObjectId
from fastapi import status

from app.core.exceptions import AppHTTPException
from app.domains.chatbot.enums import TriageState
from app.domains.chatbot.schemas import (
    AttendanceClient, CreateAttendanceDTO, TriageInputDTO, TriageResponseDTO, TriageData, TriageInputDef, 
    QuickReply, TriageResponseMeta, TriageResult
)
from app.domains.chatbot.fsm import ChatbotFSM
from app.domains.chatbot.repositories.chatbot_repository import ChatbotRepository
from app.domains.ticket.models import (
    Ticket,
    TicketClient,
    TicketCompany,
    TicketCriticality,
    TicketStatus,
    TicketType,
)

class ChatbotService:
    def __init__(self, repository: ChatbotRepository) -> None:
        self.repository = repository

    async def create_attendance(
        self,
        client: AttendanceClient,
        triage_id: str | None = None,
    ) -> dict[str, Any]:
        dto = CreateAttendanceDTO(
            client = client
        )
        final_triage_id = triage_id or str(ObjectId())
        return await self.repository.create_attendance(dto, final_triage_id)

    async def process_message(self, payload: TriageInputDTO) -> TriageResponseDTO:
        attendance_db = await self.repository.find_attendance(payload.triage_id)

        if attendance_db is None:
            bootstrap_client = self._build_attendance_client_from_payload(payload)
            await self.create_attendance(bootstrap_client, payload.triage_id)
            attendance_db = await self.repository.find_attendance(payload.triage_id)

            if attendance_db is None:
                raise AppHTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=(
                        "Attendance was created but could not be loaded afterward. "
                        "Please try again."
                    ),
                )

        attendance: dict[str, Any] = attendance_db
        
        triage: list[dict[str, Any]] = attendance.get("triage", [])
        current_state: TriageState | None = None
        
        if triage:
            last_interaction = triage[-1]
            step = last_interaction.get("step")
            
            current_state = TriageState(step) if step is not None else None
            
            if payload.answer_text is not None:
                last_interaction["answer_text"] = payload.answer_text
            if payload.answer_value is not None:
                last_interaction["answer_value"] = payload.answer_value

        user_message = payload.answer_value if payload.answer_value else (payload.answer_text or "")

        bot_response = ChatbotFSM.process_interaction(current_state, user_message)

        if not bot_response.is_finished:
            new_question: dict[str, Any] = {
                "step": bot_response.new_state.value if bot_response.new_state else "UNKNOWN",
                "question": bot_response.response_text,
                "answer_text": None,
                "answer_value": None,
                "type": "free_text" if bot_response.is_free_text else "quick_replies"
            }
            triage.append(new_question)

        attendance["triage"] = triage

        ticket_id = None
        if bot_response.new_state == TriageState.TICKET_CREATED:
            free_text_context = payload.answer_text if payload.answer_text else "Solicitação criada via URA"
            ticket_id = await self._generate_ticket_with_context(attendance, free_text_context, payload.triage_id)

        # Resolve o format do step id atual (fallback para unknown se for nulo)
        formatted_step_id = f"step_{bot_response.new_state.value.lower()}" if bot_response.new_state else "step_unknown"
        
        if bot_response.is_finished:
            attendance["status"] = "finished" 
            attendance["end_date"] = datetime.now(timezone.utc)
            attendance["result"] = {
                "type": "Ticket" if ticket_id else "Resolved",
                "closure_message": bot_response.response_text
            }
            
            data = TriageData(
                triage_id=payload.triage_id,
                finished=True,
                closure_message=bot_response.response_text,
                result=TriageResult(type="Ticket", id=str(ticket_id)) if ticket_id else None
            )
        else:
            input_def = TriageInputDef(
                mode="free_text" if bot_response.is_free_text else "quick_replies",
                quick_replies=[QuickReply(label=op["label"], value=op["value"]) for op in bot_response.quick_replies] if bot_response.quick_replies else None
            )
            data = TriageData(
                triage_id=payload.triage_id,
                step_id=formatted_step_id,
                message=bot_response.response_text,
                input=input_def
            )

        await self.repository.save_attendance(payload.triage_id, attendance)

        meta = TriageResponseMeta(
            timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            success=True,
            request_id=str(uuid.uuid4())
        )

        return TriageResponseDTO(data=data, meta=meta)

    async def _generate_ticket_with_context(self, attendance: dict[str, Any], free_text: str, attendance_id: str) -> str:
        full_triage: list[dict[str, Any]] = attendance.get("triage", [])
        
        demand_type = "issue"
        criticality = "high"
        product = "N/A"

        for interaction in full_triage:
            step = interaction.get("step")
            value = interaction.get("answer_value")

            if step == "A" and value in ["1", "2", "3"]:
                if value == "1": product = "Product A"
                elif value == "2": product = "Product B"
                elif value == "3": product = "Product C"
            
            if step == "A" and value == "5":
                demand_type = "access"
                criticality = "medium"

            if step == "B":
                if value == "1":
                    demand_type = "issue"
                    criticality = "high"
                elif value == "2":
                    demand_type = "new_feature"
                    criticality = "low"

        triage_object_id = self._resolve_triage_object_id(attendance, attendance_id)
        ticket = Ticket(
            triage_id=triage_object_id,
            type=self._resolve_ticket_type(demand_type),
            criticality=self._resolve_ticket_criticality(criticality),
            product=product,
            status=TicketStatus.OPEN,
            creation_date=datetime.now(timezone.utc),
            description=free_text,
            chat_ids=[],
            agent_history=[],
            client=self._build_ticket_client(attendance),
            comments=[],
        )

        return await self.repository.create_ticket(ticket)

    def _resolve_triage_object_id(self, attendance: dict[str, Any], attendance_id: str) -> PydanticObjectId:
        raw_id = attendance.get("_id", attendance_id)
        if isinstance(raw_id, ObjectId):
            return cast(PydanticObjectId, raw_id)

        raw_id_str = str(raw_id)
        if ObjectId.is_valid(raw_id_str):
            return cast(PydanticObjectId, ObjectId(raw_id_str))

        raise ValueError("triage_id must be a valid ObjectId to create a ticket")

    def _resolve_ticket_type(self, demand_type: str) -> TicketType:
        if demand_type == TicketType.ACCESS.value:
            return TicketType.ACCESS
        if demand_type == TicketType.NEW_FEATURE.value:
            return TicketType.NEW_FEATURE
        return TicketType.ISSUE

    def _resolve_ticket_criticality(self, criticality: str) -> TicketCriticality:
        if criticality == TicketCriticality.MEDIUM.value:
            return TicketCriticality.MEDIUM
        if criticality == TicketCriticality.LOW.value:
            return TicketCriticality.LOW
        return TicketCriticality.HIGH

    def _build_ticket_client(self, attendance: dict[str, Any]) -> TicketClient:
        client_data_raw = attendance.get("client", {})
        client_data: dict[str, Any] = (
            cast(dict[str, Any], client_data_raw) if isinstance(client_data_raw, dict) else {}
        )

        client_id = self._parse_uuid(client_data.get("id")) or uuid4()
        company_data_raw = client_data.get("company", {})
        company_data: dict[str, Any] = (
            cast(dict[str, Any], company_data_raw) if isinstance(company_data_raw, dict) else {}
        )
        company_id = self._parse_uuid(company_data.get("id")) or client_id

        email_raw = client_data.get("email")
        email = str(email_raw) if email_raw else f"{client_id}@unknown.local"
        name_raw = client_data.get("name") or client_data.get("username") or email
        name = str(name_raw)
        company_name_raw = company_data.get("name")
        company_name = str(company_name_raw) if company_name_raw else "Unknown company"

        return TicketClient(
            id=client_id,
            name=name,
            email=email,
            company=TicketCompany(id=company_id, name=company_name),
        )

    def _parse_uuid(self, raw_value: Any) -> UUID | None:
        if raw_value is None:
            return None
        if isinstance(raw_value, UUID):
            return raw_value
        try:
            return UUID(str(raw_value))
        except (TypeError, ValueError):
            return None

    def _build_attendance_client_from_payload(self, payload: TriageInputDTO) -> AttendanceClient:
        missing_fields: list[str] = []
        if payload.client_id is None:
            missing_fields.append("client_id")
        if not payload.client_name:
            missing_fields.append("client_name")
        if not payload.client_email:
            missing_fields.append("client_email")

        if missing_fields:
            raise AppHTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=(
                    "triage_id was not found. To auto-create attendance, provide fields: "
                    + ", ".join(missing_fields)
                ),
            )

        client_id = payload.client_id
        client_name = payload.client_name
        client_email = payload.client_email
        if client_id is None or client_name is None or client_email is None:
            raise AppHTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Missing client data to create attendance.",
            )

        return AttendanceClient(
            id=client_id,
            name=client_name,
            email=client_email,
        )