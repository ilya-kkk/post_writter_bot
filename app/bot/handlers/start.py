from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from app.bot.keyboards import user_type_keyboard
from app.bot.states import BotStates, UserState
from app.db.session import session_factory
from app.services.project_service import upsert_user

router = Router()


@router.message(CommandStart())
async def start(message: Message, state: FSMContext) -> None:
    async with session_factory()() as session:
        await upsert_user(session, message.from_user, state=UserState.ASK_USER_TYPE)
        await session.commit()

    await state.set_state(BotStates.ask_user_type)
    await message.answer(
        "Привет! Я помогу сделать готовый Telegram-пост под твою аудиторию.\n\n"
        "Для начала выбери сценарий:",
        reply_markup=user_type_keyboard(),
    )
