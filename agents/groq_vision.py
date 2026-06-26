import json, os, re
from datetime import datetime
from pathlib import Path
import requests

GROQ_URL    = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL  = os.getenv("GROQ_MODEL",  "llama-3.3-70b-versatile")
GROQ_VISION = os.getenv("GROQ_VISION", "meta-llama/llama-4-scout-17b-16e-instruct")


def _load_env():
    env_path = Path(__file__).parent.parent / ".env"
    if not env_path.exists(): return
    try:
        with open(env_path, "r", encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    v = v.strip().strip('"').strip("'").strip()
                    os.environ.setdefault(k.strip(), v)
    except Exception:
        pass


_load_env()
GROQ_MODEL  = os.getenv("GROQ_MODEL",  "llama-3.3-70b-versatile")
GROQ_VISION = os.getenv("GROQ_VISION", "meta-llama/llama-4-scout-17b-16e-instruct")


def _load_token():
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        try:
            with open(env_path, "r", encoding="utf-8-sig") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("GROQ_API_KEY=") and not line.startswith("#"):
                        val = line.split("=", 1)[1].strip().strip('"').strip("'").strip()
                        if val and not val.startswith("gsk_xxx"):
                            return val
        except Exception:
            pass
    return os.environ.get("GROQ_API_KEY", "")


def _hdrs(key):
    return {"Authorization": "Bearer " + key, "Content-Type": "application/json"}


def is_available():
    key = _load_token()
    if not key: return False
    try:
        r = requests.get("https://api.groq.com/openai/v1/models",
                         headers=_hdrs(key), timeout=5)
        return r.status_code == 200
    except Exception:
        return False


SYSTEM_PROMPT = (
    "Tu es un assistant de gestion de taches integre dans QuickMind.\n"
    "Tu analyses textes et images pour generer des taches actionnables.\n"
    "Reponds UNIQUEMENT en JSON valide sans texte avant ou apres.\n\n"
    "Format exact :\n"
    "{\n"
    '  \"analysis\": \"resume court (1-2 phrases)\",\n'
    '  \"tasks\": [\n'
    '    {\n'
    '      \"title\": \"titre court max 80 chars\",\n'
    '      \"description\": \"details\",\n'
    '      \"category\": \"categorie exacte ou vide\",\n'
    '      \"priority\": \"low|normal|high|urgent\",\n'
    '      \"reminder\": \"YYYY-MM-DDTHH:MM:SS ou null\",\n'
    '      \"subtasks\": [\"sous-tache 1\", \"sous-tache 2\"]\n'
    '    }\n'
    '  ]\n'
    "}\n\n"
    "Regles :\n"
    "- Plusieurs elements distincts : une tache par element\n"
    "- Un seul sujet complexe : une tache avec sous-taches\n"
    "- Max 8 taches, max 8 sous-taches par tache\n"
    "- Rappels en ISO8601 par rapport a la date actuelle\n"
    "- Reponds toujours en francais"
)


def analyze_and_generate_tasks(
    prompt,
    image_b64=None,
    image_mime="image/png",
    categories=None,
    default_category="",
    default_reminder=None,
):
    key = _load_token()
    if not key:
        raise RuntimeError(
            "GROQ_API_KEY non configure. Ajoutez GROQ_API_KEY=gsk_xxx dans .env"
        )
    now      = datetime.now().strftime("%Y-%m-%d %H:%M")
    cats_str = ", ".join(categories) if categories else ""
    user_text = (
        "Date actuelle : " + now + "\n"
        "Categories disponibles : " + cats_str + "\n"
        "Categorie par defaut : " + (default_category or "aucune") + "\n"
        "Rappel par defaut : " + (default_reminder or "aucun") + "\n\n"
        "Demande : " + prompt
    )
    if image_b64:
        user_content = [
            {"type": "text", "text": user_text},
            {"type": "image_url", "image_url":
                {"url": "data:" + image_mime + ";base64," + image_b64}},
        ]
        model = GROQ_VISION
    else:
        user_content = user_text
        model = GROQ_MODEL
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": user_content},
    ]
    r = requests.post(
        GROQ_URL, headers=_hdrs(key),
        json={"model": model, "messages": messages,
              "temperature": 0.2, "max_tokens": 2048},
        timeout=30,
    )
    r.raise_for_status()
    raw = r.json()["choices"][0]["message"]["content"].strip()
    m   = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        try: return json.loads(m.group())
        except Exception: pass
    return {"analysis": raw[:200], "tasks": []}
