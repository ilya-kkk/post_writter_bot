import asyncio
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from telethon import TelegramClient, functions, types
from telethon.errors import (
    ChannelsTooMuchError,
    FloodWaitError,
    InviteHashEmptyError,
    InviteHashExpiredError,
    InviteHashInvalidError,
    InviteRequestSentError,
    PasswordHashInvalidError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    PhoneNumberInvalidError,
    RPCError,
    SessionPasswordNeededError,
    UserAlreadyParticipantError,
    UserChannelsTooMuchError,
)

from app.core.config import settings

DEFAULT_POST_LIMIT = 12
DEFAULT_MAX_MATERIAL_CHARS = 12000
PRIVATE_INVITE_CHECK_ATTEMPTS = 4
PRIVATE_INVITE_CHECK_DELAY_SECONDS = 1.0
TELEGRAM_HOSTS = {"t.me", "telegram.me", "www.t.me", "www.telegram.me"}


class TelegramClientConfigError(Exception):
    """Raised when the MTProto client is not configured."""


@dataclass(frozen=True)
class TelegramClientOperationError(Exception):
    code: str
    message: str
    retry_after_seconds: int | None = None


@dataclass(frozen=True)
class TelegramClientPost:
    text: str
    published_at: str | None = None


@dataclass(frozen=True)
class TelegramClientChannelSnapshot:
    title: str
    source_url: str
    entity_id: int | None
    posts: list[TelegramClientPost]


_client_lock = asyncio.Lock()


async def get_telegram_client_status() -> dict[str, Any]:
    base_status = _base_status()
    if not _has_required_config():
        return {
            **base_status,
            "status": "not_configured",
            "authorized": False,
        }

    async with _client_lock:
        client = _build_client()
        await client.connect()
        try:
            authorized = await client.is_user_authorized()
            payload: dict[str, Any] = {
                **_base_status(),
                "status": "authorized" if authorized else "not_authorized",
                "authorized": authorized,
            }
            if authorized:
                payload["user"] = _serialize_user(await client.get_me())
            return payload
        finally:
            await client.disconnect()


async def send_login_code(phone: str) -> dict[str, Any]:
    normalized_phone = _normalize_phone(phone)
    async with _client_lock:
        client = _build_client()
        await client.connect()
        try:
            if await client.is_user_authorized():
                return {
                    **_base_status(),
                    "status": "authorized",
                    "authorized": True,
                    "user": _serialize_user(await client.get_me()),
                }

            sent_code = await _call_telegram(
                client.send_code_request(normalized_phone),
                invalid_phone_message="Telegram не принял номер телефона",
            )
            _write_pending_login(
                {
                    "phone": normalized_phone,
                    "phone_code_hash": sent_code.phone_code_hash,
                }
            )
            return {
                **_base_status(),
                "status": "code_sent",
                "authorized": False,
                "phone": normalized_phone,
                "code_type": sent_code.type.__class__.__name__,
            }
        finally:
            await client.disconnect()


async def sign_in_with_code(code: str, phone: str | None = None) -> dict[str, Any]:
    normalized_code = code.strip().replace(" ", "")
    if not normalized_code:
        raise TelegramClientOperationError("empty_code", "Код Telegram не может быть пустым")

    pending_login = _read_pending_login()
    normalized_phone = _normalize_phone(phone or pending_login.get("phone") or "")
    phone_code_hash = pending_login.get("phone_code_hash")

    async with _client_lock:
        client = _build_client()
        await client.connect()
        try:
            if await client.is_user_authorized():
                _delete_pending_login()
                return {
                    **_base_status(),
                    "status": "authorized",
                    "authorized": True,
                    "user": _serialize_user(await client.get_me()),
                }

            try:
                user = await client.sign_in(
                    phone=normalized_phone,
                    code=normalized_code,
                    phone_code_hash=phone_code_hash,
                )
            except SessionPasswordNeededError:
                return {
                    **_base_status(),
                    "status": "password_required",
                    "authorized": False,
                    "phone": normalized_phone,
                }
            except PhoneCodeInvalidError as exc:
                raise TelegramClientOperationError("invalid_code", "Telegram не принял код") from exc
            except PhoneCodeExpiredError as exc:
                _delete_pending_login()
                raise TelegramClientOperationError(
                    "code_expired",
                    "Код Telegram истек. Запросите новый код.",
                ) from exc
            except PhoneNumberInvalidError as exc:
                raise TelegramClientOperationError(
                    "invalid_phone",
                    "Telegram не принял номер телефона",
                ) from exc
            except FloodWaitError as exc:
                raise TelegramClientOperationError(
                    "flood_wait",
                    f"Telegram временно ограничил вход. Повторите через {exc.seconds} секунд.",
                    retry_after_seconds=exc.seconds,
                ) from exc
            except RPCError as exc:
                raise TelegramClientOperationError("telegram_rpc_error", str(exc)) from exc

            _delete_pending_login()
            return {
                **_base_status(),
                "status": "authorized",
                "authorized": True,
                "user": _serialize_user(user),
            }
        finally:
            await client.disconnect()


async def sign_in_with_password(password: str) -> dict[str, Any]:
    if not password:
        raise TelegramClientOperationError("empty_password", "Пароль 2FA не может быть пустым")

    async with _client_lock:
        client = _build_client()
        await client.connect()
        try:
            if await client.is_user_authorized():
                _delete_pending_login()
                return {
                    **_base_status(),
                    "status": "authorized",
                    "authorized": True,
                    "user": _serialize_user(await client.get_me()),
                }

            try:
                user = await client.sign_in(password=password)
            except PasswordHashInvalidError as exc:
                raise TelegramClientOperationError(
                    "invalid_password",
                    "Telegram не принял пароль 2FA",
                ) from exc
            except FloodWaitError as exc:
                raise TelegramClientOperationError(
                    "flood_wait",
                    f"Telegram временно ограничил вход. Повторите через {exc.seconds} секунд.",
                    retry_after_seconds=exc.seconds,
                ) from exc
            except RPCError as exc:
                raise TelegramClientOperationError("telegram_rpc_error", str(exc)) from exc

            _delete_pending_login()
            return {
                **_base_status(),
                "status": "authorized",
                "authorized": True,
                "user": _serialize_user(user),
            }
        finally:
            await client.disconnect()


async def log_out_telegram_client() -> dict[str, Any]:
    async with _client_lock:
        client = _build_client()
        await client.connect()
        try:
            if await client.is_user_authorized():
                await client.log_out()
            _delete_pending_login()
            return {
                **_base_status(),
                "status": "not_authorized",
                "authorized": False,
            }
        finally:
            await client.disconnect()


async def fetch_private_invite_channel_posts(
    channel_link: str,
    *,
    limit: int = DEFAULT_POST_LIMIT,
) -> TelegramClientChannelSnapshot:
    invite_hash = extract_private_invite_hash(channel_link)
    if not invite_hash:
        raise TelegramClientOperationError(
            "unsupported_private_link",
            "Эту приватную ссылку нельзя открыть через invite hash",
        )

    async with _client_lock:
        client = _build_client()
        await client.connect()
        try:
            if not await client.is_user_authorized():
                raise TelegramClientOperationError(
                    "telegram_client_not_authorized",
                    "Telegram user-аккаунт не авторизован",
                )

            chat = await _join_invite_and_get_chat(client, invite_hash)
            posts = await _fetch_text_posts(client, chat, limit=limit)
            if not posts:
                raise TelegramClientOperationError(
                    "no_text_posts",
                    "В канале не нашлось доступных текстовых постов",
                )

            return TelegramClientChannelSnapshot(
                title=getattr(chat, "title", None) or "Telegram channel",
                source_url=channel_link,
                entity_id=getattr(chat, "id", None),
                posts=posts,
            )
        finally:
            await client.disconnect()


def format_client_channel_snapshot_for_analysis(
    snapshot: TelegramClientChannelSnapshot,
    *,
    max_chars: int = DEFAULT_MAX_MATERIAL_CHARS,
) -> str:
    parts = [
        f"Источник: приватный Telegram-канал {snapshot.title}",
        f"Ссылка: {snapshot.source_url}",
        "",
        "Последние доступные текстовые посты:",
    ]
    for index, post in enumerate(snapshot.posts, start=1):
        meta_text = f" ({post.published_at})" if post.published_at else ""
        parts.append(f"\nПост {index}{meta_text}:\n{post.text}")

    material = "\n".join(parts).strip()
    if len(material) <= max_chars:
        return material

    return material[: max_chars - 15].rstrip() + "\n\n[обрезано]"


def extract_private_invite_hash(value: str) -> str | None:
    raw_value = value.strip()
    if not raw_value:
        return None

    parsed = urlparse(raw_value if "://" in raw_value else f"https://{raw_value}")
    if parsed.scheme == "tg":
        invite = parse_qs(parsed.query).get("invite", [])
        return invite[0].strip() if invite and invite[0].strip() else None

    host = (parsed.netloc or "").lower()
    if host not in TELEGRAM_HOSTS:
        return None

    parts = [unquote(part) for part in parsed.path.split("/") if part]
    if not parts:
        return None

    if parts[0].startswith("+"):
        invite_hash = parts[0][1:].strip()
        return invite_hash or None

    if parts[0] == "joinchat" and len(parts) > 1:
        invite_hash = parts[1].strip()
        return invite_hash or None

    return None


def _build_client() -> TelegramClient:
    api_id = _api_id()
    api_hash = settings.telegram_client_api_hash.strip()
    if not api_hash:
        raise TelegramClientConfigError("TELEGRAM_CLIENT_API_HASH is not configured")

    session_path = _session_base_path()
    session_path.parent.mkdir(parents=True, exist_ok=True)
    return TelegramClient(
        str(session_path),
        api_id,
        api_hash,
        timeout=settings.telegram_client_timeout_seconds,
    )


def _api_id() -> int:
    raw_api_id = settings.telegram_client_api_id.strip()
    if not raw_api_id:
        raise TelegramClientConfigError("TELEGRAM_CLIENT_API_ID is not configured")
    try:
        return int(raw_api_id)
    except ValueError as exc:
        raise TelegramClientConfigError("TELEGRAM_CLIENT_API_ID must be an integer") from exc


def _has_required_config() -> bool:
    return bool(settings.telegram_client_api_id.strip() and settings.telegram_client_api_hash.strip())


def _base_status() -> dict[str, Any]:
    session_file = _session_file_path()
    return {
        "configured": _has_required_config(),
        "session_name": settings.telegram_client_session_name,
        "session_path": str(session_file),
        "session_exists": session_file.exists(),
        "pending_login_exists": _pending_login_path().exists(),
    }


def _data_dir() -> Path:
    return Path(settings.telegram_client_data_dir).expanduser()


def _session_base_path() -> Path:
    session_name = settings.telegram_client_session_name.strip() or "post_writer_client"
    return _data_dir() / session_name


def _session_file_path() -> Path:
    session_base_path = _session_base_path()
    if session_base_path.suffix == ".session":
        return session_base_path
    return session_base_path.with_suffix(".session")


def _pending_login_path() -> Path:
    session_name = settings.telegram_client_session_name.strip() or "post_writer_client"
    return _data_dir() / f"{session_name}.pending_login.json"


def _normalize_phone(phone: str) -> str:
    normalized = phone.strip()
    if not normalized:
        raise TelegramClientOperationError("empty_phone", "Номер телефона не может быть пустым")
    return normalized


def _read_pending_login() -> dict[str, str]:
    path = _pending_login_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(key): str(value) for key, value in data.items() if value is not None}


def _write_pending_login(payload: dict[str, str]) -> None:
    path = _pending_login_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=True), encoding="utf-8")
    path.chmod(0o600)


def _delete_pending_login() -> None:
    path = _pending_login_path()
    try:
        path.unlink()
    except FileNotFoundError:
        pass


async def _call_telegram(coro, *, invalid_phone_message: str):
    try:
        return await coro
    except PhoneNumberInvalidError as exc:
        raise TelegramClientOperationError("invalid_phone", invalid_phone_message) from exc
    except FloodWaitError as exc:
        raise TelegramClientOperationError(
            "flood_wait",
            f"Telegram временно ограничил вход. Повторите через {exc.seconds} секунд.",
            retry_after_seconds=exc.seconds,
        ) from exc
    except RPCError as exc:
        raise TelegramClientOperationError("telegram_rpc_error", str(exc)) from exc


async def _join_invite_and_get_chat(client: TelegramClient, invite_hash: str):
    try:
        chat = await _check_invite_joined(client, invite_hash)
    except TelegramClientOperationError as exc:
        if exc.code != "invalid_invite_link":
            raise
        chat = None
    if chat is not None:
        return chat

    try:
        await client(functions.messages.ImportChatInviteRequest(invite_hash))
    except UserAlreadyParticipantError:
        pass
    except InviteRequestSentError:
        pass
    except (InviteHashEmptyError, InviteHashExpiredError, InviteHashInvalidError) as exc:
        raise TelegramClientOperationError(
            "invalid_invite_link",
            "Telegram не принял invite-ссылку",
        ) from exc
    except (ChannelsTooMuchError, UserChannelsTooMuchError) as exc:
        raise TelegramClientOperationError(
            "too_many_channels",
            "Telegram-аккаунт уже состоит в слишком большом количестве каналов",
        ) from exc
    except FloodWaitError as exc:
        raise TelegramClientOperationError(
            "flood_wait",
            f"Telegram временно ограничил вход. Повторите через {exc.seconds} секунд.",
            retry_after_seconds=exc.seconds,
        ) from exc
    except RPCError as exc:
        raise TelegramClientOperationError("telegram_rpc_error", str(exc)) from exc

    for _ in range(PRIVATE_INVITE_CHECK_ATTEMPTS):
        chat = await _check_invite_joined(client, invite_hash)
        if chat is not None:
            return chat
        await asyncio.sleep(PRIVATE_INVITE_CHECK_DELAY_SECONDS)

    raise TelegramClientOperationError(
        "join_request_pending",
        "Заявка на вступление отправлена, но доступ к каналу пока не появился",
    )


async def _check_invite_joined(client: TelegramClient, invite_hash: str):
    try:
        invite = await client(functions.messages.CheckChatInviteRequest(invite_hash))
    except (InviteHashEmptyError, InviteHashExpiredError, InviteHashInvalidError) as exc:
        raise TelegramClientOperationError(
            "invalid_invite_link",
            "Telegram не принял invite-ссылку",
        ) from exc
    except FloodWaitError as exc:
        raise TelegramClientOperationError(
            "flood_wait",
            f"Telegram временно ограничил вход. Повторите через {exc.seconds} секунд.",
            retry_after_seconds=exc.seconds,
        ) from exc
    except RPCError as exc:
        raise TelegramClientOperationError("telegram_rpc_error", str(exc)) from exc

    if isinstance(invite, types.ChatInviteAlready):
        return invite.chat
    return None


async def _fetch_text_posts(client: TelegramClient, chat, *, limit: int) -> list[TelegramClientPost]:
    posts: list[TelegramClientPost] = []
    async for message in client.iter_messages(chat, limit=max(limit * 3, limit)):
        text = (message.message or "").strip()
        if not text:
            continue
        posts.append(
            TelegramClientPost(
                text=_normalize_post_text(text),
                published_at=message.date.isoformat() if message.date else None,
            )
        )
        if len(posts) >= limit:
            break

    return list(reversed(posts))


def _normalize_post_text(text: str) -> str:
    normalized = text.replace("\xa0", " ")
    normalized = re.sub(r"[ \t\r\f\v]+", " ", normalized)
    normalized = re.sub(r" *\n *", "\n", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()


def _serialize_user(user) -> dict[str, Any]:
    return {
        "id": user.id,
        "username": user.username,
        "phone": user.phone,
        "first_name": user.first_name,
        "last_name": user.last_name,
    }
