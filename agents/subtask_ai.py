"""
Generation de sous-taches via Mistral.
"""
import json
import re
import ollama


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

    try:
        response = ollama.chat(
            model="mistral",
            messages=[
                {"role": "system",
                 "content": "Tu generes des listes de sous-taches en JSON."},
                {"role": "user", "content": prompt},
            ],
            options={"temperature": 0.2}
        )
        raw   = response["message"]["content"].strip()
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            data = json.loads(match.group())
            subs = data.get("subtasks", [])
            return [s.strip() for s in subs if s.strip()][:max_subtasks]
    except Exception as e:
        err = str(e)
        if "connection" in err.lower() or "refused" in err.lower():
            raise RuntimeError("Ollama n est pas demarre.")
        raise

    return []
