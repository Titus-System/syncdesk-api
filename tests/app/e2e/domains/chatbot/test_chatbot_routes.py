from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from bson import ObjectId
from httpx import AsyncClient
from motor.motor_asyncio import AsyncIOMotorDatabase

from tests.app.e2e.conftest import AuthActions


@pytest_asyncio.fixture(autouse=True)
async def cleanup_attendance_collection(
	mongo_db_conn: AsyncIOMotorDatabase[dict[str, Any]],
) -> None:
	await mongo_db_conn["atendimentos"].delete_many({})
	yield
	await mongo_db_conn["atendimentos"].delete_many({})


class TestChatbotRoutes:
	@pytest.mark.asyncio
	async def test_create_triage_requires_auth(self, client: AsyncClient) -> None:
		response = await client.post("/api/chatbot/")

		assert response.status_code == 403

	@pytest.mark.asyncio
	async def test_create_triage_success_and_persists_attendance(
		self,
		client: AsyncClient,
		auth: AuthActions,
		mongo_db_conn: AsyncIOMotorDatabase[dict[str, Any]],
	) -> None:
		tokens = await auth.register_and_login(
			email="chatbot_create_triage@test.com",
			username="chatbotcreatetriage",
		)
		user = await auth.me(tokens["access_token"])

		response = await client.post(
			"/api/chatbot/",
			headers=auth.auth_headers(tokens["access_token"]),
		)

		assert response.status_code == 201
		body = response.json()
		assert body["meta"]["success"] is True
		triage_id = body["data"]["triage_id"]
		assert triage_id
		assert body["data"]["step_id"] == "step_a"
		assert body["data"]["input"]["mode"] == "quick_replies"
		assert len(body["data"]["input"]["quick_replies"]) > 0

		stored = await mongo_db_conn["atendimentos"].find_one({"_id": ObjectId(triage_id)})
		assert stored is not None
		assert str(stored["_id"]) == triage_id
		assert stored["status"] == "opened"
		assert stored["end_date"] is None
		assert len(stored["triage"]) == 1
		assert stored["triage"][0]["step"] == "A"
		assert stored["result"] is None
		assert stored["evaluation"] is None
		assert stored["client"]["id"] == str(user.id)
		assert stored["client"]["email"] == user.email

	@pytest.mark.asyncio
	async def test_webhook_with_existing_triage_updates_flow(
		self,
		client: AsyncClient,
		auth: AuthActions,
		mongo_db_conn: AsyncIOMotorDatabase[dict[str, Any]],
	) -> None:
		tokens = await auth.register_and_login(
			email="chatbot_webhook_existing@test.com",
			username="chatbotwebhookexisting",
		)

		create_response = await client.post(
			"/api/chatbot/",
			headers=auth.auth_headers(tokens["access_token"]),
		)
		triage_id = create_response.json()["data"]["triage_id"]

		response = await client.post(
			"/api/chatbot/webhook",
			json={
				"triage_id": triage_id,
				"step_id": "step_a",
			},
		)

		assert response.status_code == 200
		body = response.json()
		assert body["data"]["triage_id"] == triage_id
		assert body["data"]["step_id"] == "step_a"
		assert body["data"]["input"]["mode"] == "quick_replies"
		assert len(body["data"]["input"]["quick_replies"]) > 0

		stored = await mongo_db_conn["atendimentos"].find_one({"_id": ObjectId(triage_id)})
		assert stored is not None
		assert len(stored["triage"]) == 1
		assert stored["triage"][0]["step"] == "A"
		assert stored["triage"][0]["answer_text"] is None
		assert stored["triage"][0]["answer_value"] is None

	@pytest.mark.asyncio
	async def test_webhook_unknown_triage_without_client_payload_returns_422(
		self,
		client: AsyncClient,
	) -> None:
		response = await client.post(
			"/api/chatbot/webhook",
			json={
				"triage_id": str(ObjectId()),
				"step_id": "step_a",
			},
		)

		assert response.status_code == 422
		assert "triage_id was not found" in response.json()["detail"]

	@pytest.mark.asyncio
	async def test_webhook_unknown_triage_with_client_payload_bootstraps_attendance(
		self,
		client: AsyncClient,
		mongo_db_conn: AsyncIOMotorDatabase[dict[str, Any]],
	) -> None:
		triage_id = str(ObjectId())
		client_id = uuid4()

		response = await client.post(
			"/api/chatbot/webhook",
			json={
				"triage_id": triage_id,
				"step_id": "step_a",
				"client_id": str(client_id),
				"client_name": "Joao Silva",
				"client_email": "joao@tech.com",
			},
		)

		assert response.status_code == 200
		body = response.json()
		assert body["data"]["triage_id"] == triage_id
		assert body["data"]["step_id"] == "step_a"

		stored = await mongo_db_conn["atendimentos"].find_one({"_id": ObjectId(triage_id)})
		assert stored is not None
		assert stored["client"]["id"] == str(client_id)
		assert stored["client"]["name"] == "Joao Silva"
		assert stored["client"]["email"] == "joao@tech.com"
		assert len(stored["triage"]) == 1
		assert stored["triage"][0]["step"] == "A"

	@pytest.mark.asyncio
	async def test_webhook_rejects_both_answer_text_and_answer_value(
		self,
		client: AsyncClient,
	) -> None:
		response = await client.post(
			"/api/chatbot/webhook",
			json={
				"triage_id": str(ObjectId()),
				"step_id": "step_a",
				"answer_text": "text",
				"answer_value": "1",
				"client_id": str(uuid4()),
				"client_name": "Joao Silva",
				"client_email": "joao@tech.com",
			},
		)

		assert response.status_code == 422
		assert response.json()["detail"] == "Request validation failed"

	@pytest.mark.asyncio
	async def test_get_attendance_not_found_raises_404(
		self,
		client: AsyncClient,
		auth: AuthActions,
	) -> None:
		tokens = await auth.register_and_login(
			email="chatbot_get_notfound@test.com",
			username="chatbotgetnotfound",
		)
		fake_id = str(ObjectId())

		response = await client.get(
			f"/api/chatbot/{fake_id}",
			headers=auth.auth_headers(tokens["access_token"]),
		)

		assert response.status_code == 404
		body = response.json()
		assert body["title"] == "Attendance Not Found"
		assert fake_id in body["detail"]

	@pytest.mark.asyncio
	async def test_set_evaluation_attendance_not_found_raises_404(
		self,
		client: AsyncClient,
		auth: AuthActions,
	) -> None:
		tokens = await auth.register_and_login(
			email="chatbot_eval_notfound@test.com",
			username="chatbotevalnotfound",
		)
		fake_id = str(ObjectId())

		response = await client.post(
			f"/api/chatbot/{fake_id}/evaluation",
			headers=auth.auth_headers(tokens["access_token"]),
			json={"rating": 5},
		)

		assert response.status_code == 404
		body = response.json()
		assert body["title"] == "Attendance Not Found"
		assert fake_id in body["detail"]

	@pytest.mark.asyncio
	async def test_set_evaluation_on_open_attendance_raises_409(
		self,
		client: AsyncClient,
		auth: AuthActions,
	) -> None:
		tokens = await auth.register_and_login(
			email="chatbot_eval_notfinished@test.com",
			username="chatbotevalnotfinished",
		)
		create_response = await client.post(
			"/api/chatbot/",
			headers=auth.auth_headers(tokens["access_token"]),
		)
		triage_id = create_response.json()["data"]["triage_id"]

		response = await client.post(
			f"/api/chatbot/{triage_id}/evaluation",
			headers=auth.auth_headers(tokens["access_token"]),
			json={"rating": 5},
		)

		assert response.status_code == 409
		body = response.json()
		assert body["title"] == "Attendance Not Finished"

	@pytest.mark.asyncio
	async def test_set_evaluation_already_evaluated_raises_409(
		self,
		client: AsyncClient,
		auth: AuthActions,
		mongo_db_conn: AsyncIOMotorDatabase[dict[str, Any]],
	) -> None:
		tokens = await auth.register_and_login(
			email="chatbot_eval_duplicate@test.com",
			username="chatbotevalduplicate",
		)
		triage_id = str(ObjectId())
		await mongo_db_conn["atendimentos"].insert_one({
			"_id": ObjectId(triage_id),
			"status": "finished",
			"evaluation": {"rating": 4},
			"start_date": "2026-01-01T00:00:00",
			"end_date": "2026-01-01T01:00:00",
			"triage": [],
			"result": {"type": "Resolved", "closure_message": "Resolved."},
			"client": {"id": str(uuid4()), "name": "Test User", "email": "test@test.com"},
		})

		response = await client.post(
			f"/api/chatbot/{triage_id}/evaluation",
			headers=auth.auth_headers(tokens["access_token"]),
			json={"rating": 5},
		)

		assert response.status_code == 409
		body = response.json()
		assert body["title"] == "Attendance Already Evaluated"
