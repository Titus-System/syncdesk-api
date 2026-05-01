from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from bson import ObjectId

from app.core.logger import get_logger
from app.domains.chatbot.enums import AttendanceStatus, TriageState
from app.domains.chatbot.exceptions import (
    AttendanceAlreadyEvaluatedException,AttendanceCreationException,AttendanceNotFinishedException,
    AttendanceNotFoundException,MissingClientDataException
)
from app.domains.chatbot.fsm import ChatbotFSM
from app.domains.chatbot.metrics import chatbot_messages_total
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


class ChatbotService:
    def __init__(self, repository: ChatbotRepository) -> None:
        self.repository = repository
        self.logger = get_logger("app.chatbot.service")

    async def create_attendance(
        self,
        client: AttendanceClient,
        triage_id: str | None = None,
    ) -> TriageData:
        dto = CreateAttendanceDTO(client=client)
        final_triage_id = triage_id or str(ObjectId())
        attendance = await self.repository.create_attendance(dto, final_triage_id)

        bot_response = ChatbotFSM.process_interaction(None, "")
        self._record_step_metric(bot_response)

        attendance["triage"] = [self._build_triage_step(bot_response)]
        await self.repository.save_attendance(final_triage_id, attendance)

        return self._build_triage_data(final_triage_id, bot_response)

    async def process_message(self, payload: TriageInputDTO) -> TriageData:
        attendance_db = await self.repository.find_attendance(payload.triage_id)

        if attendance_db is None:
            bootstrap_client = self._build_attendance_client_from_payload(payload)
            await self.create_attendance(bootstrap_client, payload.triage_id)
            attendance_db = await self.repository.find_attendance(payload.triage_id)

            if attendance_db is None:
                raise AttendanceCreationException()

        attendance: dict[str, Any] = attendance_db

        triage: list[dict[str, Any]] = attendance.get("triage", [])
        current_state: TriageState | None = None
        last_step: str | None = None

        if triage:
            last_interaction = triage[-1]
            step = last_interaction.get("step")

            current_state = TriageState(step) if step is not None else None
            last_step = step

            if payload.answer_text is not None:
                last_interaction["answer_text"] = payload.answer_text
            if payload.answer_value is not None:
                last_interaction["answer_value"] = payload.answer_value

        user_message = payload.answer_value if payload.answer_value else (payload.answer_text or "")

        bot_response = ChatbotFSM.process_interaction(current_state, user_message)
        self._record_step_metric(bot_response)

        if bot_response.is_finished:
            is_ticket = bot_response.new_state == TriageState.TICKET_CREATED
            self.logger.info("Triage finished", extra={"triage_id": payload.triage_id})
            attendance["status"] = AttendanceStatus.FINISHED.value
            attendance["end_date"] = datetime.now(UTC).isoformat()
            attendance["result"] = {
                "type": "Ticket" if is_ticket else "Resolved",
                "closure_message": bot_response.response_text,
            }
        else:
            new_state_value = (
                bot_response.new_state.value if bot_response.new_state else "UNKNOWN"
            )
            if new_state_value != last_step:
                triage.append(self._build_triage_step(bot_response))

        attendance["triage"] = triage

        await self.repository.save_attendance(payload.triage_id, attendance)

        return self._build_triage_data(payload.triage_id, bot_response)

    async def list_attendances(
        self, filters: AttendanceSearchFiltersDTO
    ) -> list[AttendanceResponse]:
        docs = await self.repository.list_attendances(filters)
        return [self._map_attendance_response(doc) for doc in docs]

    async def get_attendance(self, triage_id: str) -> AttendanceResponse:
        attendance = await self.repository.find_attendance(triage_id)
        if attendance is None:
            raise AttendanceNotFoundException(triage_id)
        return self._map_attendance_response(attendance)

    async def finish_attendance_pending_evaluation(self, triage_id: str) -> bool:
        finished_at = datetime.now(UTC)
        try:
            updated = await self.repository.finish_attendance_pending_evaluation(
                triage_id,
                finished_at.isoformat(),
            )
        except Exception:
            self.logger.exception(
                "Failed to finish attendance from ticket close event",
                extra={"triage_id": triage_id},
            )
            return False
        if updated:
            self.logger.info(
                "Attendance finished from ticket close event",
                extra={"triage_id": triage_id},
            )
        else:
            self.logger.debug(
                "Skipping attendance finish from ticket close event - attendance not found",
                extra={"triage_id": triage_id},
            )
        return updated

    async def set_evaluation(
        self, triage_id: str, payload: EvaluationRequest
    ) -> EvaluationResponse:
        attendance = await self.repository.find_attendance(triage_id)
        if attendance is None:
            raise AttendanceNotFoundException(triage_id)

        if attendance.get("status") != AttendanceStatus.FINISHED.value:
            raise AttendanceNotFinishedException()

        if attendance.get("evaluation") is not None:
            raise AttendanceAlreadyEvaluatedException()

        evaluated_at = datetime.now(UTC)
        attendance["evaluation"] = AttendanceEvaluation(rating=payload.rating).model_dump(mode="json")
        attendance["end_date"] = attendance.get("end_date") or evaluated_at.isoformat()

        await self.repository.save_attendance(triage_id, attendance)

        return EvaluationResponse(
            triage_id=triage_id,
            rating=payload.rating,
            evaluated_at=evaluated_at,
        )

    def _record_step_metric(self, bot_response: InternalBotResponseDTO) -> None:
        step_label = bot_response.new_state.value if bot_response.new_state else "unknown"
        chatbot_messages_total.labels(step=step_label).inc()

    def _build_triage_step(self, bot_response: InternalBotResponseDTO) -> dict[str, Any]:
        return {
            "step": bot_response.new_state.value if bot_response.new_state else "UNKNOWN",
            "question": bot_response.response_text,
            "answer_text": None,
            "answer_value": None,
            "type": "free_text" if bot_response.is_free_text else "quick_replies",
        }

    def _build_triage_data(
        self, triage_id: str, bot_response: InternalBotResponseDTO
    ) -> TriageData:
        if bot_response.is_finished:
            is_ticket = bot_response.new_state == TriageState.TICKET_CREATED
            return TriageData(
                triage_id=triage_id,
                finished=True,
                closure_message=bot_response.response_text,
                result=(
                    TriageResult(type="Ticket", id=triage_id) if is_ticket else None
                ),
            )

        formatted_step_id = (
            f"step_{bot_response.new_state.value.lower()}"
            if bot_response.new_state
            else "step_unknown"
        )
        input_def = TriageInputDef(
            mode="free_text" if bot_response.is_free_text else "quick_replies",
            quick_replies=(
                [
                    QuickReply(label=op["label"], value=op["value"])
                    for op in bot_response.quick_replies
                ]
                if bot_response.quick_replies
                else None
            ),
        )
        return TriageData(
            triage_id=triage_id,
            step_id=formatted_step_id,
            message=bot_response.response_text,
            input=input_def,
        )

    def _build_attendance_client_from_payload(self, payload: TriageInputDTO) -> AttendanceClient:
        missing_fields: list[str] = []
        if payload.client_id is None:
            missing_fields.append("client_id")
        if not payload.client_name:
            missing_fields.append("client_name")
        if not payload.client_email:
            missing_fields.append("client_email")

        if missing_fields:
            detail_msg = (
                "triage_id was not found. To auto-create attendance, provide fields: "
                + ", ".join(missing_fields)
            )
            raise MissingClientDataException(detail=detail_msg)

        client_id = payload.client_id
        client_name = payload.client_name
        client_email = payload.client_email
        if client_id is None or client_name is None or client_email is None:
            raise MissingClientDataException()

        return AttendanceClient(
            id=client_id,
            name=client_name,
            email=client_email,
        )

    def _map_attendance_response(self, attendance: dict[str, Any]) -> AttendanceResponse:
        client_raw = attendance["client"]
        result_raw = attendance.get("result")
        evaluation_raw = attendance.get("evaluation")

        start_date_raw = attendance["start_date"]
        start_date = (
            datetime.fromisoformat(start_date_raw)
            if isinstance(start_date_raw, str)
            else start_date_raw
        )
        end_date_raw = attendance.get("end_date")
        end_date = (
            datetime.fromisoformat(end_date_raw)
            if isinstance(end_date_raw, str)
            else end_date_raw
        )

        return AttendanceResponse(
            triage_id=str(attendance["_id"]),
            status=AttendanceStatus(attendance["status"]),
            start_date=start_date,
            end_date=end_date,
            client=AttendanceClient(
                id=UUID(client_raw["id"]) if isinstance(client_raw.get("id"), str) else client_raw["id"],
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
        )
