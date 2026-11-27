"""
Generation de sous-taches via Groq.
"""
import json
import re
from agents.ai_client import call_ai


def generate_subtasks(task_title: str, task_description: str = "",
                      max_subtasks: int = 10) -> list[str]:
    """
    Genere une liste de sous-taches pour une tache donnee.
    Retourne une liste de titres de sous-taches.
    """
    prompt = (
        f"Tu es un assistant de gestion de projet.\n"
        f"Genere une liste de sous-taches concretes et actionnables "
        f"pour la tache suivante.\n\n"
        f"Tache : {task_title}\n"
        + (f"Description : {task_description}\n" if task_description else "") +
        f"\nRetourne UNIQUEMENT un JSON valide :\n"
        f"{{\"subtasks\": [\"sous-tache 1\", \"sous-tache 2\", ...]}}\n\n"
        f"Regles :\n"
        f"- Maximum {max_subtasks} sous-taches\n"
        f"- Chaque sous-tache est courte et actionnable (max 60 caracteres)\n"
        f"- Commencer par un verbe d action\n"
        f"- En francais\n"
        f"- Ordre logique d execution"
    )

    raw = call_ai(
        [
            {"role": "system", "content": "Tu generes des listes de sous-taches en JSON."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
    ).strip()
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        data = json.loads(match.group())
        subs = data.get("subtasks", [])
        if isinstance(subs, list):
            return [item.strip() for item in subs
                    if isinstance(item, str) and item.strip()][:max_subtasks]

    return []
