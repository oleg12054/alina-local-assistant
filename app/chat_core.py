import json
import requests

from app.prompt import build_system_prompt
from app.config import MODEL_NAME, OLLAMA_URL, REQUEST_TIMEOUT, KEEP_ALIVE



SYSTEM_PROMPT = build_system_prompt()


class OllamaUnavailableError(Exception):
    pass


class ModelUnavailableError(Exception):
    pass


def create_initial_messages():
    return [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]


def stream_chat_response(messages):
    try:
        with requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL_NAME,
                "messages": messages,
                "stream": True,
                "keep_alive": KEEP_ALIVE
            },
            stream=True,
            timeout=REQUEST_TIMEOUT
        ) as response:
            # Попробуем отдельно распознать случай, когда модели нет
            if response.status_code == 404:
                try:
                    data = response.json()
                    error_text = str(data.get("error", ""))
                except ValueError:
                    error_text = ""

                if "not found" in error_text.lower():
                    raise ModelUnavailableError(MODEL_NAME)

            response.raise_for_status()

            assistant_text = ""

            for line in response.iter_lines():
                if not line:
                    continue

                chunk = json.loads(line.decode("utf-8"))

                if "message" in chunk and "content" in chunk["message"]:
                    piece = chunk["message"]["content"]
                    assistant_text += piece

            return assistant_text

    except requests.ConnectionError as error:
        raise OllamaUnavailableError("ollama_unavailable") from error
    except requests.RequestException as error:
        raise OllamaUnavailableError("ollama_unavailable") from error


def unload_model():
    try:
        requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL_NAME,
                "messages": [],
                "stream": False,
                "keep_alive": 0
            },
            timeout=REQUEST_TIMEOUT
        )
    except requests.RequestException:
        pass

def stream_chat_chunks(messages):
    try:
        with requests.post(
                OLLAMA_URL,
                json={
                    "model": MODEL_NAME,
                    "messages": messages,
                    "stream": True,
                    "keep_alive": KEEP_ALIVE
                },
                stream=True,
                timeout=REQUEST_TIMEOUT
        ) as response:
            if response.status_code == 404:
                try:
                    data = response.json()
                    error_text = str(data.get("error", ""))
                except ValueError:
                    error_text = ""

                if "not found" in error_text.lower():
                    raise ModelUnavailableError(MODEL_NAME)

            response.raise_for_status()

            for line in response.iter_lines():
                if not line:
                    continue

                chunk = json.loads(line.decode("utf-8"))

                if "message" in chunk and "content" in chunk["message"]:
                    piece = chunk["message"]["content"]
                    if piece:
                        yield piece

    except requests.ConnectionError as error:
        raise OllamaUnavailableError("ollama_unavailable") from error
    except requests.RequestException as error:
        raise OllamaUnavailableError("ollama_unavailable") from error
