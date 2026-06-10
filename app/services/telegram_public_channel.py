import logging
import re
from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urlparse

import httpx

logger = logging.getLogger(__name__)

CHANNEL_USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{4,31}$")
DEFAULT_POST_LIMIT = 12
DEFAULT_MAX_MATERIAL_CHARS = 12000
VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "source",
    "track",
    "wbr",
}


@dataclass(frozen=True)
class PublicTelegramPost:
    text: str
    url: str | None = None
    published_at: str | None = None


@dataclass(frozen=True)
class PublicTelegramChannelSnapshot:
    username: str
    source_url: str
    posts: list[PublicTelegramPost]


class PublicTelegramChannelError(Exception):
    """Raised when a public Telegram channel cannot be parsed from t.me/s."""


def normalize_public_channel_username(value: str) -> str | None:
    raw_value = value.strip()
    if raw_value.startswith("@"):
        username = raw_value[1:]
        return username if CHANNEL_USERNAME_RE.match(username) else None

    url_value = raw_value if "://" in raw_value else f"https://{raw_value}"
    parsed = urlparse(url_value)
    host = (parsed.netloc or "").lower()
    if host not in {"t.me", "telegram.me", "www.t.me", "www.telegram.me"}:
        return None

    parts = [part for part in parsed.path.split("/") if part]
    if not parts:
        return None

    if parts[0] == "s":
        parts = parts[1:]

    if not parts:
        return None

    username = parts[0]
    if username.startswith("+") or username in {"c", "joinchat", "share", "iv", "addstickers"}:
        return None

    return username if CHANNEL_USERNAME_RE.match(username) else None


def is_private_telegram_link(value: str) -> bool:
    raw_value = value.strip()
    if raw_value.startswith("@"):
        return False

    url_value = raw_value if "://" in raw_value else f"https://{raw_value}"
    parsed = urlparse(url_value)
    host = (parsed.netloc or "").lower()
    if host not in {"t.me", "telegram.me", "www.t.me", "www.telegram.me"}:
        return False

    parts = [part for part in parsed.path.split("/") if part]
    if not parts:
        return False

    if parts[0] == "s":
        parts = parts[1:]

    if not parts:
        return False

    return parts[0].startswith("+") or parts[0] in {"c", "joinchat"}


async def fetch_public_channel_posts(
    channel_link: str,
    *,
    limit: int = DEFAULT_POST_LIMIT,
    timeout: float = 10.0,
) -> PublicTelegramChannelSnapshot:
    username = normalize_public_channel_username(channel_link)
    if username is None:
        raise PublicTelegramChannelError("Link is not a public Telegram channel username")

    source_url = f"https://t.me/s/{username}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; PostWriterBot/1.0; "
            "+https://t.me)"
        )
    }
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout, headers=headers) as client:
            response = await client.get(source_url)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.info("Failed to fetch public Telegram channel %s: %s", username, exc)
        raise PublicTelegramChannelError("Telegram public page is not available") from exc

    posts = parse_public_channel_posts(response.text)
    if not posts:
        raise PublicTelegramChannelError("No text posts found on Telegram public page")

    return PublicTelegramChannelSnapshot(
        username=username,
        source_url=source_url,
        posts=posts[-limit:],
    )


def parse_public_channel_posts(html: str) -> list[PublicTelegramPost]:
    parser = _TelegramPublicChannelParser()
    parser.feed(html)
    parser.close()
    return parser.posts


def format_channel_snapshot_for_analysis(
    snapshot: PublicTelegramChannelSnapshot,
    *,
    max_chars: int = DEFAULT_MAX_MATERIAL_CHARS,
) -> str:
    parts = [
        f"Источник: публичный Telegram-канал @{snapshot.username}",
        f"Ссылка: {snapshot.source_url}",
        "",
        "Последние доступные текстовые посты:",
    ]
    for index, post in enumerate(snapshot.posts, start=1):
        meta = []
        if post.published_at:
            meta.append(post.published_at)
        if post.url:
            meta.append(post.url)
        meta_text = f" ({', '.join(meta)})" if meta else ""
        parts.append(f"\nПост {index}{meta_text}:\n{post.text}")

    material = "\n".join(parts).strip()
    if len(material) <= max_chars:
        return material

    return material[: max_chars - 15].rstrip() + "\n\n[обрезано]"


class _TelegramPublicChannelParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.posts: list[PublicTelegramPost] = []
        self._current_message: dict[str, str | None] | None = None
        self._message_depth = 0
        self._text_depth = 0
        self._text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        classes = set((attrs_dict.get("class") or "").split())

        if tag == "div" and "tgme_widget_message" in classes and attrs_dict.get("data-post"):
            post_id = attrs_dict["data-post"]
            self._current_message = {
                "post_id": post_id,
                "url": f"https://t.me/{post_id}",
                "published_at": None,
                "text": None,
            }
            self._message_depth = 1
            return

        if self._current_message is not None:
            if tag in VOID_TAGS:
                if self._text_depth and tag == "br":
                    self._text_parts.append("\n")
                return

            self._message_depth += 1

            if tag == "time" and attrs_dict.get("datetime"):
                self._current_message["published_at"] = attrs_dict["datetime"]

            if tag == "div" and "tgme_widget_message_text" in classes:
                self._text_depth = 1
                self._text_parts = []
            elif self._text_depth:
                self._text_depth += 1
                if tag in {"br", "p", "div", "li"}:
                    self._text_parts.append("\n")

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._text_depth and tag == "br":
            self._text_parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._text_depth:
            self._text_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._current_message is None:
            return

        if self._text_depth:
            if tag in {"p", "div", "li"} and self._text_depth > 1:
                self._text_parts.append("\n")
            self._text_depth -= 1
            if self._text_depth == 0:
                self._current_message["text"] = _normalize_post_text("".join(self._text_parts))

        self._message_depth -= 1
        if self._message_depth == 0:
            text = self._current_message.get("text")
            if text:
                self.posts.append(
                    PublicTelegramPost(
                        text=text,
                        url=self._current_message.get("url"),
                        published_at=self._current_message.get("published_at"),
                    )
                )
            self._current_message = None


def _normalize_post_text(text: str) -> str:
    normalized = text.replace("\xa0", " ")
    normalized = re.sub(r"[ \t\r\f\v]+", " ", normalized)
    normalized = re.sub(r" *\n *", "\n", normalized)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    return normalized.strip()
