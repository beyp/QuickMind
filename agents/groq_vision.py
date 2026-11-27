import json, os, re
from datetime import datetime
from pathlib import Path

from agents.ai_client import call_ai, get_api_key, is_available


def _load_token():
    return get_api_key()


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
        vision = True
    else:
        user_content = user_text
        vision = False
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": user_content},
    ]
    raw = call_ai(messages, vision=vision, temperature=0.2).strip()
    m   = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        try: return json.loads(m.group())
        except Exception: pass
    return {"analysis": raw[:200], "tasks": []}
