import uuid
from typing import Any
from datetime import datetime, timezone

from app.domains.chatbot.enums import TriageState
from app.domains.chatbot.schemas import (
    TriageInputDTO, TriageResponseDTO, TriageData, TriageInputDef, 
    QuickReply, TriageResponseMeta, TriageResult
)
from app.domains.chatbot.fsm import ChatbotFSM
from app.domains.chatbot.repositories.chatbot_repository import ChatbotRepository

class ChatbotService:
    def __init__(self, repository: ChatbotRepository) -> None:
        self.repository = repository

    async def process_message(self, payload: TriageInputDTO) -> TriageResponseDTO:
        attendance_db = await self.repository.find_attendance(payload.triage_id)
        
        attendance: dict[str, Any] = {}
        if attendance_db is None:
            attendance = {
                "_id": payload.triage_id, 
                "triage": [],
                "client": {}, 
                "status": "in_progress",
                "start_date": datetime.now(timezone.utc).isoformat()
            }
        else:
            attendance = attendance_db
        
        triage: list[dict[str, Any]] = attendance.get("triage", [])
        current_state: TriageState | None = None
        
        if triage:
            last_interaction = triage[-1]
            step = last_interaction.get("step")
            
            current_state = TriageState(step) if step is not None else None
            
            if payload.answer_text:
                last_interaction["answer_text"] = payload.answer_text
            if payload.answer_value:
                last_interaction["answer_value"] = payload.answer_value

        user_message = payload.answer_value if payload.answer_value else (payload.answer_text or "")

        bot_response = ChatbotFSM.process_interaction(current_state, user_message)

        new_question: dict[str, Any] = {
            "step": bot_response.new_state.value,
            "question": bot_response.response_text,
            "answer_text": None,
            "answer_value": None,
            "type": "free_text" if bot_response.is_free_text else "quick_replies"
        }
        
        triage.append(new_question)
        attendance["triage"] = triage

        await self.repository.save_attendance(payload.triage_id, attendance)

        ticket_id = None
        if bot_response.new_state == TriageState.TICKET_CREATED:
            free_text_context = payload.answer_text if payload.answer_text else "Solicitação criada via URA"
            ticket_id = await self._generate_ticket_with_context(attendance, free_text_context, payload.triage_id)

        formatted_step_id = f"step_{bot_response.new_state.value.lower()}"
        
        if bot_response.is_finished:
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

        client_data: dict[str, Any] = attendance.get("client", {})
        
        mock_ticket_id = str(uuid.uuid4()) 

        new_ticket: dict[str, Any] = {
            "_id": mock_ticket_id,
            "triage_id": attendance_id,
            "type": demand_type,
            "criticality": criticality,
            "product": product,
            "status": "Open",
            "creation_date": datetime.now(timezone.utc).isoformat(),
            "description": free_text,
            "chat_id": None,
            "agent_history": [],
            "client": client_data,
            "comments": []
        }

        await self.repository.create_ticket(new_ticket)
        return mock_ticket_id