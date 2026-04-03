from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from app.core.dependencies import ResponseFactoryDep
from app.core.exceptions import AppHTTPException
from app.core.logger import get_logger
from app.db.exceptions import ResourceAlreadyExistsError
from app.domains.auth.schemas.api_schemas import (
    AdminRegisterUserRequest,
    ChangePasswordRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
)

from ..dependencies import (
    AuthServiceDep,
    CurrentUserSessionDep,
    UserServiceDep,
    PasswordServiceDep,
    require_permission,
)
from ..exceptions import (
    InvalidPasswordError,
    InvalidResetTokenError,
    InvalidSessionError,
    SessionNotFoundError,
    UserNotFoundError,
    UserPasswordNotConfiguredError,
)
from ..schemas import (
    RefreshSessionRequest,
    RegisterUserRequest,
    UserLoginRequest,
)
from .swagger_utils import (
    admin_register_swagger,
    change_password_swagger,
    forgot_password_swagger,
    get_me_swagger,
    login_swagger,
    logout_swagger,
    reset_password_swagger,
    refresh_swagger,
    register_swagger,
)

auth_router = APIRouter()


@auth_router.post("/login", tags=["Auth"], **login_swagger)
async def login(
    dto: UserLoginRequest, service: AuthServiceDep, response: ResponseFactoryDep
) -> JSONResponse:
    try:
        device_info = response.request.state.device_info
        login_response = await service.login(dto, device_info)
        return response.success(
            data=login_response.model_dump(mode="json"),
            status_code=status.HTTP_200_OK,
        )
    except (UserNotFoundError, InvalidPasswordError, UserPasswordNotConfiguredError) as e:
        raise AppHTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        ) from e


@auth_router.post("/register", tags=["Auth"], **register_swagger)
async def register_common_user(
    dto: RegisterUserRequest, service: AuthServiceDep, response: ResponseFactoryDep
) -> JSONResponse:
    try:
        device_info = response.request.state.device_info
        user = await service.register(dto, device_info)
        return response.success(
            data=user,
            status_code=status.HTTP_201_CREATED,
        )
    except ResourceAlreadyExistsError as e:
        raise AppHTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid registration data",
        ) from e


@auth_router.post("/refresh", tags=["Auth"], **refresh_swagger)
async def refresh(
    dto: RefreshSessionRequest,
    current_user: CurrentUserSessionDep,
    request: Request,
    service: AuthServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    try:
        user, session = current_user
        device_info = request.state.device_info

        tokens = await service.refresh_session(user, session, dto, device_info)
        return response.success(
            data=tokens,
            status_code=status.HTTP_200_OK,
        )
    except SessionNotFoundError as e:
        raise AppHTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found. Login required.",
        ) from e
    except InvalidSessionError as e:
        raise AppHTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session. New login required.",
        ) from e


@auth_router.post("/logout", tags=["Auth"], **logout_swagger)
async def logout(
    user_session: CurrentUserSessionDep,
    response: ResponseFactoryDep,
    service: AuthServiceDep,
) -> JSONResponse:
    user, session = user_session
    await service.logout(user, session)
    return response.success(
        data=None,
        status_code=status.HTTP_200_OK,
    )


@auth_router.get("/me", tags=["Auth"], **get_me_swagger)
async def get_me(
    user_session: CurrentUserSessionDep, service: UserServiceDep, response: ResponseFactoryDep
) -> JSONResponse:
    user = user_session[0]
    user_with_roles = await service.get_by_id_with_roles(user.id)
    if user_with_roles is None:
        raise AppHTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return response.success(data=user_with_roles.to_response_dict(), status_code=status.HTTP_200_OK)


@auth_router.post(
    "/admin/register",
    tags=["Auth"],
    dependencies=[require_permission("user:create")],
    **admin_register_swagger,
)
async def admin_register_user(
    dto: AdminRegisterUserRequest,
    _auth: CurrentUserSessionDep,
    service: AuthServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    try:
        user = await service.admin_register(dto)
        return response.success(
            data=user.to_response_dict(),
            status_code=status.HTTP_201_CREATED,
        )
    except ResourceAlreadyExistsError as e:
        raise AppHTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid registration data",
        ) from e


@auth_router.post(
    "/change-password",
    tags=["Auth"],
    dependencies=[require_permission("password:change")],
    **change_password_swagger,
)
async def change_password(
    dto: ChangePasswordRequest,
    auth: CurrentUserSessionDep,
    service: PasswordServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    user = auth[0]
    try:
        updated_user = await service.change_password(user, dto.current_password, dto.new_password)

        if updated_user is None:
            raise AppHTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")

        return response.success(data=None, status_code=status.HTTP_200_OK)
    except InvalidPasswordError as e:
        raise AppHTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect."
        ) from e


@auth_router.post("/forgot-password", tags=["Auth"], **forgot_password_swagger)
async def forgot_password(
    dto: ForgotPasswordRequest, service: PasswordServiceDep, response: ResponseFactoryDep
) -> JSONResponse:
    try:
        await service.forgot_password(dto.email)
    except Exception:
        get_logger().error("Failed forgot-password pipeline.", exc_info=True)
    return response.success(
        data={"message": "If the email exists, a reset link has been sent."},
        status_code=status.HTTP_200_OK,
    )


@auth_router.post("/reset-password", tags=["Auth"], **reset_password_swagger)
async def reset_password(
    dto: ResetPasswordRequest, service: PasswordServiceDep, response: ResponseFactoryDep
) -> JSONResponse:
    try:
        user = await service.reset_password(dto.token, dto.new_password)

        if user is None:
            raise AppHTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Could not reset password for this token.",
            )

        return response.success(data=None, status_code=status.HTTP_200_OK)
    except InvalidResetTokenError as e:
        raise AppHTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid or expired reset token."
        ) from e
