from typing import Any

from fastapi import status

from app.domains.auth.entities import (
    Permission,
    PermissionWithRoles,
    Role,
    RoleWithPermissions,
    User,
    UserWithRoles,
)
from app.domains.auth.schemas import LoginResponse, UserCreatedResponse
from app.schemas.response import ErrorContent, GenericSuccessContent

# ---------------------------------------------------------------------------
# Auth Router
# ---------------------------------------------------------------------------

login_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Login successful. Returns access and refresh tokens.",
        "model": GenericSuccessContent[LoginResponse],
    },
    401: {
        "description": "Invalid email or password.",
        "model": ErrorContent,
    },
    422: {
        "description": "Request body validation failed.",
        "model": ErrorContent,
    },
}

login_swagger: dict[str, Any] = {
    "summary": "Authenticate user",
    "description": (
        "Validates credentials and returns a pair of access / refresh tokens. "
        "Returns 401 for wrong email or password."
    ),
    "response_model": GenericSuccessContent[LoginResponse],
    "responses": login_responses,
}

register_responses: dict[int | str, dict[str, Any]] = {
    201: {
        "description": "User registered successfully.",
        "model": GenericSuccessContent[UserCreatedResponse],
    },
    400: {
        "description": "Invalid registration data (e.g. duplicate email).",
        "model": ErrorContent,
    },
    422: {
        "description": "Request body validation failed.",
        "model": ErrorContent,
    },
}

register_swagger: dict[str, Any] = {
    "summary": "Register a new user",
    "description": (
        "Creates a new user account with the default 'user' role and returns "
        "the created user along with access / refresh tokens. "
        "Returns 400 if the email is already taken."
    ),
    "status_code": status.HTTP_201_CREATED,
    "response_model": GenericSuccessContent[UserCreatedResponse],
    "responses": register_responses,
}

refresh_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Session refreshed. Returns new access and refresh tokens.",
        "model": GenericSuccessContent[LoginResponse],
    },
    401: {
        "description": "Invalid or expired session. A new login is required.",
        "model": ErrorContent,
    },
    404: {
        "description": "Session not found. Login required.",
        "model": ErrorContent,
    },
}

refresh_swagger: dict[str, Any] = {
    "summary": "Refresh session tokens",
    "description": (
        "Rotates the refresh token and issues a new access token. "
        "The previous refresh token is invalidated."
    ),
    "response_model": GenericSuccessContent[LoginResponse],
    "responses": refresh_responses,
}

logout_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Logout successful. Session revoked.",
        "model": GenericSuccessContent[None],
    },
    403: {
        "description": "No valid authentication token provided.",
        "model": ErrorContent,
    },
}

logout_swagger: dict[str, Any] = {
    "summary": "Logout current session",
    "description": (
        "Revokes the current session so that the associated tokens "
        "can no longer be used."
    ),
    "response_model": GenericSuccessContent[None],
    "responses": logout_responses,
}

get_me_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Authenticated user profile retrieved successfully.",
        "model": GenericSuccessContent[UserWithRoles],
    },
    404: {
        "description": "User not found.",
        "model": ErrorContent,
    },
}

get_me_swagger: dict[str, Any] = {
    "summary": "Get current user profile",
    "description": (
        "Returns the profile of the currently authenticated user, "
        "including assigned roles."
    ),
    "response_model": GenericSuccessContent[UserWithRoles],
    "responses": get_me_responses,
}

admin_register_responses: dict[int | str, dict[str, Any]] = {
    201: {
        "description": "User registered successfully by admin.",
        "model": GenericSuccessContent[User],
    },
    400: {
        "description": "Invalid registration data (e.g. duplicate email).",
        "model": ErrorContent,
    },
    403: {
        "description": "Missing permission to create users.",
        "model": ErrorContent,
    },
    422: {
        "description": "Request body validation failed.",
        "model": ErrorContent,
    },
}

admin_register_swagger: dict[str, Any] = {
    "summary": "Register a new user as admin",
    "description": (
        "Creates a new user account via admin permissions. "
        "Returns 400 when registration data is invalid (for example, duplicate email)."
    ),
    "status_code": status.HTTP_201_CREATED,
    "response_model": GenericSuccessContent[User],
    "responses": admin_register_responses,
}

change_password_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Password changed successfully.",
        "model": GenericSuccessContent[None],
    },
    400: {
        "description": "Current password is incorrect.",
        "model": ErrorContent,
    },
    403: {
        "description": "Missing permission to change password.",
        "model": ErrorContent,
    },
    404: {
        "description": "User not found.",
        "model": ErrorContent,
    },
    422: {
        "description": "Request body validation failed.",
        "model": ErrorContent,
    },
}

change_password_swagger: dict[str, Any] = {
    "summary": "Change current user password",
    "description": (
        "Changes the authenticated user's password after validating the current password."
    ),
    "response_model": GenericSuccessContent[None],
    "responses": change_password_responses,
}

forgot_password_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Password reset flow triggered (always returns success).",
        "model": GenericSuccessContent[dict[str, str]],
    },
    422: {
        "description": "Request body validation failed.",
        "model": ErrorContent,
    },
}

forgot_password_swagger: dict[str, Any] = {
    "summary": "Request password reset",
    "description": (
        "Triggers the password reset flow for a given email. "
        "For security, the endpoint returns success even when the email is not registered."
    ),
    "response_model": GenericSuccessContent[dict[str, str]],
    "responses": forgot_password_responses,
}

reset_password_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Password reset successfully.",
        "model": GenericSuccessContent[None],
    },
    400: {
        "description": "Invalid token or password reset could not be completed.",
        "model": ErrorContent,
    },
    422: {
        "description": "Request body validation failed.",
        "model": ErrorContent,
    },
}

reset_password_swagger: dict[str, Any] = {
    "summary": "Reset password with token",
    "description": (
        "Resets the user's password using a valid reset token. "
        "Returns 400 when the token is invalid, expired, or cannot be used."
    ),
    "response_model": GenericSuccessContent[None],
    "responses": reset_password_responses,
}

# ---------------------------------------------------------------------------
# Permission Router
# ---------------------------------------------------------------------------

create_perm_responses: dict[int | str, dict[str, Any]] = {
    201: {
        "description": "Permission created successfully.",
        "model": GenericSuccessContent[Permission],
    },
    409: {
        "description": "A permission with this name already exists.",
        "model": ErrorContent,
    },
    422: {
        "description": "Request body validation failed.",
        "model": ErrorContent,
    },
}

create_perm_swagger: dict[str, Any] = {
    "summary": "Create a permission",
    "description": "Creates a new permission. Returns 409 if the name is already taken.",
    "status_code": status.HTTP_201_CREATED,
    "response_model": GenericSuccessContent[Permission],
    "responses": create_perm_responses,
}

list_perms_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "List of all permissions retrieved successfully.",
        "model": GenericSuccessContent[list[Permission]],
    },
}

list_perms_swagger: dict[str, Any] = {
    "summary": "List all permissions",
    "description": "Returns every permission registered in the system.",
    "response_model": GenericSuccessContent[list[Permission]],
    "responses": list_perms_responses,
}

get_perm_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Permission retrieved successfully.",
        "model": GenericSuccessContent[Permission],
    },
    404: {
        "description": "Permission not found.",
        "model": ErrorContent,
    },
}

get_perm_swagger: dict[str, Any] = {
    "summary": "Get a permission by ID",
    "description": "Returns a single permission by its ID. Returns 404 if not found.",
    "response_model": GenericSuccessContent[Permission],
    "responses": get_perm_responses,
}

replace_perm_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Permission fully replaced successfully.",
        "model": GenericSuccessContent[Permission],
    },
    404: {
        "description": "Permission not found.",
        "model": ErrorContent,
    },
    422: {
        "description": "Request body validation failed.",
        "model": ErrorContent,
    },
}

replace_perm_swagger: dict[str, Any] = {
    "summary": "Replace a permission",
    "description": "Fully replaces the permission identified by ID. Returns 404 if not found.",
    "response_model": GenericSuccessContent[Permission],
    "responses": replace_perm_responses,
}

update_perm_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Permission partially updated successfully.",
        "model": GenericSuccessContent[Permission],
    },
    404: {
        "description": "Permission not found.",
        "model": ErrorContent,
    },
    422: {
        "description": "Request body validation failed.",
        "model": ErrorContent,
    },
}

update_perm_swagger: dict[str, Any] = {
    "summary": "Partially update a permission",
    "description": "Applies a partial update to the permission identified by ID. Returns 404 if not found.",
    "response_model": GenericSuccessContent[Permission],
    "responses": update_perm_responses,
}

delete_perm_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Permission deleted successfully.",
        "model": GenericSuccessContent[Permission],
    },
    404: {
        "description": "Permission not found.",
        "model": ErrorContent,
    },
}

delete_perm_swagger: dict[str, Any] = {
    "summary": "Delete a permission",
    "description": "Deletes the permission identified by ID. Returns 404 if not found.",
    "response_model": GenericSuccessContent[Permission],
    "responses": delete_perm_responses,
}

get_perm_roles_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Permission with associated roles retrieved successfully.",
        "model": GenericSuccessContent[PermissionWithRoles],
    },
    404: {
        "description": "Permission not found.",
        "model": ErrorContent,
    },
}

get_perm_roles_swagger: dict[str, Any] = {
    "summary": "Get roles for a permission",
    "description": "Returns the permission and its associated roles. Returns 404 if not found.",
    "response_model": GenericSuccessContent[PermissionWithRoles],
    "responses": get_perm_roles_responses,
}

add_perm_to_roles_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Permission added to the specified roles successfully.",
        "model": GenericSuccessContent[PermissionWithRoles],
    },
    422: {
        "description": "Request body validation failed.",
        "model": ErrorContent,
    },
}

add_perm_to_roles_swagger: dict[str, Any] = {
    "summary": "Add permission to roles",
    "description": "Associates the permission with the given role IDs.",
    "response_model": GenericSuccessContent[PermissionWithRoles],
    "responses": add_perm_to_roles_responses,
}

# ---------------------------------------------------------------------------
# Role Router
# ---------------------------------------------------------------------------

create_role_responses: dict[int | str, dict[str, Any]] = {
    201: {
        "description": "Role created successfully.",
        "model": GenericSuccessContent[Role],
    },
    409: {
        "description": "A role with this name already exists.",
        "model": ErrorContent,
    },
    422: {
        "description": "Request body validation failed.",
        "model": ErrorContent,
    },
}

create_role_swagger: dict[str, Any] = {
    "summary": "Create a role",
    "description": "Creates a new role. Returns 409 if the name is already taken.",
    "status_code": status.HTTP_201_CREATED,
    "response_model": GenericSuccessContent[Role],
    "responses": create_role_responses,
}

list_roles_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "List of all roles retrieved successfully.",
        "model": GenericSuccessContent[list[Role]],
    },
}

list_roles_swagger: dict[str, Any] = {
    "summary": "List all roles",
    "description": "Returns every role registered in the system.",
    "response_model": GenericSuccessContent[list[Role]],
    "responses": list_roles_responses,
}

get_role_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Role retrieved successfully.",
        "model": GenericSuccessContent[Role],
    },
    404: {
        "description": "Role not found.",
        "model": ErrorContent,
    },
}

get_role_swagger: dict[str, Any] = {
    "summary": "Get a role by ID",
    "description": "Returns a single role by its ID. Returns 404 if not found.",
    "response_model": GenericSuccessContent[Role],
    "responses": get_role_responses,
}

replace_role_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Role fully replaced successfully.",
        "model": GenericSuccessContent[Role],
    },
    404: {
        "description": "Role not found.",
        "model": ErrorContent,
    },
    422: {
        "description": "Request body validation failed.",
        "model": ErrorContent,
    },
}

replace_role_swagger: dict[str, Any] = {
    "summary": "Replace a role",
    "description": "Fully replaces the role identified by ID. Returns 404 if not found.",
    "response_model": GenericSuccessContent[Role],
    "responses": replace_role_responses,
}

update_role_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Role partially updated successfully.",
        "model": GenericSuccessContent[Role],
    },
    404: {
        "description": "Role not found.",
        "model": ErrorContent,
    },
    422: {
        "description": "Request body validation failed.",
        "model": ErrorContent,
    },
}

update_role_swagger: dict[str, Any] = {
    "summary": "Partially update a role",
    "description": "Applies a partial update to the role identified by ID. Returns 404 if not found.",
    "response_model": GenericSuccessContent[Role],
    "responses": update_role_responses,
}

delete_role_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Role deleted successfully.",
        "model": GenericSuccessContent[Role],
    },
    404: {
        "description": "Role not found.",
        "model": ErrorContent,
    },
}

delete_role_swagger: dict[str, Any] = {
    "summary": "Delete a role",
    "description": "Deletes the role identified by ID. Returns 404 if not found.",
    "response_model": GenericSuccessContent[Role],
    "responses": delete_role_responses,
}

get_role_perms_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Role with associated permissions retrieved successfully.",
        "model": GenericSuccessContent[RoleWithPermissions],
    },
    404: {
        "description": "Role not found.",
        "model": ErrorContent,
    },
}

get_role_perms_swagger: dict[str, Any] = {
    "summary": "Get permissions for a role",
    "description": "Returns the role and its associated permissions. Returns 404 if not found.",
    "response_model": GenericSuccessContent[RoleWithPermissions],
    "responses": get_role_perms_responses,
}

add_role_perms_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Permissions added to the role successfully.",
        "model": GenericSuccessContent[RoleWithPermissions],
    },
    422: {
        "description": "Request body validation failed.",
        "model": ErrorContent,
    },
}

add_role_perms_swagger: dict[str, Any] = {
    "summary": "Add permissions to a role",
    "description": "Associates the given permission IDs with the role.",
    "response_model": GenericSuccessContent[RoleWithPermissions],
    "responses": add_role_perms_responses,
}

# ---------------------------------------------------------------------------
# User Router
# ---------------------------------------------------------------------------

create_user_responses: dict[int | str, dict[str, Any]] = {
    201: {
        "description": "User created successfully.",
        "model": GenericSuccessContent[User],
    },
    409: {
        "description": "A user with this email already exists.",
        "model": ErrorContent,
    },
    422: {
        "description": "Request body validation failed.",
        "model": ErrorContent,
    },
}

create_user_swagger: dict[str, Any] = {
    "summary": "Create a user",
    "description": (
        "Creates a new user (admin-only). "
        "Returns 409 if the email is already taken."
    ),
    "status_code": status.HTTP_201_CREATED,
    "response_model": GenericSuccessContent[User],
    "responses": create_user_responses,
}

list_users_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "List of all users retrieved successfully.",
        "model": GenericSuccessContent[list[User]],
    },
}

list_users_swagger: dict[str, Any] = {
    "summary": "List all users",
    "description": "Returns every user registered in the system.",
    "response_model": GenericSuccessContent[list[User]],
    "responses": list_users_responses,
}

get_user_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "User retrieved successfully.",
        "model": GenericSuccessContent[User],
    },
    404: {
        "description": "User not found.",
        "model": ErrorContent,
    },
}

get_user_swagger: dict[str, Any] = {
    "summary": "Get a user by ID",
    "description": "Returns a single user by their UUID. Returns 404 if not found.",
    "response_model": GenericSuccessContent[User],
    "responses": get_user_responses,
}

replace_user_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "User fully replaced successfully.",
        "model": GenericSuccessContent[User],
    },
    404: {
        "description": "User not found.",
        "model": ErrorContent,
    },
    422: {
        "description": "Request body validation failed.",
        "model": ErrorContent,
    },
}

replace_user_swagger: dict[str, Any] = {
    "summary": "Replace a user",
    "description": "Fully replaces the user identified by UUID. Returns 404 if not found.",
    "response_model": GenericSuccessContent[User],
    "responses": replace_user_responses,
}

update_user_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "User partially updated successfully.",
        "model": GenericSuccessContent[User],
    },
    404: {
        "description": "User not found.",
        "model": ErrorContent,
    },
    422: {
        "description": "Request body validation failed.",
        "model": ErrorContent,
    },
}

update_user_swagger: dict[str, Any] = {
    "summary": "Partially update a user",
    "description": "Applies a partial update to the user identified by UUID. Returns 404 if not found.",
    "response_model": GenericSuccessContent[User],
    "responses": update_user_responses,
}

add_user_roles_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Roles added to user successfully.",
        "model": GenericSuccessContent[UserWithRoles],
    },
    400: {
        "description": "No role IDs provided.",
        "model": ErrorContent,
    },
    404: {
        "description": "User or one of the referenced roles not found.",
        "model": ErrorContent,
    },
}

add_user_roles_swagger: dict[str, Any] = {
    "summary": "Add roles to a user",
    "description": (
        "Associates the given role IDs with the user. "
        "Returns 400 if no role IDs are provided, 404 if user or roles not found."
    ),
    "response_model": GenericSuccessContent[UserWithRoles],
    "responses": add_user_roles_responses,
}
