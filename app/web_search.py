import requests
from bs4 import BeautifulSoup
from ddgs import DDGS

from app.config import (
    WEB_ENABLED,
    WEB_FETCH_MAX_PAGES,
    WEB_SEARCH_MAX_RESULTS,
    WEB_TIMEOUT,
)


class WebSearchError(Exception):
    pass


def search_web(query: str, max_results: int | None = None) -> list[dict]:
    if not WEB_ENABLED:
        raise WebSearchError("web_disabled")

    max_results = max_results or WEB_SEARCH_MAX_RESULTS

    try:
        with DDGS(timeout=WEB_TIMEOUT) as ddgs:
            results = ddgs.text(
                query,
                region="ru-ru",
                safesearch="moderate",
                max_results=max_results,
            )
    except Exception as error:
        raise WebSearchError("search_failed") from error

    cleaned = []

    for item in results or []:
        title = str(item.get("title", "")).strip()
        url = str(item.get("href", "")).strip()
        snippet = str(item.get("body", "")).strip()

        if not url:
            continue

        cleaned.append({
            "title": title,
            "url": url,
            "snippet": snippet,
        })

    if not cleaned:
        raise WebSearchError("no_results")

    return cleaned


def fetch_page_text(url: str) -> str:
    try:
        response = requests.get(
            url,
            timeout=WEB_TIMEOUT,
            headers={
                "User-Agent": "Mozilla/5.0"
            },
        )
        response.raise_for_status()
    except requests.RequestException:
        return ""

    soup = BeautifulSoup(response.text, "html.parser")

    # Убираем шумные теги, чтобы взять только смысловой текст.
    for tag in soup(["script", "style", "noscript", "header", "footer", "nav", "aside"]):
        tag.decompose()

    main_block = (
            soup.find("main")
            or soup.find("article")
            or soup.body
            or soup
    )

    text = main_block.get_text(separator=" ", strip=True)
    text = " ".join(text.split())

    # Слишком длинный текст модели не нужен — берём сжатый фрагмент.
    return text[:2500]


def build_web_context(results: list[dict]) -> str:
    lines = [
        "Ниже дана внешняя справка из интернет-источников.",
        "Используй её как опору, но не копируй дословно.",
        "Если данные неполные, спорные или разрозненные — честно скажи об этом.",
        "",
    ]

    for index, item in enumerate(results[:WEB_FETCH_MAX_PAGES], start=1):
        lines.append(f"Результат {index}")
        lines.append(f"Заголовок: {item['title']}")
        lines.append(f"Ссылка: {item['url']}")

        if item["snippet"]:
            lines.append(f"Краткая справка: {item['snippet']}")

        page_text = fetch_page_text(item["url"])
        if page_text:
            lines.append(f"Фрагмент страницы: {page_text}")

        lines.append("")

    return "\n".join(lines).strip()