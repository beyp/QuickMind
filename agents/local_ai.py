"""
Agent IA local — Ollama + Mistral
Transforme un prompt utilisateur en actions QuickMind.
Supporte la creation de taches avec sous-taches.
"""
import json
import re
from datetime import datetime
from typing import Optional
import ollama
from core.database import (get_tasks, get_categories, add_task,
                           update_task, delete_task, init_db,
                           add_subtask, get_subtasks)


SYSTEM_PROMPT = """Tu es un assistant de gestion de taches integre dans QuickMind.
Tu reponds UNIQUEMENT en JSON valide, sans texte avant ou apres.

Actions disponibles :
- create_task            : creer une tache simple
- create_task_subtasks   : creer une tache AVEC des sous-taches
- list_tasks             : lister / filtrer des taches
- update_task            : modifier le statut ou la priorite
- delete_task            : supprimer une tache
- add_reminder           : ajouter un rappel
- add_subtasks           : ajouter des sous-taches a une tache existante
- summary                : faire un resume
- unknown                : si non compris

Format de reponse obligatoire :
{
  "action": "nom_action",
  "params": { ... },
  "message": "message court a afficher"
}

Parametres par action :
- create_task          : title, description, priority(low|normal|high|urgent), category, reminder(ISO8601 opt)
- create_task_subtasks : title, description, priority, category, reminder(opt),
                         subtasks(liste de strings, max 10)
- list_tasks           : category(opt), status(opt), priority(opt), keyword(opt)
- update_task          : task_id, status(opt), priority(opt), title(opt)
- add_reminder         : task_id, reminder(ISO8601)
- add_subtasks         : task_id, subtasks(liste de strings)
- summary              : scope(all|category|week|urgent)

Exemples de prompts et actions attendues :
- "Cree une tache pour preparer la demo avec les etapes" -> create_task_subtasks
- "Ajoute des sous-taches a la tache #3" -> add_subtasks
- "Cree une tache simple : appeler le client" -> create_task

Date actuelle : """ + datetime.now().strftime("%Y-%m-%d %H:%M") + """
Reponds toujours en francais dans le champ message.
"""


def _parse_response(raw: str) -> dict:
    raw   = raw.strip()
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return {"action": "unknown", "params": {}, "message": raw}


def _get_context() -> str:
    init_db()
    cats  = {c.id: c.name for c in get_categories()}
    tasks = get_tasks()
    lines = [
        f"Date actuelle : {datetime.now().strftime('%d/%m/%Y %H:%M')}",
        f"Categories disponibles : {', '.join(cats.values())}",
        f"Nombre de taches : {len(tasks)}",
        ""
    ]
    if tasks:
        lines.append("Taches existantes (ID | Titre | Statut | Priorite | Cat | Sous-taches) :")
        for t in tasks[:20]:
            cat_name = cats.get(t.category_id, "?")
            subs     = get_subtasks(t.id)
            sub_info = f" | {len(subs)} sous-tache(s)" if subs else ""
            remind   = (f" | Rappel: {t.reminder_at.strftime('%d/%m/%Y %H:%M')}"
                       if t.reminder_at else "")
            lines.append(
                f"  #{t.id} | {t.title} | {t.status} | "
                f"{t.priority} | {cat_name}{sub_info}{remind}"
            )
    return "\n".join(lines)


def _execute_action(parsed: dict) -> str:
    action = parsed.get("action", "unknown")
    params = parsed.get("params", {})
    message = parsed.get("message", "")

    init_db()
    cats_by_name = {c.name.lower(): c.id for c in get_categories()}
    cats_by_id   = {c.id: c        for c in get_categories()}

    # ── CREATE TASK ───────────────────────────────────────────────────────────
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

        task = add_task(title=title, description=desc,
                        category_id=cat_id, priority=priority,
                        reminder_at=remind_dt)
        return (
            f"Tache #{task.id} creee : **{title}**" +
            (f" (rappel le {remind_dt.strftime('%d/%m/%Y %H:%M')})"
             if remind_dt else "")
        )

    # ── CREATE TASK WITH SUBTASKS ─────────────────────────────────────────────
    elif action == "create_task_subtasks":
        title     = params.get("title", "Nouvelle tache")
        desc      = params.get("description", "")
        priority  = params.get("priority", "normal")
        cat_name  = params.get("category", "")
        cat_id    = cats_by_name.get(cat_name.lower()) if cat_name else None
        subtasks  = params.get("subtasks", [])
        remind_dt = None
        if params.get("reminder"):
            try: remind_dt = datetime.fromisoformat(params["reminder"])
            except Exception: pass

        task = add_task(title=title, description=desc,
                        category_id=cat_id, priority=priority,
                        reminder_at=remind_dt)

        # Ajouter les sous-taches
        added = []
        for sub_title in subtasks[:10]:
            if sub_title.strip():
                result = add_subtask(task.id, sub_title.strip())
                if result:
                    added.append(sub_title.strip())

        sub_list = "\n".join(f"  • {s}" for s in added)
        return (
            f"Tache #{task.id} creee : **{title}**\n"
            f"{len(added)} sous-tache(s) ajoutee(s) :\n{sub_list}"
        )

    # ── ADD SUBTASKS TO EXISTING TASK ─────────────────────────────────────────
    elif action == "add_subtasks":
        task_id  = params.get("task_id")
        subtasks = params.get("subtasks", [])
        if not task_id:
            return "ID de tache manquant."
        added = []
        for sub_title in subtasks[:10]:
            if sub_title.strip():
                result = add_subtask(task_id, sub_title.strip())
                if result:
                    added.append(sub_title.strip())
                else:
                    break  # limite atteinte
        sub_list = "\n".join(f"  • {s}" for s in added)
        return (
            f"{len(added)} sous-tache(s) ajoutee(s) a la tache #{task_id} :\n"
            f"{sub_list}"
        )

    # ── LIST TASKS ────────────────────────────────────────────────────────────
    elif action == "list_tasks":
        cat_name = params.get("category", "")
        cat_id   = cats_by_name.get(cat_name.lower()) if cat_name else None
        status   = params.get("status")
        priority = params.get("priority")
        keyword  = params.get("keyword")

        tasks = get_tasks(category_id=cat_id, status=status)
        if priority: tasks = [t for t in tasks if t.priority == priority]
        if keyword:
            kw = keyword.lower()
            tasks = [t for t in tasks
                     if kw in (t.title or "").lower()
                     or kw in (t.description or "").lower()]

        if not tasks:
            return "Aucune tache trouvee."

        STATUS_ICON = {"todo":"📋","in_progress":"⚙️","done":"✅"}
        PRIO_ICON   = {"urgent":"🔴","high":"🟠","normal":"🔵","low":"⚪"}
        lines       = [f"{message}\n"]
        for t in tasks:
            cat      = cats_by_id.get(t.category_id)
            cat_str  = f" [{cat.name}]" if cat else ""
            remind   = (f" ⏰ {t.reminder_at.strftime('%d/%m/%Y %H:%M')}"
                       if t.reminder_at else "")
            subs     = get_subtasks(t.id)
            sub_str  = f" [{len(subs)} sous-tâche(s)]" if subs else ""
            lines.append(
                f"{PRIO_ICON.get(t.priority,'🔵')} #{t.id} {t.title}"
                f" — {STATUS_ICON.get(t.status,'📋')} {t.status}"
                f"{cat_str}{sub_str}{remind}"
            )
        return "\n".join(lines)

    # ── UPDATE TASK ───────────────────────────────────────────────────────────
    elif action == "update_task":
        task_id = params.get("task_id")
        if not task_id: return "ID de tache manquant."
        kwargs = {}
        for k in ("status","priority","title"):
            if k in params: kwargs[k] = params[k]
        update_task(task_id, **kwargs)
        return f"{message} (tache #{task_id} mise a jour)"

    # ── ADD REMINDER ──────────────────────────────────────────────────────────
    elif action == "add_reminder":
        task_id   = params.get("task_id")
        remind_raw = params.get("reminder")
        if not task_id or not remind_raw:
            return "ID ou date de rappel manquant."
        try:
            remind_dt = datetime.fromisoformat(remind_raw)
            update_task(task_id, reminder_at=remind_dt, reminder_fired=False)
            return (f"Rappel ajoute sur tache #{task_id} : "
                    f"{remind_dt.strftime('%d/%m/%Y %H:%M')}")
        except Exception as e:
            return f"Erreur rappel : {e}"

    # ── DELETE TASK ───────────────────────────────────────────────────────────
    elif action == "delete_task":
        task_id = params.get("task_id")
        if not task_id: return "ID de tache manquant."
        delete_task(task_id)
        return f"Tache #{task_id} supprimee."

    # ── SUMMARY ───────────────────────────────────────────────────────────────
    elif action == "summary":
        tasks   = get_tasks()
        total   = len(tasks)
        todo    = sum(1 for t in tasks if t.status == "todo")
        wip     = sum(1 for t in tasks if t.status == "in_progress")
        done    = sum(1 for t in tasks if t.status == "done")
        urgent  = sum(1 for t in tasks if t.priority == "urgent")
        overdue = sum(1 for t in tasks
                      if t.reminder_at and t.reminder_at < datetime.now()
                      and not t.reminder_fired)
        # Sous-taches
        total_subs = sum(len(get_subtasks(t.id)) for t in tasks)
        return (
            f"{message}\n\n"
            f"Resume QuickMind :\n"
            f"  Total taches    : {total}\n"
            f"  A faire         : {todo}\n"
            f"  En cours        : {wip}\n"
            f"  Terminees       : {done}\n"
            f"  Urgentes        : {urgent}\n"
            f"  En retard       : {overdue}\n"
            f"  Sous-taches     : {total_subs}"
        )

    else:
        return message or "Je n ai pas compris. Peux-tu reformuler ?"


def ask_ai(prompt: str) -> str:
    context      = _get_context()
    user_message = f"Contexte :\n{context}\n\nDemande : {prompt}"

    try:
        response = ollama.chat(
            model="mistral",
            messages=[
                {"role": "system",  "content": SYSTEM_PROMPT},
                {"role": "user",    "content": user_message},
            ],
            options={"temperature": 0.1},
        )
        raw    = response["message"]["content"]
        parsed = _parse_response(raw)
        return _execute_action(parsed)

    except Exception as e:
        err = str(e)
        if "connection" in err.lower() or "refused" in err.lower():
            return "Ollama n est pas demarre. Lance : ollama serve"
        return f"Erreur IA : {err}"
