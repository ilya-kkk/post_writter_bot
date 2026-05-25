from typing import Any

from app.db.models import AudienceProfile, Idea


def format_audience_profile(profile: AudienceProfile) -> str:
    tone = profile.tone_json or {}
    pains = _bullet_list(profile.pains_json)
    desires = _bullet_list(profile.desires_json)
    style = tone.get("style") or "живой Telegram-стиль"

    return (
        "Я понял аудиторию так:\n\n"
        f"Ниша: {profile.niche}\n"
        f"Кто читает: {profile.audience_summary}\n\n"
        f"Главные боли:\n{pains}\n\n"
        f"Чего хотят:\n{desires}\n\n"
        f"Стиль: {style}\n\n"
        "Теперь подберу идеи для постов."
    )


def format_ideas(ideas: list[Idea]) -> str:
    lines = ["Я подобрал идеи для нового поста. Выбери одну:\n"]
    for index, idea in enumerate(ideas, start=1):
        lines.append(f"{index}. {idea.title}\n{idea.description}")
    return "\n\n".join(lines)


def profile_to_dict(profile: AudienceProfile) -> dict[str, Any]:
    data = dict(profile.raw_analysis_json or {})
    data.update(
        {
            "niche": profile.niche,
            "audience_summary": profile.audience_summary,
            "pains": profile.pains_json or [],
            "desires": profile.desires_json or [],
            "beliefs": profile.beliefs_json or [],
            "tone_of_voice": profile.tone_json or {},
        }
    )
    return data


def idea_to_dict(idea: Idea) -> dict[str, Any]:
    return {
        "title": idea.title,
        "description": idea.description,
        "angle": idea.angle,
    }


def free_post_explanation() -> str:
    return (
        "Готово.\n\n"
        "Этот пост сделан на основе анализа твоей аудитории. Это бесплатный пример.\n\n"
        "В подписке можно:\n"
        "— генерировать посты регулярно;\n"
        "— получать идеи без лимитов;\n"
        "— писать в выбранном стиле;\n"
        "— улучшать свои черновики;\n"
        "— делать посты из голосовых заметок."
    )


def _bullet_list(items: list[str] | None) -> str:
    values = items or ["требует уточнения"]
    return "\n".join(f"— {item}" for item in values[:5])
