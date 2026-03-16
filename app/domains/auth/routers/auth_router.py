from typing import Any

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse

from app.core.dependencies import ResponseFactoryDep
from app.core.exceptions import AppHTTPException
from app.db.exceptions import ResourceAlreadyExistsError
from app.schemas.response import GenericSuccessContent

from ..dependencies import AuthServiceDep, CurrentUserSessionDep, UserServiceDep
from ..exceptions import (
    InvalidPasswordError,
    InvalidSessionError,
    SessionNotFoundError,
    UserNotFoundError,
    UserPasswordNotConfiguredError,
)
from ..schemas import (
    LoginResponse,
    RefreshSessionRequest,
    RegisterUserRequest,
    UserCreatedResponse,
    UserLoginRequest,
)

auth_router = APIRouter()


register_responses: dict[int | str, dict[str, Any]] = {
    status.HTTP_201_CREATED: {
        "model": UserCreatedResponse,
        "description": "User created successfully.",
    }
}


login_responses: dict[str | int, dict[str, Any]] = {
    status.HTTP_200_OK: {"description": "Login successful"},
    status.HTTP_404_NOT_FOUND: {"description": "User not found"},
    status.HTTP_400_BAD_REQUEST: {"description": "Password not configured"},
    status.HTTP_401_UNAUTHORIZED: {"description": "Invalid password"},
}

login_response_model = GenericSuccessContent[LoginResponse]


@auth_router.post(
    "/login", tags=["Auth"], response_model=login_response_model, responses=login_responses
)
async def login(
    dto: UserLoginRequest, service: AuthServiceDep, response: ResponseFactoryDep
) -> JSONResponse:
    try:
        device_info = response.request.state.device_info
        access_token, refresh_token = await service.login(dto, device_info)
        return response.success(
            data={"access_token": access_token, "refresh_token": refresh_token},
            status_code=status.HTTP_200_OK,
        )
    except (UserNotFoundError, InvalidPasswordError, UserPasswordNotConfiguredError) as e:
        raise AppHTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        ) from e


@auth_router.post("/register", tags=["Auth"], responses=register_responses)
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


@auth_router.post("/refresh", tags=["Auth"])
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


@auth_router.post("/logout", tags=["Auth"])
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


@auth_router.get("/me", tags=["Auth"])
async def get_me(
    user_session: CurrentUserSessionDep, service: UserServiceDep, response: ResponseFactoryDep
) -> JSONResponse:
    user = user_session[0]
    user_with_roles = await service.get_by_id_with_roles(user.id)
    if user_with_roles is None:
        raise AppHTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return response.success(data=user_with_roles.to_response_dict(), status_code=status.HTTP_200_OK)
