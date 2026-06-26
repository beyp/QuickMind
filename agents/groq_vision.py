"""
QuickMind Agent Vision Groq
Analyse images + texte pour generer des taches et sous-taches.
Inspire d AION-Core brain.py - utilise llama-4-scout pour vision
et llama-3.3-70b pour texte.
"""
import json
import os
import re
from datetime import datetime
from pathlib import Path
import requests

GROQ_URL    = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL  = os.getenv("GROQ_MODEL",  "llama-3.3-70b-versatile")
GROQ_VISION = os.getenv("GROQ_VISION", "meta-llama/llama-4-scout-17b-16e-instruct")

# Charger .env au demarrage pour rendre les vars disponibles
try:
    _env_path = Path(__file__).parent.parent / ".env"
    if _env_path.exists():
        with open(_env_path, "r", encoding="utf-8-sig") as _f:
            for _line in _f:
                _line = _line.strip()
                if _line and not _line.startswith("#") and "=" in _line:
                    _k, _v = _line.split("=", 1)
                    _k = _k.strip()
                    _v = _v.strip().strip('"').strip("'")
                    os.environ.setdefault(_k, _v)
    GROQ_MODEL  = os.getenv("GROQ_MODEL",  "llama-3.3-70b-versatile")
    GROQ_VISION = os.getenv("GROQ_VISION", "meta-llama/llama-4-scout-17b-16e-instruct")
except Exception:
    pass


def _load_token():
    """Charge la cle Groq depuis .env puis variable OS."""
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        try:
            with open(env_path, "r", encoding="utf-8-sig") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("GROQ_API_KEY=") and not line.startswith("#"):
                        val = line.split("=", 1)[1].strip()
                        val = val.strip('"').strip("'")
                        if val and not val.startswith("gsk_xxx"):
                            return val
        except Exception:
            pass
    return os.environ.get("GROQ_API_KEY", "")


def _hdrs(key):
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }


def is_available():
    """Verifie si Groq est configure et accessible."""
    key = _load_token()
    if not key:
        return False
    try:
        r = requests.get(
            "https://api.groq.com/openai/v1/models",
            headers=_hdrs(key),
            timeout=5,
        )
        return r.status_code == 200
    except Exception:
        return False


SYSTEM_PROMPT = """Tu es un assistant de gestion de taches integre dans QuickMind.
Tu analyses textes et images pour generer des taches actionnables.
Reponds UNIQUEMENT en JSON valide sans texte avant ou apres.

Format exact :
{
  "analysis": "resume court de ce que tu as compris (1-2 phrases)",
  "tasks": [
    {
      "title": "titre court et actionnable (max 80 chars)",
      "description": "details de la tache",
      "category": "nom exact de la categorie ou chaine vide",
      "priority": "low|normal|high|urgent",
      "reminder": "YYYY-MM-DDTHH:MM:SS ou null",
      "subtasks": ["sous-tache 1", "sous-tache 2"]
    }
  ]
}

Regles :
- Plusieurs elements distincts : une tache par element
- Un seul sujet complexe : une tache principale avec sous-taches
- Max 8 taches, max 8 sous-taches par tache
- Rappels calcules en ISO8601 par rapport a la date actuelle
- Reponds toujours en francais"""


def analyze_and_generate_tasks(
    prompt,
    image_b64=None,
    image_mime="image/png",
    categories=None,
    default_category="",
    default_reminder=None,
):
    """
    Analyse prompt + image optionnelle via Groq.
    Texte seul : llama-3.3-70b-versatile
    Avec image  : llama-4-scout-17b-16e-instruct (vision)
    Retourne dict avec analysis + tasks.
    """
    key = _load_token()
    if not key:
        raise RuntimeError(
            "GROQ_API_KEY non configure. "
            "Ajoutez GROQ_API_KEY=gsk_xxx dans votre fichier .env"
        )

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    no_reminder = "aucun"
    cats_str    = ", ".join(categories) if categories else ""

    user_text = (
        f"Date actuelle : {now}
"
        f"Categories disponibles : {cats_str}
"
        f"Categorie par defaut : {default_category or 'aucune'}
"
        f"Rappel par defaut : {default_reminder or no_reminder}

"
        f"Demande : {prompt}"
    )

    if image_b64:
        user_content = [
            {"type": "text",      "text": user_text},
            {"type": "image_url", "image_url": {"url": f"data:{image_mime};base64,{image_b64}"}},
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
        GROQ_URL,
        headers=_hdrs(key),
        json={
            "model":       model,
            "messages":    messages,
            "temperature": 0.2,
            "max_tokens":  2048,
        },
        timeout=30,
    )
    r.raise_for_status()

    raw = r.json()["choices"][0]["message"]["content"].strip()
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except Exception:
            pass

    return {"analysis": raw[:200], "tasks": []}
