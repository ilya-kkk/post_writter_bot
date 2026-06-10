import logging
from typing import Any

from app.core.llm import complete_text, dumps_for_prompt, parse_json_array, render_prompt

logger = logging.getLogger(__name__)


async def generate_ideas(audience_profile: dict[str, Any], count: int = 6) -> list[dict[str, str]]:
    prompt = render_prompt(
        "generate_ideas.md",
        AUDIENCE_PROFILE=dumps_for_prompt(audience_profile),
        COUNT=str(count),
    )
    response = await complete_text(prompt, temperature=0.8)
    if response is None:
        return mock_ideas(audience_profile, count)

    try:
        ideas = parse_json_array(response)
    except ValueError as exc:
        logger.warning("Ideas response is not valid JSON, falling back to mock: %s", exc)
        return mock_ideas(audience_profile, count)
    normalized = [normalize_idea(item) for item in ideas]
    return normalized[:count] or mock_ideas(audience_profile, count)


def normalize_idea(item: dict[str, Any]) -> dict[str, str]:
    title = str(item.get("title") or "Идея поста")
    description = str(item.get("description") or item.get("target_pain") or "Короткий разбор боли аудитории.")
    angle = str(item.get("angle") or item.get("suggested_cta") or "Показать проблему и предложить следующий шаг.")
    return {
        "title": title,
        "description": description,
        "target_pain": str(item.get("target_pain") or ""),
        "angle": angle,
        "suggested_cta": str(item.get("suggested_cta") or "Написать в личку за разбором"),
    }


def mock_ideas(audience_profile: dict[str, Any], count: int = 6) -> list[dict[str, str]]:
    pains = audience_profile.get("pains") or ["нет регулярных идей", "текст не продает", "сложно попасть в аудиторию"]
    base = [
        (
            "Почему посты не приводят заявки",
            "Разобрать типичную ошибку: автор пишет о себе, а не о боли читателя.",
            pains[0],
            "Через узнаваемую ситуацию показать, что пост начинается с аудитории.",
        ),
        (
            "Как понять, что аудитория готова купить",
            "Показать сигналы спроса в комментариях, вопросах и личных сообщениях.",
            pains[min(1, len(pains) - 1)],
            "Дать простой чек-лист и привести к регулярной генерации идей.",
        ),
        (
            "Один пост вместо недели прогрева",
            "Объяснить, как один точный инсайт может заменить много проходных публикаций.",
            pains[min(2, len(pains) - 1)],
            "Сравнить общий текст и текст, собранный под боли аудитории.",
        ),
        (
            "Почему шаблонные тексты считываются сразу",
            "Показать разницу между пластиковым текстом и живым Telegram-постом.",
            "страх получить шаблонный контент",
            "Через примеры фраз объяснить роль тона.",
        ),
        (
            "Как выбрать тему, если в голове пусто",
            "Дать метод: боль, желание, возражение, пример, CTA.",
            "непонятно, о чем писать регулярно",
            "Позиционировать бота как помощника в регулярности.",
        ),
        (
            "Пост, который продает без давления",
            "Показать структуру: история, боль, вывод, мягкий CTA.",
            "не хочется выглядеть навязчиво",
            "Снять страх продаж и показать мягкий сценарий.",
        ),
    ]
    return [
        {
            "title": title,
            "description": description,
            "target_pain": target_pain,
            "angle": angle,
            "suggested_cta": "Выбрать тариф и получать такие посты регулярно",
        }
        for title, description, target_pain, angle in base[:count]
    ]
