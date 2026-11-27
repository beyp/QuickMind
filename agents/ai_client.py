"""Groq provider adapter for QuickMind; replaceable with AgentHub gateway later."""
import os
from pathlib import Path

import requests

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODELS_URL = "https://api.groq.com/openai/v1/models"
DEFAULT_TEXT_MODEL = "llama-3.3-70b-versatile"
DEFAULT_VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"


def _setting(name: str) -> str:
    """Environment takes precedence; desktop can also read a local untracked .env."""
    value = os.getenv(name, "").strip()
    if value:
        return value
    path = Path(__file__).resolve().parent.parent / ".env"
    if path.is_file():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if line.strip().startswith(name + "="):
                return line.split("=", 1)[1].strip().strip("\"' ")
    return ""


def get_api_key() -> str:
    key = _setting("GROQ_API_KEY")
    return "" if not key or key.startswith("gsk_xxx") else key


def model_name(vision: bool = False) -> str:
    return (_setting("GROQ_VISION") or DEFAULT_VISION_MODEL) if vision else (
        _setting("GROQ_MODEL") or DEFAULT_TEXT_MODEL
    )


def is_available() -> bool:
    key = get_api_key()
    if not key:
        return False
    try:
        response = requests.get(
            GROQ_MODELS_URL,
            headers={"Authorization": "Bearer " + key},
            timeout=5,
        )
        return response.status_code == 200
    except requests.RequestException:
        return False


def call_ai(messages: list[dict], *, vision: bool = False,
            temperature: float = 0.1, max_tokens: int = 2048) -> str:
    """Return generated text; no silent local fallback when cloud calls fail."""
    key = get_api_key()
    if not key:
        raise RuntimeError("GROQ_API_KEY absent. Configurez la cle dans l'environnement QuickMind.")
    selected_model = model_name(vision)
    try:
        response = requests.post(
            GROQ_URL,
            headers={"Authorization": "Bearer " + key,
                     "Content-Type": "application/json"},
            json={"model": selected_model, "messages": messages,
                  "temperature": temperature, "max_tokens": max_tokens},
            timeout=40,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
    except requests.HTTPError as exc:
        # Never include request headers or credentials in the error.
        code = exc.response.status_code if exc.response is not None else "?"
        raise RuntimeError(f"Groq HTTP {code} (modele {selected_model})") from exc
    except requests.RequestException as exc:
        raise RuntimeError("Groq indisponible (reseau ou delai depasse)") from exc
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("Reponse Groq invalide") from exc
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("Reponse Groq vide")
    return content
