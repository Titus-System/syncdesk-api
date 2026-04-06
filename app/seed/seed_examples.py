"""
Seed example data for a professional SyncDesk demo.

Creates:
  - Postgres: agent and client users with proper roles
  - MongoDB:  attendances (triage sessions), tickets, and conversations
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import PasswordSecurity
from app.domains.auth.models import Role, User, user_roles

# ---------------------------------------------------------------------------
# Fixed UUIDs so relationships stay consistent across seeds
# ---------------------------------------------------------------------------
AGENT_IDS: dict[str, UUID] = {
    "lucas": UUID("a1000000-0000-0000-0000-000000000001"),
    "camila": UUID("a1000000-0000-0000-0000-000000000002"),
    "rafael": UUID("a1000000-0000-0000-0000-000000000003"),
}

CLIENT_IDS: dict[str, UUID] = {
    "marcos": UUID("c1000000-0000-0000-0000-000000000001"),
    "ana": UUID("c1000000-0000-0000-0000-000000000002"),
    "fernanda": UUID("c1000000-0000-0000-0000-000000000003"),
    "ricardo": UUID("c1000000-0000-0000-0000-000000000004"),
}

COMPANY_IDS: dict[str, UUID] = {
    "techsol": UUID("d1000000-0000-0000-0000-000000000001"),
    "dataflow": UUID("d1000000-0000-0000-0000-000000000002"),
}

# Fixed ObjectIds for MongoDB documents
TRIAGE_IDS = [ObjectId() for _ in range(6)]
TICKET_IDS = [ObjectId() for _ in range(6)]
CONVERSATION_IDS = [ObjectId() for _ in range(6)]

NOW = datetime(2026, 4, 4, 14, 0, 0, tzinfo=UTC)


# ===== POSTGRES =====

async def seed_example_users(session: AsyncSession) -> None:
    """Seed agent and client users."""
    pw = PasswordSecurity()
    default_password = "Demo@2026!"

    users_payload: list[dict[str, Any]] = [
        # Agents
        {
            "id": AGENT_IDS["lucas"],
            "email": "lucas.silva@syncdesk.pro",
            "password_hash": pw.generate_password_hash(default_password),
            "username": "lucas.silva",
            "name": "Lucas Silva",
            "must_change_password": False,
            "must_accept_terms": False,
        },
        {
            "id": AGENT_IDS["camila"],
            "email": "camila.santos@syncdesk.pro",
            "password_hash": pw.generate_password_hash(default_password),
            "username": "camila.santos",
            "name": "Camila Santos",
            "must_change_password": False,
            "must_accept_terms": False,
        },
        {
            "id": AGENT_IDS["rafael"],
            "email": "rafael.costa@syncdesk.pro",
            "password_hash": pw.generate_password_hash(default_password),
            "username": "rafael.costa",
            "name": "Rafael Costa",
            "must_change_password": False,
            "must_accept_terms": False,
        },
        # Clients
        {
            "id": CLIENT_IDS["marcos"],
            "email": "marcos.oliveira@techsol.com.br",
            "password_hash": pw.generate_password_hash(default_password),
            "username": "marcos.oliveira",
            "name": "Marcos Oliveira",
            "must_change_password": False,
            "must_accept_terms": False,
        },
        {
            "id": CLIENT_IDS["ana"],
            "email": "ana.pereira@techsol.com.br",
            "password_hash": pw.generate_password_hash(default_password),
            "username": "ana.pereira",
            "name": "Ana Pereira",
            "must_change_password": False,
            "must_accept_terms": False,
        },
        {
            "id": CLIENT_IDS["fernanda"],
            "email": "fernanda.lima@dataflow.io",
            "password_hash": pw.generate_password_hash(default_password),
            "username": "fernanda.lima",
            "name": "Fernanda Lima",
            "must_change_password": False,
            "must_accept_terms": False,
        },
        {
            "id": CLIENT_IDS["ricardo"],
            "email": "ricardo.mendes@dataflow.io",
            "password_hash": pw.generate_password_hash(default_password),
            "username": "ricardo.mendes",
            "name": "Ricardo Mendes",
            "must_change_password": False,
            "must_accept_terms": False,
        },
    ]

    insert_stmt = pg_insert(User).values(users_payload).on_conflict_do_nothing()
    await session.execute(insert_stmt)


async def seed_example_user_roles(session: AsyncSession) -> None:
    """Assign agent and client roles to seeded users."""
    role_map: dict[str, list[UUID]] = {
        "agent": list(AGENT_IDS.values()),
        "client": list(CLIENT_IDS.values()),
    }

    for role_name, user_ids in role_map.items():
        res = await session.execute(select(Role.id).where(Role.name == role_name))
        role_id = res.scalar_one_or_none()
        if role_id is None:
            continue

        values = [{"user_id": uid, "role_id": role_id} for uid in user_ids]
        stmt = pg_insert(user_roles).values(values).on_conflict_do_nothing()
        await session.execute(stmt)


# ===== MONGODB — helpers =====

def _client_doc(name: str, email: str, client_id: UUID, company_name: str, company_id: UUID) -> dict[str, Any]:
    return {
        "id": str(client_id),
        "name": name,
        "email": email,
        "company": {"id": str(company_id), "name": company_name},
    }


CLIENTS_DOC = {
    "marcos": _client_doc("Marcos Oliveira", "marcos.oliveira@techsol.com.br",
                          CLIENT_IDS["marcos"], "TechSol Sistemas", COMPANY_IDS["techsol"]),
    "ana": _client_doc("Ana Pereira", "ana.pereira@techsol.com.br",
                       CLIENT_IDS["ana"], "TechSol Sistemas", COMPANY_IDS["techsol"]),
    "fernanda": _client_doc("Fernanda Lima", "fernanda.lima@dataflow.io",
                            CLIENT_IDS["fernanda"], "DataFlow Analytics", COMPANY_IDS["dataflow"]),
    "ricardo": _client_doc("Ricardo Mendes", "ricardo.mendes@dataflow.io",
                           CLIENT_IDS["ricardo"], "DataFlow Analytics", COMPANY_IDS["dataflow"]),
}


# ===== MONGODB — attendances (triage sessions) =====

def _build_attendances() -> list[dict[str, Any]]:
    """Build 6 attendance documents representing completed triage flows."""
    return [
        # 0 — Marcos: Product A → system failure → ticket created
        {
            "_id": TRIAGE_IDS[0],
            "status": "finished",
            "start_date": (NOW - timedelta(days=3, hours=2)).isoformat(),
            "end_date": (NOW - timedelta(days=3, hours=1, minutes=50)).isoformat(),
            "client": CLIENTS_DOC["marcos"],
            "result": {"type": "ticket", "closure_message": "Ticket criado com sucesso."},
            "evaluation": {"rating": 4},
            "triage": [
                {"step": "A", "question": "Selecione a opção que indica sobre o que você quer falar hoje:",
                 "answer_text": None, "answer_value": "1", "type": "quick_replies"},
                {"step": "B", "question": "Como posso te ajudar hoje em relação ao Produto escolhido?",
                 "answer_text": None, "answer_value": "1", "type": "quick_replies"},
                {"step": "F", "question": "Por favor, explique da maneira mais detalhada possível o seu problema.",
                 "answer_text": "O módulo de relatórios do Produto A está retornando erro 500 ao exportar para PDF. Acontece com qualquer relatório desde a atualização de ontem.",
                 "answer_value": None, "type": "free_text"},
                {"step": "E", "question": "Aguarde, sua solicitação foi criada.",
                 "answer_text": None, "answer_value": None, "type": "quick_replies"},
            ],
        },
        # 1 — Ana: Product B → new feature request → ticket created
        {
            "_id": TRIAGE_IDS[1],
            "status": "finished",
            "start_date": (NOW - timedelta(days=2, hours=5)).isoformat(),
            "end_date": (NOW - timedelta(days=2, hours=4, minutes=45)).isoformat(),
            "client": CLIENTS_DOC["ana"],
            "result": {"type": "ticket", "closure_message": "Ticket criado com sucesso."},
            "evaluation": {"rating": 5},
            "triage": [
                {"step": "A", "question": "Selecione a opção que indica sobre o que você quer falar hoje:",
                 "answer_text": None, "answer_value": "2", "type": "quick_replies"},
                {"step": "B", "question": "Como posso te ajudar hoje em relação ao Produto escolhido?",
                 "answer_text": None, "answer_value": "2", "type": "quick_replies"},
                {"step": "G", "question": "Por favor, explique da maneira mais detalhada possível a nova funcionalidade.",
                 "answer_text": "Gostaria de ter a opção de exportar os dashboards do Produto B em formato PowerPoint, além do PDF que já existe. Nosso time de vendas precisa incluir os gráficos em apresentações.",
                 "answer_value": None, "type": "free_text"},
                {"step": "E", "question": "Aguarde, sua solicitação foi criada.",
                 "answer_text": None, "answer_value": None, "type": "quick_replies"},
            ],
        },
        # 2 — Fernanda: access request → ticket created
        {
            "_id": TRIAGE_IDS[2],
            "status": "finished",
            "start_date": (NOW - timedelta(days=1, hours=8)).isoformat(),
            "end_date": (NOW - timedelta(days=1, hours=7, minutes=52)).isoformat(),
            "client": CLIENTS_DOC["fernanda"],
            "result": {"type": "ticket", "closure_message": "Ticket criado com sucesso."},
            "evaluation": {"rating": 5},
            "triage": [
                {"step": "A", "question": "Selecione a opção que indica sobre o que você quer falar hoje:",
                 "answer_text": None, "answer_value": "5", "type": "quick_replies"},
                {"step": "D", "question": "Por favor, envie uma mensagem respondendo as seguintes perguntas...",
                 "answer_text": "1- Novo perfil. 2- joao.martins@dataflow.io, DataFlow Analytics. 3- Novo colaborador no time de dados. 4- Produto A e Produto C.",
                 "answer_value": None, "type": "free_text"},
                {"step": "E", "question": "Aguarde, sua solicitação foi criada.",
                 "answer_text": None, "answer_value": None, "type": "quick_replies"},
            ],
        },
        # 3 — Ricardo: Product C → system failure → ticket created
        {
            "_id": TRIAGE_IDS[3],
            "status": "finished",
            "start_date": (NOW - timedelta(hours=6)).isoformat(),
            "end_date": (NOW - timedelta(hours=5, minutes=48)).isoformat(),
            "client": CLIENTS_DOC["ricardo"],
            "result": {"type": "ticket", "closure_message": "Ticket criado com sucesso."},
            "evaluation": None,
            "triage": [
                {"step": "A", "question": "Selecione a opção que indica sobre o que você quer falar hoje:",
                 "answer_text": None, "answer_value": "3", "type": "quick_replies"},
                {"step": "B", "question": "Como posso te ajudar hoje em relação ao Produto escolhido?",
                 "answer_text": None, "answer_value": "1", "type": "quick_replies"},
                {"step": "F", "question": "Por favor, explique da maneira mais detalhada possível o seu problema.",
                 "answer_text": "O login do Produto C está falhando intermitentemente. Alguns usuários do nosso time conseguem acessar e outros recebem 'credenciais inválidas' mesmo com senha correta. Parece estar relacionado ao servidor de autenticação.",
                 "answer_value": None, "type": "free_text"},
                {"step": "E", "question": "Aguarde, sua solicitação foi criada.",
                 "answer_text": None, "answer_value": None, "type": "quick_replies"},
            ],
        },
        # 4 — Marcos: doubt about deadlines → resolved without ticket
        {
            "_id": TRIAGE_IDS[4],
            "status": "finished",
            "start_date": (NOW - timedelta(days=5)).isoformat(),
            "end_date": (NOW - timedelta(days=5) + timedelta(minutes=3)).isoformat(),
            "client": CLIENTS_DOC["marcos"],
            "result": None,
            "evaluation": {"rating": 3},
            "triage": [
                {"step": "A", "question": "Selecione a opção que indica sobre o que você quer falar hoje:",
                 "answer_text": None, "answer_value": "4", "type": "quick_replies"},
                {"step": "C", "question": "Selecione, por favor, qual a sua dúvida:",
                 "answer_text": None, "answer_value": "1", "type": "quick_replies"},
                {"step": "X", "question": "Verifiquei e esses são os seguintes prazos...",
                 "answer_text": None, "answer_value": "2", "type": "quick_replies"},
                {"step": "I", "question": "Atendimento finalizado!",
                 "answer_text": None, "answer_value": None, "type": "quick_replies"},
            ],
        },
        # 5 — Ana: Product A → system failure → ticket (most recent)
        {
            "_id": TRIAGE_IDS[5],
            "status": "finished",
            "start_date": (NOW - timedelta(hours=2)).isoformat(),
            "end_date": (NOW - timedelta(hours=1, minutes=50)).isoformat(),
            "client": CLIENTS_DOC["ana"],
            "result": {"type": "ticket", "closure_message": "Ticket criado com sucesso."},
            "evaluation": None,
            "triage": [
                {"step": "A", "question": "Selecione a opção que indica sobre o que você quer falar hoje:",
                 "answer_text": None, "answer_value": "1", "type": "quick_replies"},
                {"step": "B", "question": "Como posso te ajudar hoje em relação ao Produto escolhido?",
                 "answer_text": None, "answer_value": "1", "type": "quick_replies"},
                {"step": "F", "question": "Por favor, explique da maneira mais detalhada possível o seu problema.",
                 "answer_text": "A integração com a API de pagamentos no Produto A parou de funcionar. As transações ficam pendentes e não são processadas. Urgente pois está impactando o faturamento.",
                 "answer_value": None, "type": "free_text"},
                {"step": "E", "question": "Aguarde, sua solicitação foi criada.",
                 "answer_text": None, "answer_value": None, "type": "quick_replies"},
            ],
        },
    ]


# ===== MONGODB — tickets =====

def _build_tickets() -> list[dict[str, Any]]:
    """Build 5 tickets (indices 0-3 and 5 from attendances; #4 had no ticket)."""
    return [
        # Ticket 0 — Marcos / Product A issue / in_progress (assigned to Lucas)
        {
            "_id": TICKET_IDS[0],
            "triage_id": TRIAGE_IDS[0],
            "type": "issue",
            "criticality": "high",
            "product": "Product A",
            "status": "in_progress",
            "creation_date": (NOW - timedelta(days=3, hours=1, minutes=50)).isoformat(),
            "description": "O módulo de relatórios do Produto A está retornando erro 500 ao exportar para PDF. Acontece com qualquer relatório desde a atualização de ontem.",
            "chat_ids": [str(CONVERSATION_IDS[0])],
            "agent_history": [
                {
                    "agent_id": str(AGENT_IDS["lucas"]),
                    "name": "Lucas Silva",
                    "level": "N1",
                    "assignment_date": (NOW - timedelta(days=3, hours=1, minutes=45)).isoformat(),
                    "exit_date": (NOW - timedelta(days=3, hours=1, minutes=45)).isoformat(),
                    "transfer_reason": "Atribuição inicial",
                },
            ],
            "client": CLIENTS_DOC["marcos"],
            "comments": [
                {
                    "comment_id": str(uuid4()),
                    "author": "Lucas Silva",
                    "text": "Consegui reproduzir o erro. O problema está na lib de geração de PDF após a atualização da dependência. Trabalhando na correção.",
                    "date": (NOW - timedelta(days=2, hours=3)).isoformat(),
                    "internal": True,
                },
            ],
        },
        # Ticket 1 — Ana / Product B new feature / open
        {
            "_id": TICKET_IDS[1],
            "triage_id": TRIAGE_IDS[1],
            "type": "new_feature",
            "criticality": "low",
            "product": "Product B",
            "status": "open",
            "creation_date": (NOW - timedelta(days=2, hours=4, minutes=45)).isoformat(),
            "description": "Gostaria de ter a opção de exportar os dashboards do Produto B em formato PowerPoint, além do PDF que já existe. Nosso time de vendas precisa incluir os gráficos em apresentações.",
            "chat_ids": [],
            "agent_history": [],
            "client": CLIENTS_DOC["ana"],
            "comments": [],
        },
        # Ticket 2 — Fernanda / access request / waiting_for_provider
        {
            "_id": TICKET_IDS[2],
            "triage_id": TRIAGE_IDS[2],
            "type": "access",
            "criticality": "medium",
            "product": "N/A",
            "status": "waiting_for_provider",
            "creation_date": (NOW - timedelta(days=1, hours=7, minutes=52)).isoformat(),
            "description": "1- Novo perfil. 2- joao.martins@dataflow.io, DataFlow Analytics. 3- Novo colaborador no time de dados. 4- Produto A e Produto C.",
            "chat_ids": [str(CONVERSATION_IDS[2])],
            "agent_history": [
                {
                    "agent_id": str(AGENT_IDS["camila"]),
                    "name": "Camila Santos",
                    "level": "N1",
                    "assignment_date": (NOW - timedelta(days=1, hours=7, minutes=40)).isoformat(),
                    "exit_date": (NOW - timedelta(days=1, hours=7, minutes=40)).isoformat(),
                    "transfer_reason": "Atribuição inicial",
                },
            ],
            "client": CLIENTS_DOC["fernanda"],
            "comments": [
                {
                    "comment_id": str(uuid4()),
                    "author": "Camila Santos",
                    "text": "Solicitação de criação de perfil encaminhada ao time de infraestrutura. Aguardando liberação.",
                    "date": (NOW - timedelta(days=1, hours=6)).isoformat(),
                    "internal": True,
                },
            ],
        },
        # Ticket 3 — Ricardo / Product C issue / in_progress (escalated)
        {
            "_id": TICKET_IDS[3],
            "triage_id": TRIAGE_IDS[3],
            "type": "issue",
            "criticality": "high",
            "product": "Product C",
            "status": "in_progress",
            "creation_date": (NOW - timedelta(hours=5, minutes=48)).isoformat(),
            "description": "O login do Produto C está falhando intermitentemente. Alguns usuários do nosso time conseguem acessar e outros recebem 'credenciais inválidas' mesmo com senha correta. Parece estar relacionado ao servidor de autenticação.",
            "chat_ids": [str(CONVERSATION_IDS[3])],
            "agent_history": [
                {
                    "agent_id": str(AGENT_IDS["camila"]),
                    "name": "Camila Santos",
                    "level": "N1",
                    "assignment_date": (NOW - timedelta(hours=5, minutes=40)).isoformat(),
                    "exit_date": (NOW - timedelta(hours=4)).isoformat(),
                    "transfer_reason": "Atribuição inicial",
                },
                {
                    "agent_id": str(AGENT_IDS["rafael"]),
                    "name": "Rafael Costa",
                    "level": "N2",
                    "assignment_date": (NOW - timedelta(hours=4)).isoformat(),
                    "exit_date": (NOW - timedelta(hours=4)).isoformat(),
                    "transfer_reason": "Escalado para N2 — problema de infraestrutura de autenticação",
                },
            ],
            "client": CLIENTS_DOC["ricardo"],
            "comments": [
                {
                    "comment_id": str(uuid4()),
                    "author": "Camila Santos",
                    "text": "Confirmado o problema intermitente de login. Parece ser do lado do auth server. Escalando para N2.",
                    "date": (NOW - timedelta(hours=4, minutes=10)).isoformat(),
                    "internal": True,
                },
                {
                    "comment_id": str(uuid4()),
                    "author": "Rafael Costa",
                    "text": "Identificado: o balanceador de carga está direcionando parte das requisições para uma instância do auth server com cache expirado. Reiniciando a instância.",
                    "date": (NOW - timedelta(hours=3)).isoformat(),
                    "internal": True,
                },
            ],
        },
        # Ticket 4 (index 5 from attendances) — Ana / Product A issue / open (newest)
        {
            "_id": TICKET_IDS[5],
            "triage_id": TRIAGE_IDS[5],
            "type": "issue",
            "criticality": "high",
            "product": "Product A",
            "status": "open",
            "creation_date": (NOW - timedelta(hours=1, minutes=50)).isoformat(),
            "description": "A integração com a API de pagamentos no Produto A parou de funcionar. As transações ficam pendentes e não são processadas. Urgente pois está impactando o faturamento.",
            "chat_ids": [],
            "agent_history": [],
            "client": CLIENTS_DOC["ana"],
            "comments": [],
        },
    ]


# ===== MONGODB — conversations =====

def _build_conversations() -> list[dict[str, Any]]:
    """Build conversations linked to tickets that have chat_ids."""
    return [
        # Conversation 0 — Ticket 0 (Marcos ↔ Lucas, Product A PDF export)
        {
            "_id": CONVERSATION_IDS[0],
            "ticket_id": TICKET_IDS[0],
            "agent_id": str(AGENT_IDS["lucas"]),
            "client_id": str(CLIENT_IDS["marcos"]),
            "sequential_index": 0,
            "parent_id": None,
            "children_ids": [],
            "started_at": (NOW - timedelta(days=3, hours=1, minutes=40)).isoformat(),
            "finished_at": None,
            "messages": [
                {
                    "id": str(uuid4()),
                    "conversation_id": str(CONVERSATION_IDS[0]),
                    "sender_id": "System",
                    "timestamp": (NOW - timedelta(days=3, hours=1, minutes=40)).isoformat(),
                    "type": "text",
                    "content": "Conversa iniciada. Agente Lucas Silva atribuído ao chamado.",
                },
                {
                    "id": str(uuid4()),
                    "conversation_id": str(CONVERSATION_IDS[0]),
                    "sender_id": str(AGENT_IDS["lucas"]),
                    "timestamp": (NOW - timedelta(days=3, hours=1, minutes=38)).isoformat(),
                    "type": "text",
                    "content": "Olá Marcos! Sou o Lucas e vou cuidar do seu chamado sobre o erro no módulo de relatórios. Você consegue me dizer em qual navegador está tentando exportar?",
                },
                {
                    "id": str(uuid4()),
                    "conversation_id": str(CONVERSATION_IDS[0]),
                    "sender_id": str(CLIENT_IDS["marcos"]),
                    "timestamp": (NOW - timedelta(days=3, hours=1, minutes=30)).isoformat(),
                    "type": "text",
                    "content": "Oi Lucas! Testei no Chrome e no Firefox, mesmo erro nos dois. O relatório começa a gerar mas retorna erro 500 antes de completar.",
                },
                {
                    "id": str(uuid4()),
                    "conversation_id": str(CONVERSATION_IDS[0]),
                    "sender_id": str(AGENT_IDS["lucas"]),
                    "timestamp": (NOW - timedelta(days=3, hours=1, minutes=25)).isoformat(),
                    "type": "text",
                    "content": "Entendi. Consegui reproduzir aqui no ambiente de testes. Parece que a atualização de ontem quebrou a dependência de geração de PDF. Vou trabalhar na correção e te mantenho informado.",
                },
                {
                    "id": str(uuid4()),
                    "conversation_id": str(CONVERSATION_IDS[0]),
                    "sender_id": str(CLIENT_IDS["marcos"]),
                    "timestamp": (NOW - timedelta(days=3, hours=1, minutes=20)).isoformat(),
                    "type": "text",
                    "content": "Perfeito, obrigado! Enquanto isso tem alguma alternativa para eu conseguir os dados?",
                },
                {
                    "id": str(uuid4()),
                    "conversation_id": str(CONVERSATION_IDS[0]),
                    "sender_id": str(AGENT_IDS["lucas"]),
                    "timestamp": (NOW - timedelta(days=3, hours=1, minutes=15)).isoformat(),
                    "type": "text",
                    "content": "Sim! Você pode exportar em formato CSV pelo menu Relatórios > Exportar > CSV. Essa opção não foi afetada pela atualização.",
                },
            ],
        },
        # Conversation 2 — Ticket 2 (Fernanda ↔ Camila, access request)
        {
            "_id": CONVERSATION_IDS[2],
            "ticket_id": TICKET_IDS[2],
            "agent_id": str(AGENT_IDS["camila"]),
            "client_id": str(CLIENT_IDS["fernanda"]),
            "sequential_index": 0,
            "parent_id": None,
            "children_ids": [],
            "started_at": (NOW - timedelta(days=1, hours=7, minutes=35)).isoformat(),
            "finished_at": None,
            "messages": [
                {
                    "id": str(uuid4()),
                    "conversation_id": str(CONVERSATION_IDS[2]),
                    "sender_id": "System",
                    "timestamp": (NOW - timedelta(days=1, hours=7, minutes=35)).isoformat(),
                    "type": "text",
                    "content": "Conversa iniciada. Agente Camila Santos atribuída ao chamado.",
                },
                {
                    "id": str(uuid4()),
                    "conversation_id": str(CONVERSATION_IDS[2]),
                    "sender_id": str(AGENT_IDS["camila"]),
                    "timestamp": (NOW - timedelta(days=1, hours=7, minutes=30)).isoformat(),
                    "type": "text",
                    "content": "Oi Fernanda! Recebi a solicitação de acesso para o João Martins. Só preciso confirmar: ele vai precisar de perfil administrador ou usuário padrão nos produtos A e C?",
                },
                {
                    "id": str(uuid4()),
                    "conversation_id": str(CONVERSATION_IDS[2]),
                    "sender_id": str(CLIENT_IDS["fernanda"]),
                    "timestamp": (NOW - timedelta(days=1, hours=7, minutes=20)).isoformat(),
                    "type": "text",
                    "content": "Oi Camila! Perfil de usuário padrão por enquanto. Se precisar de mais permissões depois a gente solicita.",
                },
                {
                    "id": str(uuid4()),
                    "conversation_id": str(CONVERSATION_IDS[2]),
                    "sender_id": str(AGENT_IDS["camila"]),
                    "timestamp": (NOW - timedelta(days=1, hours=7, minutes=15)).isoformat(),
                    "type": "text",
                    "content": "Perfeito! Já encaminhei para o time de infraestrutura. O prazo padrão para criação de acesso é de até 24h úteis. Te aviso assim que estiver pronto!",
                },
            ],
        },
        # Conversation 3 — Ticket 3 (Ricardo ↔ Camila → Rafael, auth issue)
        {
            "_id": CONVERSATION_IDS[3],
            "ticket_id": TICKET_IDS[3],
            "agent_id": str(AGENT_IDS["rafael"]),
            "client_id": str(CLIENT_IDS["ricardo"]),
            "sequential_index": 0,
            "parent_id": None,
            "children_ids": [],
            "started_at": (NOW - timedelta(hours=5, minutes=35)).isoformat(),
            "finished_at": None,
            "messages": [
                {
                    "id": str(uuid4()),
                    "conversation_id": str(CONVERSATION_IDS[3]),
                    "sender_id": "System",
                    "timestamp": (NOW - timedelta(hours=5, minutes=35)).isoformat(),
                    "type": "text",
                    "content": "Conversa iniciada. Agente Camila Santos atribuída ao chamado.",
                },
                {
                    "id": str(uuid4()),
                    "conversation_id": str(CONVERSATION_IDS[3]),
                    "sender_id": str(AGENT_IDS["camila"]),
                    "timestamp": (NOW - timedelta(hours=5, minutes=30)).isoformat(),
                    "type": "text",
                    "content": "Olá Ricardo! Sou a Camila. Vi que vocês estão com problema intermitente de login no Produto C. Quantos usuários estão sendo afetados?",
                },
                {
                    "id": str(uuid4()),
                    "conversation_id": str(CONVERSATION_IDS[3]),
                    "sender_id": str(CLIENT_IDS["ricardo"]),
                    "timestamp": (NOW - timedelta(hours=5, minutes=22)).isoformat(),
                    "type": "text",
                    "content": "Oi Camila! Uns 5 de 12 usuários. O padrão é estranho — funciona, falha, funciona de novo. Parece aleatório.",
                },
                {
                    "id": str(uuid4()),
                    "conversation_id": str(CONVERSATION_IDS[3]),
                    "sender_id": str(AGENT_IDS["camila"]),
                    "timestamp": (NOW - timedelta(hours=5, minutes=15)).isoformat(),
                    "type": "text",
                    "content": "Esse padrão intermitente pode indicar problema de infraestrutura. Vou escalar para nosso time de nível 2 para uma análise mais profunda. O Rafael vai assumir o chamado.",
                },
                {
                    "id": str(uuid4()),
                    "conversation_id": str(CONVERSATION_IDS[3]),
                    "sender_id": "System",
                    "timestamp": (NOW - timedelta(hours=4)).isoformat(),
                    "type": "text",
                    "content": "Chamado transferido para o agente Rafael Costa (N2).",
                },
                {
                    "id": str(uuid4()),
                    "conversation_id": str(CONVERSATION_IDS[3]),
                    "sender_id": str(AGENT_IDS["rafael"]),
                    "timestamp": (NOW - timedelta(hours=3, minutes=55)).isoformat(),
                    "type": "text",
                    "content": "Oi Ricardo, aqui é o Rafael. Já estou analisando os logs do servidor de autenticação. O comportamento intermitente é consistente com um problema de balanceamento de carga que estamos investigando.",
                },
                {
                    "id": str(uuid4()),
                    "conversation_id": str(CONVERSATION_IDS[3]),
                    "sender_id": str(AGENT_IDS["rafael"]),
                    "timestamp": (NOW - timedelta(hours=3)).isoformat(),
                    "type": "text",
                    "content": "Encontrei a causa: uma das instâncias do servidor de autenticação estava com cache desatualizado. Já reiniciei a instância. Pode pedir para o time testar o login agora?",
                },
                {
                    "id": str(uuid4()),
                    "conversation_id": str(CONVERSATION_IDS[3]),
                    "sender_id": str(CLIENT_IDS["ricardo"]),
                    "timestamp": (NOW - timedelta(hours=2, minutes=45)).isoformat(),
                    "type": "text",
                    "content": "Testamos agora e está funcionando para todos! Muito obrigado pela resolução rápida, Rafael!",
                },
            ],
        },
    ]


# ===== MONGODB — seed functions =====

async def seed_example_attendances(db: AsyncIOMotorDatabase) -> None:  # type: ignore[type-arg]
    """Insert example attendance (triage) documents into MongoDB."""
    collection = db["atendimentos"]
    for doc in _build_attendances():
        await collection.replace_one({"_id": doc["_id"]}, doc, upsert=True)


async def seed_example_tickets(db: AsyncIOMotorDatabase) -> None:  # type: ignore[type-arg]
    """Insert example ticket documents into MongoDB."""
    collection = db["tickets"]
    for doc in _build_tickets():
        await collection.replace_one({"_id": doc["_id"]}, doc, upsert=True)


async def seed_example_conversations(db: AsyncIOMotorDatabase) -> None:  # type: ignore[type-arg]
    """Insert example conversation documents into MongoDB."""
    collection = db["conversations"]

    # Drop legacy index that conflicts with the current schema
    indexes = await collection.index_information()
    legacy = "service_session_id_1_sequential_index_1"
    if legacy in indexes:
        await collection.drop_index(legacy)

    for doc in _build_conversations():
        await collection.replace_one({"_id": doc["_id"]}, doc, upsert=True)
