import asyncio
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from beanie import PydanticObjectId
from bson import ObjectId

from app.core.event_dispatcher.enums import AppEvent
from app.core.event_dispatcher.event_dispatcher import EventDispatcher
from app.core.event_dispatcher.schemas import TriageFinishedEventSchema
from app.core.logger import get_logger
from app.domains.chatbot.enums import AttendanceStatus, TriageState
from app.domains.chatbot.exceptions import (
    AttendanceAlreadyEvaluatedException,
    AttendanceCreationException,
    AttendanceNotFinishedException,
    AttendanceNotFoundException,
    MissingClientDataException,
)
from app.domains.chatbot.fsm import ChatbotFSM
from app.domains.chatbot.metrics import chatbot_messages_total
from app.domains.chatbot.models import (
    AttendanceClient,
    AttendanceEvaluation,
    AttendanceResult,
)
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
    TriageInputDTO,
    TriageInputDef,
    TriageResult,
    TriageStepSchema,
)
from app.domains.ticket.models import TicketCriticality, TicketType


class ChatbotService:
    def __init__(
        self,
        repository: ChatbotRepository,
        dispatcher: EventDispatcher,
    ) -> None:
        self.repository = repository
        self.dispatcher = dispatcher
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

        if attendance.get("status") == AttendanceStatus.FINISHED.value:
            return self._build_finished_triage_data_from_attendance(
                payload.triage_id,
                attendance,
            )

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

        ticket_id: str | None = None
        chat_id: str | None = None

        if bot_response.is_finished:
            is_ticket = bot_response.new_state == TriageState.TICKET_CREATED

            self.logger.info(
                "Triage finished",
                extra={
                    "triage_id": payload.triage_id,
                    "is_ticket": is_ticket,
                },
            )

            attendance["status"] = AttendanceStatus.FINISHED.value
            attendance["end_date"] = datetime.now(UTC).isoformat()
            attendance["result"] = {
                "type": "Ticket" if is_ticket else "Resolved",
                "closure_message": bot_response.response_text,
                "ticket_id": None,
                "chat_id": None,
            }
            attendance["triage"] = triage

            await self.repository.save_attendance(payload.triage_id, attendance)

            if is_ticket:
                ticket_id, chat_id = await self._publish_triage_finished_and_resolve_ids(
                    payload.triage_id,
                    attendance,
                )

                attendance["result"]["ticket_id"] = ticket_id
                attendance["result"]["chat_id"] = chat_id

                await self.repository.save_attendance(payload.triage_id, attendance)

            return self._build_triage_data(
                payload.triage_id,
                bot_response,
                ticket_id=ticket_id,
                chat_id=chat_id,
            )

        new_state_value = bot_response.new_state.value if bot_response.new_state else "UNKNOWN"

        if new_state_value != last_step:
            triage.append(self._build_triage_step(bot_response))

        attendance["triage"] = triage

        await self.repository.save_attendance(payload.triage_id, attendance)

        return self._build_triage_data(payload.triage_id, bot_response)

    async def list_attendances(
        self,
        filters: AttendanceSearchFiltersDTO,
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
                "Skipping attendance finish from ticket close event because attendance was not found",
                extra={"triage_id": triage_id},
            )

        return updated

    async def set_evaluation(
        self,
        triage_id: str,
        payload: EvaluationRequest,
    ) -> EvaluationResponse:
        attendance = await self.repository.find_attendance(triage_id)

        if attendance is None:
            raise AttendanceNotFoundException(triage_id)

        if attendance.get("status") != AttendanceStatus.FINISHED.value:
            raise AttendanceNotFinishedException()

        if attendance.get("evaluation") is not None:
            raise AttendanceAlreadyEvaluatedException()

        evaluated_at = datetime.now(UTC)

        attendance["evaluation"] = AttendanceEvaluation(
            rating=payload.rating,
        ).model_dump(mode="json")
        attendance["end_date"] = attendance.get("end_date") or evaluated_at.isoformat()

        await self.repository.save_attendance(triage_id, attendance)

        return EvaluationResponse(
            triage_id=triage_id,
            rating=payload.rating,
            evaluated_at=evaluated_at,
        )

    async def _publish_triage_finished_and_resolve_ids(
        self,
        triage_id: str,
        attendance: dict[str, Any],
    ) -> tuple[str | None, str | None]:
        event_payload = self._build_triage_finished_event(triage_id, attendance)

        await self.dispatcher.publish(
            AppEvent.TRIAGE_FINISHED,
            event_payload,
        )

        ticket_id: str | None = None
        chat_id: str | None = None

        for _ in range(20):
            ticket_id, chat_id = await self.repository.find_ticket_and_conversation_ids_by_triage_id(
                triage_id,
            )

            if ticket_id is not None and chat_id is not None:
                break

            await asyncio.sleep(0.05)

        if ticket_id is None:
            self.logger.warning(
                "Triage finished event was published but ticket was not found",
                extra={"triage_id": triage_id},
            )

        if ticket_id is not None and chat_id is None:
            self.logger.warning(
                "Ticket was created but conversation was not found",
                extra={
                    "triage_id": triage_id,
                    "ticket_id": ticket_id,
                },
            )

        return ticket_id, chat_id

    def _build_triage_finished_event(
        self,
        triage_id: str,
        attendance: dict[str, Any],
    ) -> TriageFinishedEventSchema:
        client_raw = attendance["client"]
        company_raw = client_raw.get("company")

        ticket_type, ticket_criticality, product_name, ticket_description = (
            self._derive_ticket_payload_from_triage(attendance)
        )

        company_id: UUID | None = None
        company_name: str | None = None

        if isinstance(company_raw, dict):
            raw_company_id = company_raw.get("id")

            if raw_company_id is not None:
                company_id = self._coerce_uuid(raw_company_id)

            company_name_raw = company_raw.get("name")

            if company_name_raw is not None:
                company_name = str(company_name_raw)

        return TriageFinishedEventSchema(
            client_id=self._coerce_uuid(client_raw["id"]),
            client_email=str(client_raw["email"]),
            client_name=str(client_raw["name"]),
            company_id=company_id,
            company_name=company_name,
            attendance_id=PydanticObjectId(triage_id),
            ticket_type=ticket_type,
            ticket_criticality=ticket_criticality,
            product_name=product_name,
            ticket_description=ticket_description,
        )

    def _derive_ticket_payload_from_triage(
        self,
        attendance: dict[str, Any],
    ) -> tuple[TicketType, TicketCriticality, str, str]:
        triage: list[dict[str, Any]] = attendance.get("triage", [])

        main_menu_answer = self._answer_value_for_step(triage, TriageState.MAIN_MENU.value)
        product_problem_answer = self._answer_value_for_step(
            triage,
            TriageState.CHOOSING_PRODUCT_PROBLEM.value,
        )

        product_name = self._resolve_product_name(main_menu_answer)
        description = self._last_text_answer(triage) or "Solicitação criada pela URA digital."

        if main_menu_answer == "5":
            return (
                TicketType.ACCESS,
                TicketCriticality.MEDIUM,
                "Sync Desk",
                description,
            )

        if product_problem_answer == "2":
            return (
                TicketType.NEW_FEATURE,
                TicketCriticality.MEDIUM,
                product_name,
                description,
            )

        return (
            TicketType.ISSUE,
            TicketCriticality.MEDIUM,
            product_name,
            description,
        )

    def _answer_value_for_step(
        self,
        triage: list[dict[str, Any]],
        step: str,
    ) -> str | None:
        for item in triage:
            if item.get("step") == step and item.get("answer_value") is not None:
                return str(item["answer_value"])
        return None

    def _last_text_answer(self, triage: list[dict[str, Any]]) -> str | None:
        for item in reversed(triage):
            answer_text = item.get("answer_text")

            if isinstance(answer_text, str) and answer_text.strip():
                return answer_text.strip()

        return None

    def _resolve_product_name(self, answer_value: str | None) -> str:
        product_map = {
            "1": "Produto A",
            "2": "Produto B",
            "3": "Produto C",
        }

        return product_map.get(answer_value or "", "Produto não informado")

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
        self,
        triage_id: str,
        bot_response: InternalBotResponseDTO,
        ticket_id: str | None = None,
        chat_id: str | None = None,
    ) -> TriageData:
        if bot_response.is_finished:
            is_ticket = bot_response.new_state == TriageState.TICKET_CREATED

            return TriageData(
                triage_id=triage_id,
                finished=True,
                closure_message=bot_response.response_text,
                result=(
                    TriageResult(
                        type="Ticket",
                        id=triage_id,
                        ticket_id=ticket_id,
                        chat_id=chat_id,
                    )
                    if is_ticket
                    else None
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
                    QuickReply(label=option["label"], value=option["value"])
                    for option in bot_response.quick_replies
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

    def _build_finished_triage_data_from_attendance(
        self,
        triage_id: str,
        attendance: dict[str, Any],
    ) -> TriageData:
        result_raw = attendance.get("result") or {}
        result_type = result_raw.get("type")
        closure_message = result_raw.get("closure_message") or "Atendimento finalizado."

        return TriageData(
            triage_id=triage_id,
            finished=True,
            closure_message=closure_message,
            result=(
                TriageResult(
                    type="Ticket",
                    id=triage_id,
                    ticket_id=result_raw.get("ticket_id"),
                    chat_id=result_raw.get("chat_id"),
                )
                if result_type == "Ticket"
                else None
            ),
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

        start_date = self._coerce_datetime(attendance["start_date"])
        end_date = self._coerce_datetime(attendance.get("end_date"))

        current_step_id, current_message, current_input = self._get_current_input(attendance)

        return AttendanceResponse(
            triage_id=str(attendance["_id"]),
            status=AttendanceStatus(attendance["status"]),
            start_date=start_date,
            end_date=end_date,
            client=AttendanceClient(
                id=self._coerce_uuid(client_raw["id"]),
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
            current_step_id=current_step_id,
            current_message=current_message,
            current_input=current_input,
        )

    def _get_current_input(
        self,
        attendance: dict[str, Any],
    ) -> tuple[str | None, str | None, TriageInputDef | None]:
        if attendance.get("status") == AttendanceStatus.FINISHED.value:
            return None, None, None

        triage: list[dict[str, Any]] = attendance.get("triage", [])

        if not triage:
            return None, None, None

        current = triage[-1]
        step = current.get("step")

        if step is None:
            return None, None, None

        try:
            state = TriageState(step)
        except ValueError:
            return None, None, None

        bot_response = ChatbotFSM._get_state_response(state)
        triage_data = self._build_triage_data(str(attendance["_id"]), bot_response)

        return triage_data.step_id, triage_data.message, triage_data.input

    def _coerce_uuid(self, value: Any) -> UUID:
        if isinstance(value, UUID):
            return value

        return UUID(str(value))

    def _coerce_datetime(self, value: Any) -> datetime | None:
        if value is None:
            return None

        if isinstance(value, datetime):
            return value

        return datetime.fromisoformat(str(value))