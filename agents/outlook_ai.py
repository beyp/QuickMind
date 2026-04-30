"""
Router IA pour les commandes Outlook.
Detecte les intentions liees a Outlook et les execute.
"""
import json
import re
from datetime import datetime
from agents.outlook_agent import (
    get_unread_mails, get_recent_mails, send_mail,
    get_upcoming_events, create_calendar_event,
    get_outlook_tasks, create_outlook_task,
    get_mail_info
)
import ollama


OUTLOOK_SYSTEM = (
    "Tu es un assistant qui gere Outlook (mails, calendrier, taches).\n"
    "Tu reponds UNIQUEMENT en JSON valide, sans texte avant ou apres.\n\n"
    "Actions disponibles :\n"
    "- read_unread      : lire les mails non lus\n"
    "- read_recent      : lire les derniers mails\n"
    "- send_mail        : envoyer un mail\n"
    "- get_calendar     : voir les prochains evenements\n"
    "- create_event     : creer un evenement calendrier\n"
    "- get_tasks        : voir les taches Outlook\n"
    "- create_ol_task   : creer une tache Outlook\n"
    "- mail_to_qm_task  : transformer un mail en tache QuickMind\n"
    "- unknown          : si non compris\n\n"
    "Format obligatoire :\n"
    "{\n"
    "  \"action\": \"nom_action\",\n"
    "  \"params\": { ... },\n"
    "  \"message\": \"message court\"\n"
    "}\n\n"
    "Parametres par action :\n"
    "- send_mail      : to(str), subject(str), body(str)\n"
    "- create_event   : subject(str), start(ISO8601), end(ISO8601 opt), location(str), reminder_minutes(int)\n"
    "- create_ol_task : subject(str), due(ISO8601 opt), body(str), importance(0|1|2)\n"
    "- get_calendar   : days(int, defaut 7)\n"
    "- mail_to_qm_task: mail_index(int, commence a 0)\n\n"
    "Date actuelle : " + datetime.now().strftime("%Y-%m-%d %H:%M") + "\n"
    "Reponds toujours en francais dans le champ message."
)


def _parse(raw: str) -> dict:
    raw = raw.strip()
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except Exception:
            pass
    return {"action": "unknown", "params": {}, "message": raw}


def summarize_mail(entry_id: str, mode: str = "auto") -> str:
    """
    Résume ou retourne le corps complet d'un mail via Mistral.
    mode : "summary" | "full" | "auto" (Mistral choisit)
    """
    try:
        info = get_mail_info(entry_id)
    except Exception as e:
        return f"Impossible de lire le mail : {e}"

    body = info.get("body_full", "").strip()
    subject = info.get("subject", "")
    sender  = info.get("sender", "")
    received = info.get("received", "")

    if not body:
        return "Le corps de ce mail est vide."

    if mode == "full":
        return (
            f"De    : {sender}\n"
            f"Objet : {subject}\n"
            f"Recu  : {received}\n"
            f"{'-'*50}\n\n"
            f"{body}"
        )

    # Mode summary ou auto : on demande a Mistral
    word_count = len(body.split())
    if mode == "auto":
        instruction = (
            "Ce mail fait environ " + str(word_count) + " mots. "
            "Si le mail est court (moins de 80 mots), retourne-le en entier. "
            "Sinon, fais un resume clair et structure en francais, "
            "en mettant en evidence : l objet principal, les points cles, "
            "et les actions demandees si applicable."
        )
    else:
        instruction = (
            "Fais un resume clair et structure en francais de ce mail. "
            "Mets en evidence : l objet principal, les points cles, "
            "et les actions demandees si applicable."
        )

    prompt = (
        f"Mail de : {sender}\n"
        f"Objet   : {subject}\n"
        f"Recu le : {received}\n\n"
        f"Corps du mail :\n{body[:3000]}\n\n"
        f"Instruction : {instruction}"
    )

    try:
        response = ollama.chat(
            model="mistral",
            messages=[
                {"role": "system",
                 "content": "Tu es un assistant qui analyse et resume des emails professionnels en francais."},
                {"role": "user", "content": prompt},
            ],
            options={"temperature": 0.2},
        )
        summary = response["message"]["content"].strip()
        header = (
            f"De    : {sender}\n"
            f"Objet : {subject}\n"
            f"Recu  : {received}\n"
            f"{'-'*50}\n\n"
        )
        return header + summary
    except Exception as e:
        err = str(e)
        if "connection" in err.lower() or "refused" in err.lower():
            return "Ollama n est pas demarre. Lance : ollama serve"
        return f"Erreur Mistral : {e}"


def ask_outlook(prompt: str) -> tuple[str, list | None]:
    """Point d entree principal pour les commandes Outlook."""
    try:
        response = ollama.chat(
            model="mistral",
            messages=[
                {"role": "system", "content": OUTLOOK_SYSTEM},
                {"role": "user",   "content": prompt},
            ],
            options={"temperature": 0.1},
        )
        parsed = _parse(response["message"]["content"])
    except Exception as e:
        return f"Erreur Mistral : {e}", None

    action = parsed.get("action", "unknown")
    params = parsed.get("params", {})
    msg    = parsed.get("message", "")

    try:
        if action == "read_unread":
            mails = get_unread_mails(max_count=10)
            if not mails:
                return "Aucun mail non lu.", None
            lines = [msg + "\n"]
            for i, m in enumerate(mails):
                lines.append(
                    f"#{i+1} De : {m['sender']}\n"
                    f"   Objet  : {m['subject']}\n"
                    f"   Recu   : {m['received']}\n"
                    f"   Apercu : {m['body_preview'][:120]}...\n"
                )
            return "\n".join(lines), mails

        elif action == "read_recent":
            mails = get_recent_mails(max_count=10)
            if not mails:
                return "Aucun mail recent.", None
            lines = [msg + "\n"]
            for i, m in enumerate(mails):
                unread = "[NON LU] " if m.get("unread") else ""
                lines.append(
                    f"#{i+1} {unread}De : {m['sender']}\n"
                    f"   Objet  : {m['subject']}\n"
                    f"   Recu   : {m['received']}\n"
                    f"   Apercu : {m['body_preview'][:120]}...\n"
                )
            return "\n".join(lines), mails

        elif action == "send_mail":
            to      = params.get("to", "")
            subject = params.get("subject", "")
            body    = params.get("body", "")
            if not to or not subject:
                return "Destinataire ou objet manquant.", None
            send_mail(to, subject, body)
            return f"Mail envoye a {to} : {subject}", None

        elif action == "get_calendar":
            days   = int(params.get("days", 7))
            events = get_upcoming_events(days=days)
            if not events:
                return f"Aucun evenement dans les {days} prochains jours.", None
            lines = [msg + "\n"]
            for e in events:
                loc = f" | {e['location']}" if e["location"] else ""
                lines.append(f"  {e['start']} -> {e['end']}\n  {e['subject']}{loc}\n")
            return "\n".join(lines), None

        elif action == "create_event":
            subject  = params.get("subject", "Nouvel evenement")
            start_s  = params.get("start")
            end_s    = params.get("end")
            location = params.get("location", "")
            reminder = int(params.get("reminder_minutes", 15))
            if not start_s:
                return "Date de debut manquante.", None
            start_dt = datetime.fromisoformat(start_s)
            end_dt   = datetime.fromisoformat(end_s) if end_s else None
            create_calendar_event(subject, start_dt, end_dt, "", location, reminder)
            return (
                f"Evenement cree :\n  {subject}\n"
                f"  Le {start_dt.strftime('%d/%m/%Y a %H:%M')}"
                + (f" | {location}" if location else ""),
                None
            )

        elif action == "get_tasks":
            tasks = get_outlook_tasks()
            if not tasks:
                return "Aucune tache Outlook en cours.", None
            PRIO = {0: "basse", 1: "normale", 2: "haute"}
            lines = [msg + "\n"]
            for t in tasks:
                lines.append(
                    f"  - {t['subject']}"
                    f" | Echeance : {t['due']}"
                    f" | Priorite : {PRIO.get(t['priority'], '?')}\n"
                )
            return "\n".join(lines), None

        elif action == "create_ol_task":
            subject    = params.get("subject", "Nouvelle tache")
            due_s      = params.get("due")
            body       = params.get("body", "")
            importance = int(params.get("importance", 1))
            due_dt     = datetime.fromisoformat(due_s) if due_s else None
            create_outlook_task(subject, due_dt, body, importance)
            return f"Tache Outlook creee : {subject}", None

        elif action == "mail_to_qm_task":
            idx   = int(params.get("mail_index", 0))
            mails = get_recent_mails(max_count=idx + 1)
            if not mails or idx >= len(mails):
                return "Mail introuvable.", None
            m = mails[idx]
            return f"MAIL_TO_TASK:{m['subject']}|{m['body_preview'][:300]}", [m]

        else:
            return msg or "Commande Outlook non reconnue.", None

    except Exception as e:
        return f"Erreur Outlook : {e}", None
