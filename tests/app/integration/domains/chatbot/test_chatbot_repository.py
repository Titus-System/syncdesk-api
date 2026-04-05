from datetime import UTC, datetime
from collections.abc import AsyncGenerator
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from beanie import PydanticObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.domains.chatbot.repositories.chatbot_repository import ChatbotRepository
from app.domains.chatbot.schemas import AttendanceClient, AttendanceCompany, CreateAttendanceDTO
from app.domains.ticket.models import (
	Ticket,
	TicketClient,
	TicketComment,
	TicketCompany,
	TicketCriticality,
	TicketStatus,
	TicketType,
)


@pytest_asyncio.fixture(autouse=True)
async def cleanup_collections(
	mongo_db_conn: AsyncIOMotorDatabase[dict[str, Any]],
) -> AsyncGenerator[None, None]:
	await mongo_db_conn["atendimentos"].delete_many({})
	await Ticket.delete_all()
	yield
	await mongo_db_conn["atendimentos"].delete_many({})
	await Ticket.delete_all()


class TestChatbotRepository:
	@pytest.fixture
	def repo(self, mongo_db_conn: AsyncIOMotorDatabase[dict[str, Any]]) -> ChatbotRepository:
		return ChatbotRepository(mongo_db_conn)

	@pytest.fixture
	def attendance_dto(self) -> CreateAttendanceDTO:
		return CreateAttendanceDTO(
			client=AttendanceClient(
				id=uuid4(),
				name="Client Test",
				email="client@test.com",
				company=AttendanceCompany(
					id=uuid4(),
					name="SyncDesk Co",
				),
			)
		)

	@pytest.mark.asyncio
	async def test_create_attendance_success(
		self,
		repo: ChatbotRepository,
		attendance_dto: CreateAttendanceDTO,
	) -> None:
		triage_id = str(PydanticObjectId())

		created = await repo.create_attendance(attendance_dto, triage_id)

		assert created["triage_id"] == triage_id
		assert created["client"]["email"] == attendance_dto.client.email
		assert created["triage"] == []

		stored = await repo.find_attendance(triage_id)
		assert stored is not None
		assert str(stored["_id"]) == triage_id
		assert stored["client"]["name"] == attendance_dto.client.name

	@pytest.mark.asyncio
	async def test_find_attendance_not_found_returns_none(
		self,
		repo: ChatbotRepository,
	) -> None:
		found = await repo.find_attendance(str(PydanticObjectId()))
		assert found is None

	@pytest.mark.asyncio
	async def test_find_attendance_with_string_id(
		self,
		repo: ChatbotRepository,
		attendance_dto: CreateAttendanceDTO,
	) -> None:
		triage_id = "triage-string-id"
		await repo.create_attendance(attendance_dto, triage_id)

		found = await repo.find_attendance(triage_id)

		assert found is not None
		assert found["_id"] == triage_id
		assert found["client"]["email"] == attendance_dto.client.email

	@pytest.mark.asyncio
	async def test_save_attendance_replaces_existing_document(
		self,
		repo: ChatbotRepository,
		attendance_dto: CreateAttendanceDTO,
	) -> None:
		triage_id = str(PydanticObjectId())
		await repo.create_attendance(attendance_dto, triage_id)

		replacement = {
			"_id": triage_id,
			"triage": [
				{
					"step": "A",
					"question": "Q1",
					"answer_text": None,
					"answer_value": "1",
					"type": "quick_replies",
				}
			],
			"client": {
				"id": str(attendance_dto.client.id),
				"name": "Updated Name",
				"email": attendance_dto.client.email,
			},
			"status": "in_progress",
			"start_date": datetime.now(UTC).isoformat(),
		}

		await repo.save_attendance(triage_id, replacement)
		updated = await repo.find_attendance(triage_id)

		assert updated is not None
		assert updated["triage"][0]["step"] == "A"
		assert updated["client"]["name"] == "Updated Name"
		assert updated["status"] == "in_progress"

	@pytest.mark.asyncio
	async def test_save_attendance_upsert_creates_document_when_missing(
		self,
		repo: ChatbotRepository,
	) -> None:
		triage_id = str(PydanticObjectId())
		full_attendance: dict[str, Any] = {
			"triage": [],
			"client": {},
			"status": "opened",
			"start_date": datetime.now(UTC).isoformat(),
		}

		await repo.save_attendance(triage_id, full_attendance)
		created = await repo.find_attendance(triage_id)

		assert created is not None
		assert str(created["_id"]) == triage_id
		assert created["status"] == "opened"

	@pytest.mark.asyncio
	async def test_save_attendance_persists_expected_document_format(
		self,
		repo: ChatbotRepository,
	) -> None:
		triage_id = "651"
		full_attendance: dict[str, Any] = {
			"_id": triage_id,
			"status": "finished",
			"start_date": "2024-03-26T10:00:00Z",
			"end_date": "2024-03-26T10:05:00Z",
			"client": {
				"id": "99",
				"name": "João Silva",
				"company": {
					"name": "Tech Solutions",
					"id": "34",
				},
				"email": "joao@tech.com",
			},
			"triage": [
				{
					"step": "A",
					"question": "Select the product or query",
					"answer_value": "1",
					"answer_text": "Product A",
				},
				{
					"step": "B",
					"question": "How can I help regarding Product A?",
					"answer_value": "1",
					"answer_text": "The system is showing failures.",
				},
				{
					"step": "F",
					"question": "Explain the problem in detail",
					"answer_text": "The system freezes when generating the monthly sales report on the desktop version.",
					"type": "free_text",
				},
			],
			"result": {
				"type": "Ticket",
				"closure_message": "Please wait, your request has been created...",
			},
			"evaluation": {
				"rating": 5,
			},
		}

		await repo.save_attendance(triage_id, full_attendance)
		stored = await repo.find_attendance(triage_id)

		assert stored is not None
		assert stored["_id"] == "651"
		assert stored["status"] == "finished"
		assert stored["start_date"] == "2024-03-26T10:00:00Z"
		assert stored["end_date"] == "2024-03-26T10:05:00Z"
		assert stored["client"]["id"] == "99"
		assert stored["client"]["name"] == "João Silva"
		assert stored["client"]["company"]["name"] == "Tech Solutions"
		assert stored["client"]["company"]["id"] == "34"
		assert stored["client"]["email"] == "joao@tech.com"
		assert len(stored["triage"]) == 3
		assert stored["triage"][0]["step"] == "A"
		assert stored["triage"][0]["question"] == "Select the product or query"
		assert stored["triage"][0]["answer_value"] == "1"
		assert stored["triage"][0]["answer_text"] == "Product A"
		assert stored["triage"][1]["step"] == "B"
		assert stored["triage"][1]["question"] == "How can I help regarding Product A?"
		assert stored["triage"][1]["answer_value"] == "1"
		assert stored["triage"][1]["answer_text"] == "The system is showing failures."
		assert stored["triage"][2]["step"] == "F"
		assert stored["triage"][2]["question"] == "Explain the problem in detail"
		assert stored["triage"][2]["answer_text"] == "The system freezes when generating the monthly sales report on the desktop version."
		assert stored["triage"][2]["type"] == "free_text"
		assert stored["result"]["type"] == "Ticket"
		assert stored["result"]["closure_message"] == "Please wait, your request has been created..."
		assert stored["evaluation"]["rating"] == 5

	@pytest.mark.asyncio
	async def test_create_ticket_success(
		self,
		repo: ChatbotRepository,
	) -> None:
		client_id = uuid4()
		ticket = Ticket(
			triage_id=PydanticObjectId(),
			type=TicketType.ISSUE,
			criticality=TicketCriticality.HIGH,
			product="Product A",
			status=TicketStatus.OPEN,
			creation_date=datetime.now(UTC),
			description="Issue created from chatbot repository integration test",
			chat_ids=[],
			agent_history=[],
			client=TicketClient(
				id=client_id,
				name="Client Test",
				email="client@test.com",
				company=TicketCompany(id=client_id, name="SyncDesk Co"),
			),
			comments=[
				TicketComment(
					author="system",
					text="created",
					date=datetime.now(UTC),
				)
			],
		)

		ticket_id = await repo.create_ticket(ticket)

		assert ticket_id
		stored = await Ticket.get(PydanticObjectId(ticket_id))
		assert stored is not None
		assert stored.product == "Product A"
		assert stored.status == TicketStatus.OPEN
