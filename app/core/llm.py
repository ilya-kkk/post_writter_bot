import json
import logging
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from app.core.config import settings

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
logger = logging.getLogger(__name__)


def render_prompt(name: str, **values: str) -> str:
    prompt = (PROMPTS_DIR / name).read_text(encoding="utf-8")
    for key, value in values.items():
        prompt = prompt.replace("{{" + key + "}}", value)
    return prompt


async def complete_text(prompt: str, temperature: float = 0.7) -> str | None:
    if not settings.openai_api_key:
        return None

    try:
        client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url or None,
            timeout=settings.openai_timeout_seconds,
            max_retries=1,
        )
        response = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
        )
        return response.choices[0].message.content or ""
    except Exception as exc:
        logger.warning("LLM request failed, falling back to mock response: %s", exc)
        return None


def dumps_for_prompt(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def parse_json_object(text: str) -> dict[str, Any]:
    value = _parse_json(text)
    if not isinstance(value, dict):
        raise ValueError("LLM response is not a JSON object")
    return value


def parse_json_array(text: str) -> list[dict[str, Any]]:
    value = _parse_json(text)
    if not isinstance(value, list):
        raise ValueError("LLM response is not a JSON array")
    return [item for item in value if isinstance(item, dict)]


def _parse_json(text: str) -> Any:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        cleaned = cleaned.removeprefix("json").strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    object_start = cleaned.find("{")
    object_end = cleaned.rfind("}")
    array_start = cleaned.find("[")
    array_end = cleaned.rfind("]")

    if array_start != -1 and array_end > array_start:
        return json.loads(cleaned[array_start : array_end + 1])
    if object_start != -1 and object_end > object_start:
        return json.loads(cleaned[object_start : object_end + 1])

    raise ValueError("LLM response does not contain valid JSON")
