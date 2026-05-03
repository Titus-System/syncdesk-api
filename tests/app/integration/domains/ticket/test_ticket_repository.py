from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from beanie import PydanticObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.domains.ticket.models import (
    Ticket,
    TicketClient,
    TicketComment,
    TicketCompany,
    TicketCriticality,
    TicketHistory,
    TicketStatus,
    TicketType,
)
from app.domains.ticket.repositories import TicketRepository


@pytest_asyncio.fixture(autouse=True)
async def _cleanup_tickets() -> AsyncGenerator[None, None]:
    await Ticket.delete_all()
    yield
    await Ticket.delete_all()


@pytest.fixture
def repository(
    mongo_db_conn: AsyncIOMotorDatabase[dict[str, Any]],
) -> TicketRepository:
    return TicketRepository(mongo_db_conn)


def _make_ticket(
    *,
    description: str = "Erro ao emitir boleto",
    comments: list[TicketComment] | None = None,
    client_id: UUID | None = None,
    company_id: UUID | None = None,
    agent_history: list[TicketHistory] | None = None,
) -> Ticket:
    cid = client_id or uuid4()
    coid = company_id or uuid4()
    return Ticket(
        triage_id=PydanticObjectId(),
        type=TicketType.ISSUE,
        criticality=TicketCriticality.HIGH,
        product="Sistema",
        status=TicketStatus.AWAITING_ASSIGNMENT,
        creation_date=datetime.now(UTC),
        description=description,
        chat_ids=[],
        agent_history=agent_history or [],
        client=TicketClient(
            id=cid,
            name="Cliente",
            email="cliente@test.com",
            company=TicketCompany(id=coid, name="Empresa"),
        ),
        comments=comments or [],
    )


def _make_comment(text: str) -> TicketComment:
    return TicketComment(
        author="agente",
        text=text,
        date=datetime.now(UTC),
        internal=False,
    )


def _make_history(agent_id: UUID, level: str = "N1") -> TicketHistory:
    return TicketHistory(
        agent_id=agent_id,
        name="Agente",
        level=level,
        assignment_date=datetime.now(UTC),
        exit_date=None,
        transfer_reason=None,
    )


class TestSearchTicketByClient:
    @pytest.mark.asyncio
    async def test_matches_text_in_description(
        self, repository: TicketRepository
    ) -> None:
        client_id = uuid4()
        await repository.create_ticket(
            _make_ticket(description="Erro crítico no boleto", client_id=client_id)
        )
        await repository.create_ticket(
            _make_ticket(description="Configuração de SMTP", client_id=client_id)
        )

        result = await repository.search_ticket("boleto", client_id=client_id)

        assert result is not None
        assert len(result) == 1
        assert result[0].description == "Erro crítico no boleto"

    @pytest.mark.asyncio
    async def test_matches_text_in_comments(
        self, repository: TicketRepository
    ) -> None:
        client_id = uuid4()
        await repository.create_ticket(
            _make_ticket(
                description="Pedido genérico",
                comments=[_make_comment("Cliente relatou queda na fatura")],
                client_id=client_id,
            )
        )

        result = await repository.search_ticket("queda", client_id=client_id)

        assert result is not None
        assert len(result) == 1
        assert result[0].comments[0].text == "Cliente relatou queda na fatura"

    @pytest.mark.asyncio
    async def test_search_is_case_insensitive(
        self, repository: TicketRepository
    ) -> None:
        client_id = uuid4()
        await repository.create_ticket(
            _make_ticket(description="Falha CRÍTICA na importação", client_id=client_id)
        )

        result = await repository.search_ticket("crítica", client_id=client_id)

        assert result is not None
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_excludes_tickets_from_other_clients(
        self, repository: TicketRepository
    ) -> None:
        target_client = uuid4()
        other_client = uuid4()
        await repository.create_ticket(
            _make_ticket(description="boleto vencido", client_id=target_client)
        )
        await repository.create_ticket(
            _make_ticket(description="boleto duplicado", client_id=other_client)
        )

        result = await repository.search_ticket("boleto", client_id=target_client)

        assert result is not None
        assert len(result) == 1
        assert result[0].client.id == target_client

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_matches(
        self, repository: TicketRepository
    ) -> None:
        client_id = uuid4()
        await repository.create_ticket(
            _make_ticket(description="cobrança incorreta", client_id=client_id)
        )

        result = await repository.search_ticket("inexistente", client_id=client_id)

        assert result == []


class TestSearchTicketByAgent:
    @pytest.mark.asyncio
    async def test_filters_by_agent_history(
        self, repository: TicketRepository
    ) -> None:
        target_agent = uuid4()
        another_agent = uuid4()
        await repository.create_ticket(
            _make_ticket(
                description="cobrança incorreta",
                agent_history=[_make_history(target_agent)],
            )
        )
        await repository.create_ticket(
            _make_ticket(
                description="cobrança duplicada",
                agent_history=[_make_history(another_agent)],
            )
        )

        result = await repository.search_ticket("cobrança", agent_id=target_agent)

        assert result is not None
        assert len(result) == 1
        assert any(h.agent_id == target_agent for h in result[0].agent_history)

    @pytest.mark.asyncio
    async def test_matches_when_agent_appears_anywhere_in_history(
        self, repository: TicketRepository
    ) -> None:
        first_agent = uuid4()
        second_agent = uuid4()
        history = [
            _make_history(first_agent),
            _make_history(second_agent, level="N2"),
        ]
        await repository.create_ticket(
            _make_ticket(description="acesso negado", agent_history=history)
        )

        result_first = await repository.search_ticket("acesso", agent_id=first_agent)
        result_second = await repository.search_ticket("acesso", agent_id=second_agent)

        assert result_first is not None and len(result_first) == 1
        assert result_second is not None and len(result_second) == 1


class TestSearchTicketByCompany:
    @pytest.mark.asyncio
    async def test_filters_by_client_company_id(
        self, repository: TicketRepository
    ) -> None:
        target_company = uuid4()
        await repository.create_ticket(
            _make_ticket(description="acesso negado", company_id=target_company)
        )
        await repository.create_ticket(
            _make_ticket(description="acesso negado", company_id=uuid4())
        )

        result = await repository.search_ticket("acesso", company_id=target_company)

        assert result is not None
        assert len(result) == 1
        assert result[0].client.company.id == target_company


class TestSearchTicketEdgeCases:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_scope_provided(
        self, repository: TicketRepository
    ) -> None:
        await repository.create_ticket(_make_ticket(description="qualquer"))

        result = await repository.search_ticket("qualquer")

        assert result == []

    @pytest.mark.asyncio
    async def test_special_regex_characters_are_escaped(
        self, repository: TicketRepository
    ) -> None:
        client_id = uuid4()
        await repository.create_ticket(
            _make_ticket(description="Saldo (negativo) detectado", client_id=client_id)
        )
        await repository.create_ticket(
            _make_ticket(description="saldo positivo", client_id=client_id)
        )

        result = await repository.search_ticket("(negativo)", client_id=client_id)

        assert result is not None
        assert len(result) == 1
        assert "(negativo)" in result[0].description

    @pytest.mark.asyncio
    async def test_scope_priority_uses_first_provided(
        self, repository: TicketRepository
    ) -> None:
        target_client = uuid4()
        unrelated_agent = uuid4()
        await repository.create_ticket(
            _make_ticket(description="cobrança", client_id=target_client)
        )
        await repository.create_ticket(
            _make_ticket(
                description="cobrança",
                agent_history=[_make_history(unrelated_agent)],
            )
        )

        result = await repository.search_ticket(
            "cobrança",
            client_id=target_client,
            agent_id=unrelated_agent,
        )

        assert result is not None
        assert len(result) == 1
        assert result[0].client.id == target_client
