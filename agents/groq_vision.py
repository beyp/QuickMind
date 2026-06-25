"""
QuickMind Agent Vision Groq
Analyse images + texte pour generer des taches et sous-taches.
Inspire d AION-Core brain.py avec llama-4-scout vision.
"""
import json
import os
import re
from datetime import datetime
from pathlib import Path
import requests

GROQ_URL    = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL  = "llama-3.3-70b-versatile"
GROQ_VISION = "meta-llama/llama-4-scout-17b-16e-instruct"


def _load_token():
    """Charge la cle Groq depuis .env > variable OS."""
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        try:
            with open(env_path, "r", encoding="utf-8-sig") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("GROQ_API_KEY=") and not line.startswith("#"):
                        t = line.split("=", 1)[1].strip().strip("'" ")
                        if t and not t.startswith("gsk_xxx"):
                            return t
        except Exception:
            pass
    return os.environ.get("GROQ_API_KEY", "")


def _hdrs(k):
    return {"Authorization": f"Bearer {k}", "Content-Type": "application/json"}


def is_available():
    """Verifie si Groq est configure et accessible."""
    k = _load_token()
    if not k:
        return False
    try:
        r = requests.get(
            "https://api.groq.com/openai/v1/models",
            headers=_hdrs(k), timeout=5)
        return r.status_code == 200
    except Exception:
        return False


SYSTEM = """Tu es un assistant de gestion de taches integre dans QuickMind.
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
    Analyse prompt + image optionnelle via Groq Vision.
    Retourne dict avec analysis + tasks.
    """
    k = _load_token()
    if not k:
        raise RuntimeError("GROQ_API_KEY non configure dans .env")

    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    no_reminder = "aucun"
    user_text = (
        f"Date actuelle : {now}\n"
        f"Categories disponibles : {', '.join(categories or [])}\n"
        f"Categorie par defaut : {default_category or 'aucune'}\n"
        f"Rappel par defaut : {default_reminder or no_reminder}\n\n"
        f"Demande : {prompt}"
    )

    if image_b64:
        user_content = [
            {"type": "text", "text": user_text},
            {"type": "image_url", "image_url": {"url": f"data:{image_mime};base64,{image_b64}"}}
        ]
        model = GROQ_VISION
    else:
        user_content = user_text
        model = GROQ_MODEL

    msgs = [
        {"role": "system", "content": SYSTEM},
        {"role": "user",   "content": user_content}
    ]

    r = requests.post(
        GROQ_URL,
        headers=_hdrs(k),
        json={"model": model, "messages": msgs, "temperature": 0.2, "max_tokens": 2048},
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
