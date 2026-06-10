from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, status
from pydantic import BaseModel

from app.core.config import settings
from app.core.logging import configure_logging
from app.services.telegram_client import (
    TelegramClientConfigError,
    TelegramClientOperationError,
    get_telegram_client_status,
    log_out_telegram_client,
    send_login_code,
    sign_in_with_code,
    sign_in_with_password,
)

configure_logging()

app = FastAPI(title="Telegram Client API")


class SendCodeRequest(BaseModel):
    phone: str


class SignInCodeRequest(BaseModel):
    code: str
    phone: str | None = None


class SignInPasswordRequest(BaseModel):
    password: str


async def require_admin_token(x_admin_token: Annotated[str | None, Header()] = None) -> None:
    expected_token = settings.telegram_client_admin_token.strip()
    if expected_token and x_admin_token != expected_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": "invalid_admin_token",
                "message": "Invalid X-Admin-Token header",
            },
        )


AdminToken = Depends(require_admin_token)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "env": settings.app_env}


@app.get("/telegram-client/status", dependencies=[AdminToken])
async def telegram_client_status() -> dict:
    try:
        return await get_telegram_client_status()
    except TelegramClientConfigError as exc:
        raise _http_error(exc) from exc


@app.post("/telegram-client/send-code", dependencies=[AdminToken])
async def telegram_client_send_code(payload: SendCodeRequest) -> dict:
    try:
        return await send_login_code(payload.phone)
    except (TelegramClientConfigError, TelegramClientOperationError) as exc:
        raise _http_error(exc) from exc


@app.post("/telegram-client/sign-in", dependencies=[AdminToken])
async def telegram_client_sign_in(payload: SignInCodeRequest) -> dict:
    try:
        return await sign_in_with_code(payload.code, phone=payload.phone)
    except (TelegramClientConfigError, TelegramClientOperationError) as exc:
        raise _http_error(exc) from exc


@app.post("/telegram-client/password", dependencies=[AdminToken])
async def telegram_client_password(payload: SignInPasswordRequest) -> dict:
    try:
        return await sign_in_with_password(payload.password)
    except (TelegramClientConfigError, TelegramClientOperationError) as exc:
        raise _http_error(exc) from exc


@app.post("/telegram-client/logout", dependencies=[AdminToken])
async def telegram_client_logout() -> dict:
    try:
        return await log_out_telegram_client()
    except (TelegramClientConfigError, TelegramClientOperationError) as exc:
        raise _http_error(exc) from exc


def _http_error(exc: TelegramClientConfigError | TelegramClientOperationError) -> HTTPException:
    if isinstance(exc, TelegramClientConfigError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "telegram_client_not_configured",
                "message": str(exc),
            },
        )

    status_code = status.HTTP_400_BAD_REQUEST
    if exc.code == "flood_wait":
        status_code = status.HTTP_429_TOO_MANY_REQUESTS

    headers = None
    if exc.retry_after_seconds is not None:
        headers = {"Retry-After": str(exc.retry_after_seconds)}

    return HTTPException(
        status_code=status_code,
        detail={
            "code": exc.code,
            "message": exc.message,
            "retry_after_seconds": exc.retry_after_seconds,
        },
        headers=headers,
    )
