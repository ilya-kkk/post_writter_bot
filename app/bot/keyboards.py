from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def user_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="У меня есть канал", callback_data="user_type:channel")],
            [InlineKeyboardButton(text="Пишу для клиента", callback_data="user_type:client")],
            [InlineKeyboardButton(text="Хочу протестировать на нише", callback_data="user_type:niche")],
        ]
    )


def analysis_confirmation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Да, всё верно", callback_data="analysis:confirm")],
            [InlineKeyboardButton(text="Изменить описание", callback_data="analysis:edit")],
        ]
    )


def ideas_keyboard(count: int = 6) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for start in range(1, count + 1, 3):
        rows.append(
            [
                InlineKeyboardButton(text=str(i), callback_data=f"idea:select:{i}")
                for i in range(start, min(start + 3, count + 1))
            ]
        )
    rows.append([InlineKeyboardButton(text="Сгенерировать другие", callback_data="ideas:regenerate")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def tariff_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Лайт — 1790 ₽", callback_data="tariff:lite")],
            [InlineKeyboardButton(text="Стандарт — 3190 ₽", callback_data="tariff:standard")],
            [InlineKeyboardButton(text="Хочу ещё 1 пост", callback_data="paywall:extra_free")],
        ]
    )


def payment_keyboard(payment_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Оплатить / mock paid", callback_data=f"payment:mock_paid:{payment_id}")],
            [InlineKeyboardButton(text="Назад к тарифам", callback_data="payment:back_to_tariffs")],
        ]
    )
