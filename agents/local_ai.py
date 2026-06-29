"""
Agent IA QuickMind.
Utilise Groq (llama-3.3-70b) si disponible, sinon Ollama/Mistral en fallback.
Meme logique qu AION-Core brain.py.
"""
import json
import os
import re
import requests
from datetime import datetime
from typing import Optional
from core.database import (get_tasks, get_categories, add_task,
                           update_task, delete_task, init_db,
                           add_subtask, get_subtasks)

GROQ_URL    = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL  = os.getenv("GROQ_MODEL",  "llama-3.3-70b-versatile")
GROQ_VISION = os.getenv("GROQ_VISION", "llama-4-scout-17b-16e-instruct")

# Charger .env au demarrage
try:
    from pathlib import Path as _P
    _env = _P(__file__).parent.parent / ".env"
    if _env.exists():
        with open(_env, "r", encoding="utf-8-sig") as _f:
            for _l in _f:
                _l = _l.strip()
                if "=" in _l and not _l.startswith("#"):
                    _k, _v = _l.split("=", 1)
                    os.environ.setdefault(_k.strip(), _v.strip().strip('"\' '))
    # Relire apres chargement
    GROQ_MODEL  = os.getenv("GROQ_MODEL",  "llama-3.3-70b-versatile")
    GROQ_VISION = os.getenv("GROQ_VISION", "llama-4-scout-17b-16e-instruct")
except Exception:
    pass


def _get_groq_key():
    """Retourne la cle Groq depuis env."""
    from pathlib import Path
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        try:
            with open(env_path, "r", encoding="utf-8-sig") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("GROQ_API_KEY=") and not line.startswith("#"):
                        t = line.split("=", 1)[1].strip().strip('"\' ')
                        if t and not t.startswith("gsk_xxx"):
                            return t
        except Exception:
            pass
    return os.environ.get("GROQ_API_KEY", "")


def _groq_available():
    k = _get_groq_key()
    if not k:
        return False
    try:
        r = requests.get("https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {k}"}, timeout=5)
        return r.status_code == 200
    except Exception:
        return False


def _call_groq(messages, model=None):
    """Appel Groq API — retourne le contenu du message."""
    k = _get_groq_key()
    if not k:
        raise RuntimeError("GROQ_API_KEY non configure")
    used_model = model or GROQ_MODEL
    r = requests.post(
        GROQ_URL,
        headers={"Authorization": "Bearer " + k, "Content-Type": "application/json"},
        json={"model": used_model, "messages": messages,
              "temperature": 0.1, "max_tokens": 2048},
        timeout=30,
    )
    if r.status_code == 404:
        raise RuntimeError("Modele Groq introuvable: " + used_model + ". Verifiez GROQ_MODEL dans .env")
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _call_ollama(messages):
    """Appel Ollama/Mistral — fallback si pas de Groq."""
    import ollama
    response = ollama.chat(
        model="mistral",
        messages=messages,
        options={"temperature": 0.1},
    )
    return response["message"]["content"]


def _call_ai(messages):
    """
    Appel IA avec priorite :
    1. Groq (llama-3.3-70b) si cle disponible
    2. Ollama/Mistral sinon
    """
    if _get_groq_key():
        try:
            result = _call_groq(messages)
            print("[AI] Groq llama-3.3-70b")
            return result
        except Exception as e:
            print(f"[AI] Groq failed ({e}), fallback Ollama")
    # Fallback Ollama
    try:
        result = _call_ollama(messages)
        print("[AI] Ollama/Mistral (fallback)")
        return result
    except Exception as e:
        err = str(e)
        if "connection" in err.lower() or "refused" in err.lower():
            raise RuntimeError("Ni Groq ni Ollama disponibles. Configure GROQ_API_KEY dans .env ou lance Ollama.")
        raise


SYSTEM_PROMPT = """Tu es un assistant de gestion de taches integre dans QuickMind.
Tu reponds UNIQUEMENT en JSON valide, sans texte avant ou apres.

Actions disponibles :
- create_task            : creer une tache simple
- create_task_subtasks   : creer une tache AVEC des sous-taches
- list_tasks             : lister / filtrer des taches
- update_task            : modifier le statut ou la priorite
- delete_task            : supprimer une tache
- add_reminder           : ajouter un rappel a une tache existante
- add_subtasks           : ajouter des sous-taches a une tache existante
- summary                : faire un resume
- unknown                : si non compris

Format :
{
  "action": "nom_action",
  "params": { ... },
  "message": "message court a afficher"
}

Parametres par action :
- create_task          : title, description, priority(low|normal|high|urgent), category, reminder(ISO8601 opt)
- create_task_subtasks : title, description, priority, category, reminder(opt), subtasks(liste max 10)
- list_tasks           : category(opt), status(opt), priority(opt), keyword(opt)
- update_task          : task_id, status(opt), priority(opt), title(opt)
- add_reminder         : task_id, reminder(ISO8601)
- add_subtasks         : task_id, subtasks(liste)
- summary              : scope(all|category|week|urgent)

Date actuelle : """ + datetime.now().strftime("%Y-%m-%d %H:%M") + """
Reponds toujours en francais dans le champ message."""


def _parse_response(raw):
    raw = raw.strip()
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return {"action": "unknown", "params": {}, "message": raw}


def _get_context():
    init_db()
    cats  = {c.id: c.name for c in get_categories()}
    tasks = get_tasks()
    lines = [
        f"Date : {datetime.now().strftime('%d/%m/%Y %H:%M')}",
        f"Categories : {', '.join(cats.values())}",
        f"Taches : {len(tasks)}",
        ""
    ]
    if tasks:
        lines.append("Taches (ID | Titre | Statut | Priorite | Cat | Sous-taches) :")
        for t in tasks[:20]:
            cat_name = cats.get(t.category_id, "?")
            subs     = get_subtasks(t.id)
            sub_info = f" | {len(subs)} sous-tache(s)" if subs else ""
            remind   = f" | Rappel: {t.reminder_at.strftime('%d/%m/%Y %H:%M')}" if t.reminder_at else ""
            lines.append(f"  #{t.id} | {t.title} | {t.status} | {t.priority} | {cat_name}{sub_info}{remind}")
    return "\n".join(lines)


def _execute_action(parsed):
    action  = parsed.get("action", "unknown")
    params  = parsed.get("params", {})
    message = parsed.get("message", "")

    init_db()
    cats_by_name = {c.name.lower(): c.id for c in get_categories()}
    cats_by_id   = {c.id: c             for c in get_categories()}

    if action == "create_task":
        title    = params.get("title", "Nouvelle tache")
        desc     = params.get("description", "")
        priority = params.get("priority", "normal")
        cat_name = params.get("category", "")
        cat_id   = cats_by_name.get(cat_name.lower()) if cat_name else None
        remind_dt = None
        if params.get("reminder"):
            try: remind_dt = datetime.fromisoformat(params["reminder"])
            except Exception: pass
        task = add_task(title=title, description=desc, category_id=cat_id,
                        priority=priority, reminder_at=remind_dt)
        return f"Tache #{task.id} creee : {title}" + (
            f" (rappel le {remind_dt.strftime('%d/%m/%Y %H:%M')})" if remind_dt else "")

    elif action == "create_task_subtasks":
        title    = params.get("title", "Nouvelle tache")
        desc     = params.get("description", "")
        priority = params.get("priority", "normal")
        cat_name = params.get("category", "")
        cat_id   = cats_by_name.get(cat_name.lower()) if cat_name else None
        subtasks = params.get("subtasks", [])
        remind_dt = None
        if params.get("reminder"):
            try: remind_dt = datetime.fromisoformat(params["reminder"])
            except Exception: pass
        task = add_task(title=title, description=desc, category_id=cat_id,
                        priority=priority, reminder_at=remind_dt)
        added = []
        for s in subtasks[:10]:
            if s.strip():
                res = add_subtask(task.id, s.strip())
                if res: added.append(s.strip())
        sub_list = "\n".join(f"  - {s}" for s in added)
        return f"Tache #{task.id} creee : {title}\n{len(added)} sous-tache(s) :\n{sub_list}"

    elif action == "add_subtasks":
        task_id  = params.get("task_id")
        subtasks = params.get("subtasks", [])
        if not task_id: return "ID de tache manquant."
        added = []
        for s in subtasks[:10]:
            if s.strip():
                res = add_subtask(task_id, s.strip())
                if res: added.append(s.strip())
                else:   break
        sub_list = "\n".join(f"  - {s}" for s in added)
        return f"{len(added)} sous-tache(s) ajoutee(s) a la tache #{task_id} :\n{sub_list}"

    elif action == "list_tasks":
        cat_name = params.get("category", "")
        cat_id   = cats_by_name.get(cat_name.lower()) if cat_name else None
        status   = params.get("status")
        priority = params.get("priority")
        keyword  = params.get("keyword")
        tasks    = get_tasks(category_id=cat_id, status=status)
        if priority: tasks = [t for t in tasks if t.priority == priority]
        if keyword:
            kw = keyword.lower()
            tasks = [t for t in tasks if kw in (t.title or "").lower()
                     or kw in (t.description or "").lower()]
        if not tasks: return "Aucune tache trouvee."
        SI = {"todo":"[  ]","in_progress":"[~]","done":"[x]"}
        PI = {"urgent":"🔴","high":"🟠","normal":"🔵","low":"⚪"}
        lines = [f"{message}\n"]
        for t in tasks:
            cat    = cats_by_id.get(t.category_id)
            cat_s  = f" [{cat.name}]" if cat else ""
            subs   = get_subtasks(t.id)
            sub_s  = f" [{len(subs)} sous-tache(s)]" if subs else ""
            remind = f" ⏰ {t.reminder_at.strftime('%d/%m/%Y %H:%M')}" if t.reminder_at else ""
            lines.append(f"{PI.get(t.priority,'🔵')} #{t.id} {t.title} — {SI.get(t.status,'?')} {t.status}{cat_s}{sub_s}{remind}")
        return "\n".join(lines)

    elif action == "update_task":
        task_id = params.get("task_id")
        if not task_id: return "ID de tache manquant."
        kwargs = {}
        for k in ("status","priority","title"):
            if k in params: kwargs[k] = params[k]
        update_task(task_id, **kwargs)
        return f"{message} (tache #{task_id} mise a jour)"

    elif action == "add_reminder":
        task_id    = params.get("task_id")
        remind_raw = params.get("reminder")
        if not task_id or not remind_raw: return "ID ou date manquant."
        try:
            remind_dt = datetime.fromisoformat(remind_raw)
            update_task(task_id, reminder_at=remind_dt, reminder_fired=False)
            return f"Rappel ajoute sur tache #{task_id} : {remind_dt.strftime('%d/%m/%Y %H:%M')}"
        except Exception as e:
            return f"Erreur rappel : {e}"

    elif action == "delete_task":
        task_id = params.get("task_id")
        if not task_id: return "ID de tache manquant."
        delete_task(task_id)
        return f"Tache #{task_id} supprimee."

    elif action == "summary":
        tasks   = get_tasks()
        total   = len(tasks)
        todo    = sum(1 for t in tasks if t.status == "todo")
        wip     = sum(1 for t in tasks if t.status == "in_progress")
        done    = sum(1 for t in tasks if t.status == "done")
        urgent  = sum(1 for t in tasks if t.priority == "urgent")
        overdue = sum(1 for t in tasks if t.reminder_at and t.reminder_at < datetime.now() and not t.reminder_fired)
        total_subs = sum(len(get_subtasks(t.id)) for t in tasks)
        return (f"{message}\n\nResume QuickMind :\n"
                f"  Total taches : {total}\n"
                f"  A faire      : {todo}\n"
                f"  En cours     : {wip}\n"
                f"  Terminees    : {done}\n"
                f"  Urgentes     : {urgent}\n"
                f"  En retard    : {overdue}\n"
                f"  Sous-taches  : {total_subs}")

    else:
        return message or "Je n ai pas compris. Peux-tu reformuler ?"


def ask_ai(prompt):
    """
    Point d entree principal.
    Groq (llama-3.3-70b) en priorite, Ollama/Mistral en fallback.
    """
    context      = _get_context()
    user_message = f"Contexte :\n{context}\n\nDemande : {prompt}"
    messages = [
        {"role": "system",  "content": SYSTEM_PROMPT},
        {"role": "user",    "content": user_message},
    ]
    try:
        raw    = _call_ai(messages)
        parsed = _parse_response(raw)
        return _execute_action(parsed)
    except Exception as e:
        return f"Erreur IA : {e}"
