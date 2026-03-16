from sqlalchemy import insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.auth.models import Permission, Role, role_permissions


async def seed_roles(session: AsyncSession) -> None:
    roles = [
        {"id": 1, "name": "admin", "description": "system administrator"},
        {"id": 2, "name": "user", "description": "common user"},
    ]

    await session.execute(insert(Role).values(roles))


async def seed_permissions(session: AsyncSession) -> None:
    permissions = [
        # User
        {"name": "user:create", "description": "Create users"},
        {"name": "user:read", "description": "Read user details"},
        {"name": "user:list", "description": "List users"},
        {"name": "user:update", "description": "Update users"},
        {"name": "user:replace", "description": "Replace users"},
        {"name": "user:add_roles", "description": "Add roles to users"},
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
    ]

    await session.execute(insert(Permission).values(permissions))


async def seed_role_permissions(session: AsyncSession) -> None:
    relations = {
        "admin": ["user:%", "role:%", "permission:%"],
        "user": ["session:%"],
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
