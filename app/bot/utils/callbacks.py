import logging

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

logger = logging.getLogger(__name__)

MAX_MESSAGE_TEXT_LENGTH = 4096
CHOICE_PREFIX = "Вы выбрали:"


async def mark_callback_chosen(callback: CallbackQuery, choice_text: str | None = None) -> None:
    message = callback.message
    if not isinstance(message, Message):
        return

    choice = choice_text or _button_text_for_callback(message.reply_markup, callback.data) or "действие"
    marker = f"{CHOICE_PREFIX} {choice}"

    text = message.text
    caption = message.caption
    if text:
        await _edit_message_text(message, _append_marker(text, marker))
        return

    if caption:
        await _edit_message_caption(message, _append_marker(caption, marker))
        return

    await _remove_reply_markup(message)


async def _edit_message_text(message: Message, text: str) -> None:
    try:
        await message.edit_text(text, reply_markup=None)
    except TelegramBadRequest as exc:
        logger.info("callback_mark.edit_text_failed chat_id=%s message_id=%s error=%s", message.chat.id, message.message_id, exc)
        await _remove_reply_markup(message)


async def _edit_message_caption(message: Message, caption: str) -> None:
    try:
        await message.edit_caption(caption=caption, reply_markup=None)
    except TelegramBadRequest as exc:
        logger.info(
            "callback_mark.edit_caption_failed chat_id=%s message_id=%s error=%s",
            message.chat.id,
            message.message_id,
            exc,
        )
        await _remove_reply_markup(message)


async def _remove_reply_markup(message: Message) -> None:
    try:
        await message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest as exc:
        logger.info(
            "callback_mark.remove_markup_failed chat_id=%s message_id=%s error=%s",
            message.chat.id,
            message.message_id,
            exc,
        )


def _append_marker(text: str, marker: str) -> str:
    if CHOICE_PREFIX in text:
        return text

    suffix = f"\n\n{marker}"
    if len(text) + len(suffix) <= MAX_MESSAGE_TEXT_LENGTH:
        return text + suffix

    return text[: MAX_MESSAGE_TEXT_LENGTH - len(suffix) - 1].rstrip() + "…" + suffix


def _button_text_for_callback(reply_markup: InlineKeyboardMarkup | None, callback_data: str | None) -> str | None:
    if reply_markup is None or callback_data is None:
        return None

    for row in reply_markup.inline_keyboard:
        for button in row:
            if button.callback_data == callback_data:
                return button.text
    return None
