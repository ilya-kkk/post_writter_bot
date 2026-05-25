from datetime import UTC, datetime, timedelta

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.keyboards import tariff_keyboard
from app.core.config import settings
from app.db.models import FollowupEvent, Subscription, User

REAL_SCHEDULE = [
    ("social_proof", timedelta(hours=1)),
    ("bonus", timedelta(hours=7)),
    ("case", timedelta(hours=18)),
    ("discount", timedelta(hours=24)),
    ("deadline", timedelta(hours=36)),
    ("last_chance", timedelta(hours=47)),
]

FAST_SCHEDULE = [
    ("social_proof", timedelta(minutes=2)),
    ("bonus", timedelta(minutes=5)),
    ("case", timedelta(minutes=10)),
    ("discount", timedelta(minutes=20)),
    ("deadline", timedelta(minutes=30)),
    ("last_chance", timedelta(minutes=47)),
]

FOLLOWUP_MESSAGES = {
    "social_proof": (
        "Пользователи обычно удивляются именно первому результату.\n\n"
        "Бот не просто “пишет текст”, а сначала понимает:\n"
        "— кто аудитория;\n"
        "— чего она боится;\n"
        "— что хочет купить;\n"
        "— каким языком с ней говорить.\n\n"
        "Поэтому посты получаются не пластиковыми, а похожими на нормальный продающий контент.\n\n"
        "Выбери тариф, чтобы продолжить:"
    ),
    "bonus": (
        "Бонус за оплату в течение 48 часов:\n\n"
        "получишь набор промптов для продающих Telegram-постов:\n"
        "— пост через боль;\n"
        "— пост через историю;\n"
        "— пост через кейс;\n"
        "— пост через разбор ошибки;\n"
        "— пост с CTA в личку."
    ),
    "case": (
        "Почему это может окупиться быстро:\n\n"
        "если один нормальный пост приводит хотя бы одну заявку,\n"
        "а твой продукт стоит больше подписки,\n"
        "бот окупается с первой продажи.\n\n"
        "Главное — писать регулярно и попадать в боли аудитории."
    ),
    "discount": (
        "На 24 часа доступна скидка 10%.\n\n"
        "Лайт: 1790 ₽ → 1611 ₽\n"
        "Стандарт: 3190 ₽ → 2871 ₽"
    ),
    "deadline": (
        "Скидка и бонус сгорят через 12 часов.\n\n"
        "Если хочешь продолжить генерировать посты на основе анализа аудитории, "
        "выбери тариф сейчас."
    ),
    "last_chance": (
        "Последнее напоминание по MVP-предложению.\n\n"
        "Можно оставить всё как есть и вернуться позже. "
        "А можно включить регулярную генерацию постов уже сейчас."
    ),
}


def followup_schedule() -> list[tuple[str, timedelta]]:
    return FAST_SCHEDULE if settings.followup_fast_mode else REAL_SCHEDULE


async def create_followup_events(session: AsyncSession, user_id: int) -> None:
    now = datetime.now(UTC)
    for event_type, delay in followup_schedule():
        existing = await session.scalar(
            select(FollowupEvent).where(
                FollowupEvent.user_id == user_id,
                FollowupEvent.event_type == event_type,
            )
        )
        if existing:
            if existing.status == "pending":
                existing.scheduled_at = now + delay
            continue

        session.add(
            FollowupEvent(
                user_id=user_id,
                event_type=event_type,
                scheduled_at=now + delay,
                status="pending",
            )
        )


async def cancel_followups_for_user(session: AsyncSession, user_id: int) -> None:
    events = await session.scalars(
        select(FollowupEvent).where(FollowupEvent.user_id == user_id, FollowupEvent.status == "pending")
    )
    for event in events:
        event.status = "canceled"


async def get_due_followups(session: AsyncSession, limit: int = 20) -> list[FollowupEvent]:
    now = datetime.now(UTC)
    return list(
        await session.scalars(
            select(FollowupEvent)
            .where(FollowupEvent.status == "pending", FollowupEvent.scheduled_at <= now)
            .order_by(FollowupEvent.scheduled_at.asc())
            .limit(limit)
        )
    )


async def send_followup_event(session: AsyncSession, bot: Bot, event: FollowupEvent) -> None:
    user = await session.get(User, event.user_id)
    if user is None:
        event.status = "failed"
        event.sent_at = datetime.now(UTC)
        return

    if await _has_active_subscription(session, user.id):
        event.status = "canceled"
        return

    message = FOLLOWUP_MESSAGES.get(event.event_type)
    if message is None:
        event.status = "failed"
        event.sent_at = datetime.now(UTC)
        return

    try:
        await bot.send_message(user.telegram_id, message, reply_markup=tariff_keyboard())
    except TelegramForbiddenError:
        event.status = "blocked"
        event.sent_at = datetime.now(UTC)
        return

    event.status = "sent"
    event.sent_at = datetime.now(UTC)


async def _has_active_subscription(session: AsyncSession, user_id: int) -> bool:
    subscription = await session.scalar(
        select(Subscription).where(
            Subscription.user_id == user_id,
            Subscription.status == "active",
            Subscription.expires_at > datetime.now(UTC),
        )
    )
    return subscription is not None
