from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup


def main_menu_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Меню")]],
        resize_keyboard=True,
        input_field_placeholder="Нажми Меню или напиши текст",
    )


def user_type_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="У меня есть канал", callback_data="user_type:channel")],
            [InlineKeyboardButton(text="Пишу для клиента", callback_data="user_type:client")],
            [InlineKeyboardButton(text="Хочу протестировать на нише", callback_data="user_type:niche")],
        ]
    )


def analysis_confirmation_keyboard(project_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Да, всё верно", callback_data=f"analysis:confirm:{project_id}")],
            [InlineKeyboardButton(text="Изменить описание", callback_data=f"analysis:edit:{project_id}")],
        ]
    )


def ideas_keyboard(count: int = 6, project_id: int | None = None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for start in range(1, count + 1, 3):
        rows.append(
            [
                InlineKeyboardButton(text=str(i), callback_data=_idea_callback_data(i, project_id))
                for i in range(start, min(start + 3, count + 1))
            ]
        )
    rows.append([InlineKeyboardButton(text="Сгенерировать другие", callback_data=_regenerate_callback_data(project_id))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _idea_callback_data(index: int, project_id: int | None) -> str:
    if project_id is None:
        return f"idea:select:{index}"
    return f"idea:select:{project_id}:{index}"


def _regenerate_callback_data(project_id: int | None) -> str:
    if project_id is None:
        return "ideas:regenerate"
    return f"ideas:regenerate:{project_id}"


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


def subscription_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Мои проекты", callback_data="menu:projects")],
            [InlineKeyboardButton(text="Создать новый проект", callback_data="menu:new_project")],
            [InlineKeyboardButton(text="Статус подписки", callback_data="menu:status")],
            [InlineKeyboardButton(text="Тарифы", callback_data="menu:tariffs")],
        ]
    )


def project_actions_keyboard(project_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Сгенерировать темы", callback_data=f"project:ideas:{project_id}")],
            [InlineKeyboardButton(text="Написать свою тему", callback_data=f"project:custom_topic:{project_id}")],
            [InlineKeyboardButton(text="Мои проекты", callback_data="menu:projects")],
            [InlineKeyboardButton(text="Создать новый проект", callback_data="menu:new_project")],
        ]
    )


def manual_examples_start_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Перешлю посты", callback_data="examples:manual")],
        ]
    )


def manual_examples_submit_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Готово, отправить", callback_data="examples:submit")],
        ]
    )
