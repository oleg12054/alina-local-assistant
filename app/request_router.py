import re
from dataclasses import dataclass


MEDIA_HINTS = [
    "аниме", "сериал", "фильм", "игра", "тайтл", "манга", "ранобэ",
    "новелла", "персонаж", "герой", "героиня", "сезон", "эпизод",
    "серия", "саундтрек", "опенинг", "эндинг",
]

FACTUAL_HINTS = [
    "кто такой", "что это", "когда вышел", "дата выхода",
    "сколько сезонов", "какой рейтинг", "автор", "студия",
    "жанр", "актуально", "сейчас", "последние новости",
]

GAME_HINTS = [
    "билд", "сборка", "гайд", "команда", "мета",
    "патч", "ротация", "артефакты", "оружие", "класс", "навыки",
]


@dataclass(frozen=True)
class RequestContext:
    topic: str
    risk_of_hallucination: bool
    needs_soft_honesty_hint: bool


def normalize_text(text: str) -> str:
    return " ".join(text.lower().strip().split())


def has_quoted_title(text: str) -> bool:
    return bool(re.search(r'["«].+?["»]', text))


def analyze_request(user_text: str) -> RequestContext:
    text = normalize_text(user_text)

    has_media = any(word in text for word in MEDIA_HINTS)
    has_factual = any(word in text for word in FACTUAL_HINTS)
    has_game = any(word in text for word in GAME_HINTS)
    has_title = has_quoted_title(user_text)

    if has_game:
        return RequestContext(
            topic="game",
            risk_of_hallucination=True,
            needs_soft_honesty_hint=True,
        )

    if has_factual:
        return RequestContext(
            topic="factual",
            risk_of_hallucination=True,
            needs_soft_honesty_hint=True,
        )

    if has_media or has_title:
        return RequestContext(
            topic="media",
            risk_of_hallucination=True,
            needs_soft_honesty_hint=True,
        )

    return RequestContext(
        topic="chat",
        risk_of_hallucination=False,
        needs_soft_honesty_hint=False,
    )