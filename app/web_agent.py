from dataclasses import dataclass

from app.chat_core import stream_chat_response


@dataclass(frozen=True)
class WebPlan:
    need_web: bool
    search_query: str
    note: str


def _extract_field(text: str, field_name: str) -> str:
    prefix = f"{field_name}:"
    for line in text.splitlines():
        if line.startswith(prefix):
            return line[len(prefix):].strip()
    return ""


def decide_web_plan(messages, user_text: str) -> WebPlan:
    planner_messages = list(messages)

    planner_messages.append({
        "role": "system",
        "content": (
            "Сейчас это внутренний черновой шаг перед ответом.\n"
            "Не отвечай пользователю напрямую.\n"
            "Сначала спокойно реши, хватает ли тебе текущего контекста.\n"
            "Если да — внешний поиск не нужен.\n"
            "Если нет — предложи короткий и полезный поисковый запрос.\n\n"
            "Верни ответ строго в 3 строках:\n"
            "WEB: yes или no\n"
            "QUERY: короткий поисковый запрос или пусто\n"
            "NOTE: очень коротко зачем это нужно\n\n"
            "Не добавляй ничего сверх этих 3 строк."
        )
    })

    planner_messages.append({
        "role": "system",
        "content": (
            "Поиск особенно полезен, когда пользователь спрашивает о:\n"
            "- конкретном тайтле, персонаже, игре, авторе;\n"
            "- свежих фактах, новостях, рейтингах, датах, патчах;\n"
            "- рекомендациях, сравнениях и подборках, где полезен внешний контекст.\n"
            "Но для простой тёплой беседы поиск не нужен."
        )
    })

    planner_messages.append({"role": "user", "content": user_text})

    raw = stream_chat_response(planner_messages).strip()

    web_value = _extract_field(raw, "WEB").lower()
    query_value = _extract_field(raw, "QUERY")
    note_value = _extract_field(raw, "NOTE")

    return WebPlan(
        need_web=(web_value == "yes"),
        search_query=query_value,
        note=note_value or "внутренняя оценка контекста",
    )