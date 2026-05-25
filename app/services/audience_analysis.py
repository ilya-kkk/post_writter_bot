from typing import Any

from app.core.llm import complete_text, parse_json_object, render_prompt


async def analyze_audience(source_material: str) -> dict[str, Any]:
    prompt = render_prompt("audience_analysis.md", SOURCE_MATERIAL=source_material)
    response = await complete_text(prompt, temperature=0.3)
    if response is None:
        return mock_audience_analysis(source_material)

    data = parse_json_object(response)
    return normalize_audience_profile(data)


def normalize_audience_profile(data: dict[str, Any]) -> dict[str, Any]:
    tone = data.get("tone_of_voice") or {}
    if not isinstance(tone, dict):
        tone = {"style": str(tone), "format": "", "phrases": [], "avoid": []}

    return {
        "niche": str(data.get("niche") or "Ниша не определена"),
        "audience_summary": str(data.get("audience_summary") or "Аудитория требует уточнения."),
        "segments": _as_list(data.get("segments")),
        "pains": _as_list(data.get("pains")),
        "desires": _as_list(data.get("desires")),
        "beliefs": _as_list(data.get("beliefs")),
        "objections": _as_list(data.get("objections")),
        "tone_of_voice": {
            "style": str(tone.get("style") or "живой, прямой"),
            "format": str(tone.get("format") or "короткие абзацы Telegram"),
            "phrases": _as_list(tone.get("phrases")),
            "avoid": _as_list(tone.get("avoid")),
        },
        "content_patterns": _as_list(data.get("content_patterns")),
    }


def mock_audience_analysis(source_material: str) -> dict[str, Any]:
    snippet = source_material.strip().replace("\n", " ")[:180]
    data = {
        "niche": "Экспертный Telegram-контент",
        "audience_summary": (
            "Люди, которые читают канал, хотят быстрее понимать пользу продукта, "
            "видеть практические примеры и не тратить время на общие советы."
        ),
        "segments": ["Предприниматели", "Эксперты", "Маркетологи и редакторы"],
        "pains": [
            "Трудно регулярно придумывать темы для постов",
            "Тексты звучат слишком общо и не приводят заявки",
            "Нет ясного понимания, какие боли аудитории подсвечивать",
        ],
        "desires": [
            "Получать готовые идеи без долгого брифинга",
            "Писать живым языком и сохранять экспертность",
            "Понимать, какой пост может привести к продаже",
        ],
        "beliefs": [
            "Пост должен быть полезным, а не просто продающим",
            "Аудитория быстро чувствует шаблонность",
        ],
        "objections": [
            "Боюсь, что текст будет похож на генератор",
            "Не уверен, что бот поймет мой рынок",
        ],
        "tone_of_voice": {
            "style": "прямой, конкретный, без канцелярита",
            "format": "короткие абзацы, тезисы, сильный первый экран",
            "phrases": ["смотри", "разберем на примере", "главное здесь"],
            "avoid": ["в современном мире", "индивидуальный подход", "уникальное решение"],
        },
        "content_patterns": [
            "хук через знакомую боль",
            "короткий разбор ошибки",
            "пример из практики",
        ],
        "source_hint": snippet,
    }
    return normalize_audience_profile(data)


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if item]
    return [str(value)]
