"""
Agent IA local — Ollama + Mistral
Transforme un prompt utilisateur en actions QuickMind.
"""
import json
import re
from datetime import datetime, timedelta
from typing import Optional
import ollama
from core.database import (get_tasks, get_categories, add_task,
                           update_task, delete_task, init_db)


# ── Prompt système ────────────────────────────────────────────────────────────
SYSTEM_PROMPT = """Tu es un assistant de gestion de taches integre dans QuickMind.
Tu reponds UNIQUEMENT en JSON valide, sans texte avant ou apres.

Actions disponibles :
- create_task   : creer une tache
- list_tasks    : lister / filtrer des taches
- update_task   : modifier le statut ou la priorite d une tache
- delete_task   : supprimer une tache
- add_reminder  : ajouter un rappel a une tache existante
- summary       : faire un resume ou une analyse
- unknown       : si tu ne comprends pas

Format de reponse obligatoire :
{
  "action": "nom_action",
  "params": { ... },
  "message": "message court a afficher a l utilisateur"
}

Parametres par action :
- create_task  : title(str), description(str), priority(low|normal|high|urgent), category(str), reminder(str ISO8601 optionnel)
- list_tasks   : category(str optionnel), status(todo|in_progress|done optionnel), priority(str optionnel), keyword(str optionnel)
- update_task  : task_id(int), status(str optionnel), priority(str optionnel), title(str optionnel)
- delete_task  : task_id(int)
- add_reminder : task_id(int), reminder(str ISO8601)
- summary      : scope(all|category|week|urgent)

Dates relatives : today=""" + datetime.now().strftime("%Y-%m-%d") + """, calcule les dates futures correctement.
Reponds toujours en francais dans le champ message.
"""


def _parse_response(raw: str) -> dict:
    """Extrait le JSON de la reponse du modele."""
    raw = raw.strip()
    # Cherche un bloc JSON dans la reponse
    match = re.search(r'\{.*\}', raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return {"action": "unknown", "params": {}, "message": raw}


def _get_context() -> str:
    """Construit le contexte actuel (taches + categories) pour le modele."""
    init_db()
    cats = {c.id: c.name for c in get_categories()}
    tasks = get_tasks()

    lines = [f"Date actuelle : {datetime.now().strftime('%d/%m/%Y %H:%M')}"]
    lines.append(f"Categories disponibles : {', '.join(cats.values())}")
    lines.append(f"Nombre de taches : {len(tasks)}")
    lines.append("")

    if tasks:
        lines.append("Taches existantes (ID | Titre | Statut | Priorite | Categorie) :")
        for t in tasks[:20]:  # max 20 pour ne pas surcharger le contexte
            cat_name = cats.get(t.category_id, "?")
            remind = f" | Rappel: {t.reminder_at.strftime('%d/%m/%Y %H:%M')}" if t.reminder_at else ""
            lines.append(f"  #{t.id} | {t.title} | {t.status} | {t.priority} | {cat_name}{remind}")

    return "".join(lines)


def _execute_action(parsed: dict) -> str:
    """Execute l action demandee et retourne un message de resultat."""
    action = parsed.get("action", "unknown")
    params = parsed.get("params", {})
    message = parsed.get("message", "")

    init_db()
    cats_by_name = {c.name.lower(): c.id for c in get_categories()}
    cats_by_id   = {c.id: c for c in get_categories()}

    # ── CREATE TASK ───────────────────────────────────────────────────────────
    if action == "create_task":
        title    = params.get("title", "Nouvelle tache")
        desc     = params.get("description", "")
        priority = params.get("priority", "normal")
        cat_name = params.get("category", "")
        cat_id   = cats_by_name.get(cat_name.lower()) if cat_name else None
        remind_dt = None
        remind_raw = params.get("reminder")
        if remind_raw:
            try:
                remind_dt = datetime.fromisoformat(remind_raw)
            except Exception:
                pass

        task = add_task(title=title, description=desc,
                        category_id=cat_id, priority=priority,
                        reminder_at=remind_dt)
        return f"Tache #{task.id} creee : **{title}**" + (
            f" (rappel le {remind_dt.strftime('%d/%m/%Y %H:%M')})" if remind_dt else ""
        )

    # ── LIST TASKS ────────────────────────────────────────────────────────────
    elif action == "list_tasks":
        cat_name = params.get("category", "")
        cat_id   = cats_by_name.get(cat_name.lower()) if cat_name else None
        status   = params.get("status")
        priority = params.get("priority")
        keyword  = params.get("keyword")

        tasks = get_tasks(category_id=cat_id, status=status)
        if priority:
            tasks = [t for t in tasks if t.priority == priority]
        if keyword:
            kw = keyword.lower()
            tasks = [t for t in tasks if kw in (t.title or "").lower()]

        if not tasks:
            return "Aucune tache trouvee pour ces criteres."

        lines = [f"{message}"]
        STATUS_ICON = {"todo": "📋", "in_progress": "⚙️", "done": "✅"}
        PRIO_ICON   = {"urgent": "🔴", "high": "🟠", "normal": "🔵", "low": "⚪"}
        for t in tasks:
            cat = cats_by_id.get(t.category_id)
            cat_str = f" [{cat.name}]" if cat else ""
            remind  = f" ⏰ {t.reminder_at.strftime('%d/%m/%Y %H:%M')}" if t.reminder_at else ""
            lines.append(
                f"{PRIO_ICON.get(t.priority,'🔵')} #{t.id} {t.title}"
                f" — {STATUS_ICON.get(t.status,'📋')} {t.status}{cat_str}{remind}"
            )
        return "".join(lines)

    # ── UPDATE TASK ───────────────────────────────────────────────────────────
    elif action == "update_task":
        task_id = params.get("task_id")
        if not task_id:
            return "ID de tache manquant."
        kwargs = {}
        if "status"   in params: kwargs["status"]   = params["status"]
        if "priority" in params: kwargs["priority"] = params["priority"]
        if "title"    in params: kwargs["title"]    = params["title"]
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
            return f"Rappel ajoute sur tache #{task_id} : {remind_dt.strftime('%d/%m/%Y %H:%M')}"
        except Exception as e:
            return f"Erreur rappel : {e}"

    # ── DELETE TASK ───────────────────────────────────────────────────────────
    elif action == "delete_task":
        task_id = params.get("task_id")
        if not task_id:
            return "ID de tache manquant."
        delete_task(task_id)
        return f"Tache #{task_id} supprimee."

    # ── SUMMARY ───────────────────────────────────────────────────────────────
    elif action == "summary":
        tasks = get_tasks()
        total   = len(tasks)
        todo    = sum(1 for t in tasks if t.status == "todo")
        wip     = sum(1 for t in tasks if t.status == "in_progress")
        done    = sum(1 for t in tasks if t.status == "done")
        urgent  = sum(1 for t in tasks if t.priority == "urgent")
        overdue = sum(1 for t in tasks
                      if t.reminder_at and t.reminder_at < datetime.now()
                      and not t.reminder_fired)
        return (
            f"{message}"
            f"📊 **Resume QuickMind**"
            f"  Total     : {total} taches"
            f"  📋 A faire  : {todo}"
            f"  ⚙️  En cours : {wip}"
            f"  ✅ Terminees : {done}"
            f"  🔴 Urgentes  : {urgent}"
            f"  ⏰ En retard : {overdue}"
        )

    # ── UNKNOWN ───────────────────────────────────────────────────────────────
    else:
        return message or "Je n ai pas compris la demande. Peux-tu reformuler ?"


def ask_ai(prompt: str) -> str:
    """
    Point d entree principal.
    Envoie le prompt a Ollama/Mistral et execute l action retournee.
    """
    context = _get_context()
    user_message = f"Contexte:{context}Demande utilisateur: {prompt}"

    try:
        response = ollama.chat(
            model="mistral",
            messages=[
                {"role": "system",  "content": SYSTEM_PROMPT},
                {"role": "user",    "content": user_message},
            ],
            options={"temperature": 0.1},  # reponses deterministiques
        )
        raw = response["message"]["content"]
        parsed = _parse_response(raw)
        return _execute_action(parsed)

    except Exception as e:
        err = str(e)
        if "connection" in err.lower() or "refused" in err.lower():
            return "Ollama n est pas demarree. Lance : ollama serve"
        return f"Erreur IA : {err}"
