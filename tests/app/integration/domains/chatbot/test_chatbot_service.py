from collections.abc import AsyncGenerator
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from beanie import PydanticObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.exceptions import AppHTTPException
from app.domains.chatbot.models import AttendanceClient, AttendanceCompany
from app.domains.chatbot.repositories.chatbot_repository import ChatbotRepository
from app.domains.chatbot.schemas import TriageInputDTO
from app.domains.chatbot.services.chatbot_service import ChatbotService


@pytest_asyncio.fixture(autouse=True)
async def cleanup_collections(
	mongo_db_conn: AsyncIOMotorDatabase[dict[str, Any]],
) -> AsyncGenerator[None, None]:
	await mongo_db_conn["atendimentos"].delete_many({})
	yield
	await mongo_db_conn["atendimentos"].delete_many({})


class TestChatbotService:
	@pytest.fixture
	def service(self, mongo_db_conn: AsyncIOMotorDatabase[dict[str, Any]]) -> ChatbotService:
		repo = ChatbotRepository(mongo_db_conn)
		return ChatbotService(repo)

	@pytest.mark.asyncio
	async def test_create_attendance_persists_expected_base_model(
		self,
		service: ChatbotService,
	) -> None:
		client = AttendanceClient(
			id=uuid4(),
			name="John Silva",
			email="john@tech.com",
			company=AttendanceCompany(id=uuid4(), name="Tech Solutions"),
		)

		created = await service.create_attendance(client)
		stored = await service.repository.find_attendance(created["triage_id"])

		assert stored is not None
		assert str(stored["_id"]) == created["triage_id"]
		assert stored["status"] == "opened"
		assert isinstance(stored["start_date"], str)
		assert stored["end_date"] is None
		assert stored["client"]["name"] == "John Silva"
		assert stored["client"]["email"] == "john@tech.com"
		assert stored["client"]["company"]["name"] == "Tech Solutions"
		assert stored["result"] is None
		assert stored["evaluation"] is None
		assert stored["triage"] == []

	@pytest.mark.asyncio
	async def test_process_message_bootstraps_attendance_for_unknown_triage_id(
		self,
		service: ChatbotService,
	) -> None:
		triage_id = str(PydanticObjectId())
		payload = TriageInputDTO(
			triage_id=triage_id,
			step_id="step_a",
			answer_text=None,
			answer_value=None,
			client_id=uuid4(),
			client_name="John Silva",
			client_email="john@tech.com",
		)

		response = await service.process_message(payload)
		stored = await service.repository.find_attendance(triage_id)

		assert response.triage_id == triage_id
		assert response.step_id == "step_a"
		assert response.input is not None
		assert response.input.mode == "quick_replies"

		assert stored is not None
		assert str(stored["_id"]) == triage_id
		assert stored["client"]["name"] == "John Silva"
		assert stored["client"]["email"] == "john@tech.com"
		assert len(stored["triage"]) == 1
		assert stored["triage"][0]["step"] == "A"
		assert stored["triage"][0]["answer_text"] is None
		assert stored["triage"][0]["answer_value"] is None

	@pytest.mark.asyncio
	async def test_process_message_unknown_triage_without_client_payload_returns_422(
		self,
		service: ChatbotService,
	) -> None:
		payload = TriageInputDTO(
			triage_id=str(PydanticObjectId()),
			step_id="step_a",
			answer_text=None,
			answer_value=None,
			client_id=None,
			client_name=None,
			client_email=None,
		)

		with pytest.raises(AppHTTPException) as exc_info:
			await service.process_message(payload)

		assert exc_info.value.status_code == 422
		assert "triage_id was not found" in str(exc_info.value.detail)

	@pytest.mark.asyncio
	async def test_process_message_flow_updates_triage_answers_and_finishes(
		self,
		service: ChatbotService,
	) -> None:
		triage_id = str(PydanticObjectId())
		client_id = uuid4()

		# 1) Open flow and receive step A
		await service.process_message(
			TriageInputDTO(
				triage_id=triage_id,
				step_id="step_a",
				answer_text=None,
				answer_value=None,
				client_id=client_id,
				client_name="John Silva",
				client_email="john@tech.com",
			)
		)

		# 2) Answer A -> go to B
		await service.process_message(
			TriageInputDTO(
				triage_id=triage_id,
				step_id="step_a",
				answer_text=None,
				answer_value="1",
				client_id=None,
				client_name=None,
				client_email=None,
			)
		)

		# 3) Answer B -> go to F (free text)
		await service.process_message(
			TriageInputDTO(
				triage_id=triage_id,
				step_id="step_b",
				answer_text=None,
				answer_value="1",
				client_id=None,
				client_name=None,
				client_email=None,
			)
		)

		# 4) Answer F -> finalizado pelo ChatbotService (criação do ticket fica a cargo do event bus)
		final_response = await service.process_message(
			TriageInputDTO(
				triage_id=triage_id,
				step_id="step_f",
				answer_text=(
					"The system freezes when generating the monthly sales "
					"report on the desktop version."
				),
				answer_value=None,
				client_id=None,
				client_name=None,
				client_email=None,
			)
		)

		stored = await service.repository.find_attendance(triage_id)

		assert final_response.finished is True
		assert final_response.result is not None
		assert final_response.result.type == "Ticket"
		assert final_response.closure_message is not None

		assert stored is not None
		assert stored["status"] == "finished"
		assert stored["result"]["type"] == "Ticket"
		assert stored["triage"][0]["step"] == "A"
		assert stored["triage"][0]["answer_value"] == "1"
		assert stored["triage"][1]["step"] == "B"
		assert stored["triage"][1]["answer_value"] == "1"
		assert stored["triage"][2]["step"] == "F"
		assert stored["triage"][2]["type"] == "free_text"
		assert "freezes" in stored["triage"][2]["answer_text"]
