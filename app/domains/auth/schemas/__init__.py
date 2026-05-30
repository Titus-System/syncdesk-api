from app.core.http.schemas import SessionDeviceInfo

from .api_schemas import *
from .permission_schemas import CreatePermissionDTO, ReplacePermissionDTO, UpdatePermissionDTO
from .reset_password_token_schemas import *
from .role_schemas import AddRolePermissionsDTO, CreateRoleDTO, ReplaceRoleDTO, UpdateRoleDTO
from .session_schemas import (
    CreateSessionDTO,
    RefreshSessionDTO,
    UpdateSessionDTO,
)
from .user_schemas import (
    AddUserRolesDTO,
    CreateUserDTO,
    CurrentUserAvatarDTO,
    ReplaceUserDTO,
    SetUserAvatarDTO,
    UpdateUserDTO,
    UserCompliance,
    UserResponseDTO,
    RoleResponseDTO
)
from .user_level_schemas import (
    DeleteUserLevelResponseDTO,
    LevelResponseDTO,
    LevelUserResponseDTO,
    LevelUsersResponseDTO,
    UserLevelResponseDTO,
    UserLevelsResponseDTO,
)

__all__ = [
    "CreateRoleDTO",
    "ReplaceRoleDTO",
    "UpdateRoleDTO",
    "AddRolePermissionsDTO",
    "CreatePermissionDTO",
    "ReplacePermissionDTO",
    "UpdatePermissionDTO",
    "CreateSessionDTO",
    "UpdateSessionDTO",
    "RefreshSessionDTO",
    "SessionDeviceInfo",
    "CreateUserDTO",
    "ReplaceUserDTO",
    "UpdateUserDTO",
    "AddUserRolesDTO",
    "CurrentUserAvatarDTO",
    "SetUserAvatarDTO",
    "UserCompliance",
    "UserResponseDTO",
    "RoleResponseDTO",
    "LevelResponseDTO",
    "UserLevelResponseDTO",
    "UserLevelsResponseDTO",
    "LevelUserResponseDTO",
    "LevelUsersResponseDTO",
    "DeleteUserLevelResponseDTO",
    "CreatePasswordResetTokenDTO",
    "LoginResponse",
    "RefreshSessionRequest",
    "RegisterUserRequest",
    "UserCreatedResponse",
    "UserLoginRequest",
    "AdminRegisterUserRequest",
    "ChangePasswordRequest",
    "ForgotPasswordRequest",
    "ResetPasswordRequest"
]
