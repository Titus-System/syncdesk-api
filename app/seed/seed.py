import secrets
import string
from typing import Any

from sqlalchemy import select
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
        {"name": "user:update_roles", "description": "Add and remove roles from users"},
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
        {"name": "ticket:update", "description": "Update ticket fields"},
        {"name": "ticket:update_status", "description": "Update ticket status"},
        {"name": "ticket:queue", "description": "Read ticket queue"},
        {"name": "ticket:assign", "description": "Assign tickets"},
        {"name": "ticket:transfer", "description": "Transfer tickets"},
        {"name": "ticket:escalate", "description": "Escalate tickets"},
        {"name": "ticket:comment", "description": "Adds comment to ticket"},
        {"name": "ticket:update_comment", "description": "Updates comment to ticket"},
        {"name": "ticket:delete_comment", "description": "Deletes comment to ticket"},
        # Company
        {"name": "company:create", "description": "Create companies"},
        {"name": "company:read", "description": "Read company details"},
        {"name": "company:list", "description": "List companies"},
        {"name": "company:replace", "description": "Replace companies"},
        {"name": "company:update", "description": "Update companies"},
        {"name": "company:soft_delete", "description": "Soft delete companies"},
        {"name": "company:add_product", "description": "Add product to company"},
        {"name": "company:remove_products", "description": "Remove products from company in batch"},
        {"name": "company:remove_product", "description": "Remove single product from company"},
        {"name": "company:add_users", "description": "Add users to company"},
        {"name": "company:remove_users", "description": "Remove users from company in batch"},
        {"name": "company:remove_user", "description": "Remove single user from company"},
        {"name": "company:list_users", "description": "List company users"},
        # Product
        {"name": "product:create", "description": "Create products"},
        {"name": "product:read", "description": "Read product details"},
        {"name": "product:list", "description": "List products"},
        {"name": "product:replace", "description": "Replace products"},
        {"name": "product:update", "description": "Update products"},
        {"name": "product:soft_delete", "description": "Soft delete products"},
        {"name": "product:add_companies", "description": "Add product to companies"},
        {"name": "product:remove_companies", "description": "Remove product from companies in batch"},
        {"name": "product:remove_company", "description": "Remove product from single company"},
        {"name": "product:list_companies", "description": "List product companies"},
    ]

    insert_stmt = pg_insert(Permission).values(permissions).on_conflict_do_nothing()
    await session.execute(insert_stmt)


async def seed_role_permissions(session: AsyncSession) -> None:
    relations = {
        "admin": ["user:%", "role:%", "permission:%", "chat:%", "password:%", "ticket:%", "company:%", "product:%"],
        "user": ["session:%", "chat:%", "password:change"],
        "agent": [
            "session:%",
            "chat:%",
            "password:change",
            "ticket:%",
            "company:read",
            "company:list",
            "product:read",
            "product:list",
        ],
        "client": ["session:%", "chat:%", "password:change", "company:read", "product:read", "product:list", "ticket:read"],
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
                "must_accept_terms": False,
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