from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from app.bot.keyboards import main_menu_reply_keyboard, payment_keyboard, subscription_menu_keyboard, tariff_keyboard
from app.bot.messages import payment_created_text, paywall_text, subscription_activated_text, subscription_menu_text
from app.bot.states import BotStates
from app.db.session import session_factory
from app.services.payment_service import activate_mock_payment, create_mock_payment

router = Router()


@router.callback_query(F.data.startswith("tariff:"))
async def select_tariff(callback: CallbackQuery, state: FSMContext) -> None:
    tariff_code = callback.data.split(":", 1)[1]
    async with session_factory()() as session:
        try:
            payment = await create_mock_payment(session, callback.from_user, tariff_code)
            await session.commit()
        except ValueError:
            await session.rollback()
            await callback.answer("Тариф не найден")
            return

    await state.set_state(BotStates.payment_pending)
    await callback.message.answer(
        payment_created_text(payment.tariff.name, payment.amount),
        reply_markup=payment_keyboard(payment.id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("payment:mock_paid:"))
async def mock_paid(callback: CallbackQuery, state: FSMContext) -> None:
    payment_id = int(callback.data.rsplit(":", 1)[1])
    async with session_factory()() as session:
        try:
            subscription = await activate_mock_payment(session, payment_id, callback.from_user.id)
            await session.commit()
        except ValueError:
            await session.rollback()
            await callback.answer("Платеж не найден")
            return

    await state.set_state(BotStates.subscribed)
    await callback.message.answer(
        subscription_activated_text(subscription.projects_limit, subscription.posts_limit),
        reply_markup=main_menu_reply_keyboard(),
    )
    await callback.message.answer(
        subscription_menu_text(),
        reply_markup=subscription_menu_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "payment:back_to_tariffs")
async def back_to_tariffs(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(BotStates.wait_tariff_selection)
    await callback.message.answer(paywall_text(), reply_markup=tariff_keyboard())
    await callback.answer()


@router.callback_query(F.data == "paywall:extra_free")
async def extra_free_post(callback: CallbackQuery) -> None:
    await callback.message.answer("Ещё один бесплатный пост доступен после оплаты.")
    await callback.answer()
