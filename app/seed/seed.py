import secrets
import string
from typing import Any

from sqlalchemy import insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import PasswordSecurity
import app.domains.companies.models  # noqa: F401
import app.domains.products.models  # noqa: F401
from app.domains.auth.models import Permission, Role, User, role_permissions, user_roles


async def seed_roles(session: AsyncSession) -> None:
    roles = [
        {"id": 1, "name": "admin", "description": "system administrator"},
        {"id": 2, "name": "user", "description": "common user"},
        {"id": 3, "name": "agent", "description": "attends to the clients problems"},
        {"id": 4, "name": "client", "description": "end user of the application"},
    ]
    stmt = pg_insert(Role).values(roles).on_conflict_do_nothing()
    await session.execute(stmt)

async def seed_permissions(session: AsyncSession) -> None:
    permissions = [
        # User
        {"name": "user:create", "description": "Create users"},
        {"name": "user:read", "description": "Read user details"},
        {"name": "user:list", "description": "List users"},
        {"name": "user:update", "description": "Update users"},
        {"name": "user:replace", "description": "Replace users"},
        {"name": "user:add_roles", "description": "Add roles to users"},
        # Password
        {"name": "password:change", "description": "Change user password"},
        {"name": "password:reset", "description": "Reset user password"},
        # Role
        {"name": "role:create", "description": "Create roles"},
        {"name": "role:read", "description": "Read role details"},
        {"name": "role:list", "description": "List roles"},
        {"name": "role:update", "description": "Update roles"},
        {"name": "role:replace", "description": "Replace roles"},
        {"name": "role:delete", "description": "Delete roles"},
        {"name": "role:read_permissions", "description": "Read role permissions"},
        {"name": "role:add_permissions", "description": "Add permissions to roles"},
        # Permission
        {"name": "permission:create", "description": "Create permissions"},
        {"name": "permission:read", "description": "Read permission details"},
        {"name": "permission:list", "description": "List permissions"},
        {"name": "permission:update", "description": "Update permissions"},
        {"name": "permission:replace", "description": "Replace permissions"},
        {"name": "permission:delete", "description": "Delete permissions"},
        {"name": "permission:read_roles", "description": "Read permission roles"},
        {"name": "permission:add_to_roles", "description": "Add permission to roles"},
        # Session
        {"name": "session:create", "description": "Create sessions (login)"},
        {"name": "session:refresh", "description": "Refresh sessions"},
        {"name": "session:delete", "description": "Delete sessions (logout)"},
        # Chat
        {"name": "chat:create", "description": "Create chat entry in the database"},
        {"name": "chat:read", "description": "Read chat history"},
        {"name": "chat:update", "description": "Update chat attributes"},
        {"name": "chat:add_message", "description": "Send messages in a Chat"},
        {"name": "chat:set_agent", "description": "Set agent to conversation"},
        # Ticket
        {"name": "ticket:read", "description": "Read tickets"},
        {"name": "ticket:create", "description": "Create tickets"},
        {"name": "ticket:update_status", "description": "Update ticket status"},
    ]

    insert_stmt = pg_insert(Permission).values(permissions).on_conflict_do_nothing()
    await session.execute(insert_stmt)


async def seed_role_permissions(session: AsyncSession) -> None:
    relations = {
        "admin": ["user:%", "role:%", "permission:%", "chat:%", "password:%", "ticket:%"],
        "user": ["session:%", "chat:%", "password:change"],
        "agent": ["session:%", "chat:%", "password:change", "ticket:%"],
        "client": ["session:%", "chat:%", "password:change"],
    }

    for role_name, patterns in relations.items():
        res = await session.execute(select(Role.id).where(Role.name == role_name))
        role_id = res.scalar_one_or_none()
        if role_id is None:
            continue

        permission_ids: list[int] = []
        for pattern in patterns:
            res = await session.execute(select(Permission.id).where(Permission.name.like(pattern)))
            permission_ids.extend(res.scalars().all())

        if not permission_ids:
            continue

        values = [{"role_id": role_id, "permission_id": perm_id} for perm_id in permission_ids]
        insert_stmt = pg_insert(role_permissions).values(values).on_conflict_do_nothing()
        await session.execute(insert_stmt)


def generate_random_password(length: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits + string.punctuation

    while True:
        password = "".join(secrets.choice(alphabet) for _ in range(length))

        if (
            any(c.islower() for c in password)
            and any(c.isupper() for c in password)
            and any(c.isdigit() for c in password)
            and any(c in string.punctuation for c in password)
        ):
            return password


async def seed_users(session: AsyncSession) -> None:
    password_security = PasswordSecurity()

    admin_names: list[str] = ["angelina", "eduardo", "julia", "mafe", "pedro", "wesley"]
    default_password = "Admin@123!"
    users_payload: list[dict[str, Any]] = []

    for name in admin_names:
        users_payload.append(
            {
                "email": f"{name}@syncdesk.pro",
                "password_hash": password_security.generate_password_hash(default_password),
                "username": name,
                "name": name,
                "must_change_password": False,
                "must_accept_terms": False
            }
        )

    insert_stmt = pg_insert(User).values(users_payload).on_conflict_do_nothing()
    await session.execute(insert_stmt)

    role_result = await session.execute(select(Role.id).where(Role.name == "admin"))
    admin_role_id = role_result.scalar_one_or_none()
    if admin_role_id is None:
        return

    users_result = await session.execute(
        select(User.id).where(User.email.in_([user["email"] for user in users_payload]))
    )
    user_ids = users_result.scalars().all()
    if not user_ids:
        return

    user_role_values = [{"user_id": user_id, "role_id": admin_role_id} for user_id in user_ids]
    role_insert_stmt = pg_insert(user_roles).values(user_role_values).on_conflict_do_nothing()
    await session.execute(role_insert_stmt)
