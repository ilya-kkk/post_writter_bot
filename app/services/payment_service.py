from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.states import UserState
from app.db.models import Payment, Subscription, Tariff, User
from app.services.followup_service import cancel_followups_for_user
from app.services.project_service import upsert_user


async def get_active_tariff(session: AsyncSession, code: str) -> Tariff | None:
    return await session.scalar(select(Tariff).where(Tariff.code == code, Tariff.is_active.is_(True)))


async def create_mock_payment(session: AsyncSession, tg_user, tariff_code: str) -> Payment:
    user = await upsert_user(session, tg_user, state=UserState.PAYMENT_PENDING)
    tariff = await get_active_tariff(session, tariff_code)
    if tariff is None:
        raise ValueError("Tariff not found")

    payment = Payment(
        user_id=user.id,
        tariff_id=tariff.id,
        tariff=tariff,
        amount=tariff.monthly_price,
        currency="RUB",
        status="pending",
        provider="mock",
    )
    session.add(payment)
    await session.flush()
    payment.external_payment_id = f"mock-{payment.id}"
    payment.payment_url = f"mock://payments/{payment.id}"
    return payment


async def activate_mock_payment(session: AsyncSession, payment_id: int, telegram_id: int) -> Subscription:
    payment = await session.get(Payment, payment_id)
    if payment is None:
        raise ValueError("Payment not found")

    user = await session.get(User, payment.user_id)
    if user is None or user.telegram_id != telegram_id:
        raise ValueError("Payment does not belong to this user")

    tariff = await session.get(Tariff, payment.tariff_id)
    if tariff is None:
        raise ValueError("Tariff not found")

    now = datetime.now(UTC)
    payment.status = "paid"
    payment.paid_at = now
    user.current_state = UserState.SUBSCRIBED
    await cancel_followups_for_user(session, user.id)

    existing = await session.scalars(
        select(Subscription).where(Subscription.user_id == user.id, Subscription.status == "active")
    )
    for subscription in existing:
        subscription.status = "inactive"

    subscription = Subscription(
        user_id=user.id,
        tariff_id=tariff.id,
        status="active",
        projects_limit=tariff.projects_limit,
        posts_limit=tariff.posts_limit,
        posts_used=0,
        started_at=now,
        expires_at=now + timedelta(days=30),
    )
    session.add(subscription)
    await session.flush()
    return subscription
