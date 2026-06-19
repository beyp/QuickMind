import customtkinter as ctk
from ui.subtask_widget import SubTaskWidget
from datetime import datetime, timedelta
from core.database import (get_tasks, get_categories, add_task,
                           update_task, delete_task, get_task_attachments,
                           archive_all_done, delete_all_done,
                           get_archived_tasks, get_done_count)
from core.models import Task
from ui.task_form import TaskForm
from ui.recurrence_widget import RecurrenceWidget
import os

PRIORITY_META = {
    "urgent": ("🔴", "#FF4444"),
    "high":   ("🟠", "#FF8C00"),
    "normal": ("🔵", "#1E90FF"),
    "low":    ("⚪", "#888888"),
}

STATUS_META = {
    "todo":        ("📋", "À faire",  "#888888"),
    "in_progress": ("⚙️",  "En cours", "#FF8C00"),
    "done":        ("✅", "Terminé",  "#32CD32"),
}

NEXT_STATUS = {
    "todo":        "in_progress",
    "in_progress": "done",
    "done":        "todo",
}

PRIORITY_SCORE = {"urgent": 4, "high": 3, "normal": 2, "low": 1}

DESC_MAX_CHARS = 120


def _separator(parent):
    ctk.CTkFrame(parent, height=1, fg_color=("gray70", "gray30")).pack(
        fill="x", padx=8, pady=2)


def _smart_sort_key(task: Task) -> tuple:
    """
    Calcule un score de tri intelligent.
    Plus le score est bas, plus la tache est prioritaire (tri ascendant).

    Criteres (par ordre d importance) :
    1. Taches done -> toujours en bas
    2. Echeance depassee + priorite
    3. Echeance aujourd hui + priorite
    4. Echeance cette semaine + priorite
    5. Priorite seule
    6. Date de creation
    """
    now   = datetime.now()
    today = now.date()
    week  = today + timedelta(days=7)

    # Taches terminees -> score eleve (en bas)
    if task.status == "done":
        return (99, 0, 0, task.created_at)

    prio_score = PRIORITY_SCORE.get(task.priority, 1)

    if task.reminder_at:
        remind_date = task.reminder_at.date()

        # Echeance depassee
        if task.reminder_at < now and not task.reminder_fired:
            return (0, 5 - prio_score, 0, task.created_at)

        # Echeance aujourd hui
        if remind_date == today:
            return (1, 5 - prio_score, 0, task.created_at)

        # Echeance cette semaine
        if today < remind_date <= week:
            return (2, 5 - prio_score, remind_date.toordinal(), task.created_at)

        # Echeance future
        return (3, 5 - prio_score, remind_date.toordinal(), task.created_at)

    # Pas d echeance — trier par priorite puis date
    return (4, 5 - prio_score, 0, task.created_at)


def _get_badge(task: Task) -> tuple[str, str] | None:
    """
    Retourne (texte_badge, couleur) ou None.
    Badges : EN RETARD / AUJOURD HUI / CETTE SEMAINE / DEMAIN
    """
    if not task.reminder_at or task.status == "done":
        return None

    now   = datetime.now()
    today = now.date()
    remind_date = task.reminder_at.date()

    if task.reminder_at < now and not task.reminder_fired:
        return ("⚠ EN RETARD", "#FF4444")

    if remind_date == today:
        return ("🔔 AUJOURD'HUI", "#FF8C00")

    if remind_date == today + timedelta(days=1):
        return ("📅 DEMAIN", "#FFD700")

    if remind_date <= today + timedelta(days=7):
        days_left = (remind_date - today).days
        return (f"📅 J-{days_left}", "#32CD32")

    return None


class TaskPanel(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, corner_radius=12)
        self._cat_id = None
        self._build()

    def _build(self):
        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=12, pady=(12, 6))

        self._title_label = ctk.CTkLabel(
            header, text="📋  Toutes les tâches",
            font=ctk.CTkFont(size=16, weight="bold"))
        self._title_label.pack(side="left")

        ctk.CTkButton(header, text="＋  Nouvelle tâche",
            height=32, corner_radius=8,
            command=self._open_add_form).pack(side="right")

        # Filtres statut
        filter_row = ctk.CTkFrame(self, fg_color="transparent")
        filter_row.pack(fill="x", padx=12, pady=(0, 4))

        self._status_var = ctk.StringVar(value="all")
        for val, label in [("all","Toutes"), ("todo","À faire"),
                           ("in_progress","En cours"), ("done","Terminées")]:
            ctk.CTkRadioButton(filter_row, text=label,
                variable=self._status_var, value=val,
                command=lambda: self.refresh(self._cat_id)
            ).pack(side="left", padx=8)

        # Légende badges
        legend = ctk.CTkFrame(self, fg_color="transparent")
        legend.pack(fill="x", padx=12, pady=(0, 4))
        ctk.CTkLabel(legend, text="Tri intelligent :",
            font=ctk.CTkFont(size=10), text_color="gray"
        ).pack(side="left", padx=(0,6))
        for text, color in [
            ("⚠ EN RETARD","#FF4444"),
            ("🔔 AUJOURD'HUI","#FF8C00"),
            ("📅 DEMAIN","#FFD700"),
            ("📅 J-N","#32CD32"),
        ]:
            ctk.CTkLabel(legend, text=text,
                font=ctk.CTkFont(size=10, weight="bold"),
                text_color=color
            ).pack(side="left", padx=6)

        # ── Barre actions taches terminees ────────────────────────────────────
        actions_row = ctk.CTkFrame(self, fg_color="transparent")
        actions_row.pack(fill="x", padx=12, pady=(0, 4))

        self._done_count_label = ctk.CTkLabel(
            actions_row, text="",
            font=ctk.CTkFont(size=11), text_color="#32CD32"
        )
        self._done_count_label.pack(side="left", padx=(0, 10))

        ctk.CTkButton(actions_row,
            text="📦 Archiver terminées",
            height=26, width=165,
            fg_color="#2a3a2a", hover_color="#3a5a3a",
            font=ctk.CTkFont(size=11),
            command=self._archive_done
        ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(actions_row,
            text="🗑 Supprimer terminées",
            height=26, width=170,
            fg_color="#3a1a1a", hover_color="#5a2a2a",
            font=ctk.CTkFont(size=11),
            command=self._delete_done
        ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(actions_row,
            text="🗂 Archives",
            height=26, width=90,
            fg_color="#2a2a3a", hover_color="#3a3a6a",
            font=ctk.CTkFont(size=11),
            command=self._show_archives
        ).pack(side="left")

        _separator(self)

        self._scroll = ctk.CTkScrollableFrame(self, corner_radius=0)
        self._scroll.pack(fill="both", expand=True, padx=4, pady=4)

    def refresh(self, category_id=None, status_filter=None,
                priority_filter=None, keyword=None):
        self._cat_id = category_id
        status = status_filter or (
            None if self._status_var.get() == "all" else self._status_var.get())
        tasks = get_tasks(category_id=category_id, status=status)

        if priority_filter:
            tasks = [t for t in tasks if t.priority == priority_filter]
        if keyword:
            kw = keyword.lower()
            tasks = [t for t in tasks
                     if kw in (t.title or "").lower()
                     or kw in (t.description or "").lower()]

        # Tri intelligent
        tasks = sorted(tasks, key=_smart_sort_key)

        cats = {c.id: c for c in get_categories()}
        cat_name = cats[category_id].name if category_id and category_id in cats else "Toutes"

        # Compter les taches en retard
        now      = datetime.now()
        overdue  = sum(1 for t in tasks
                       if t.reminder_at and t.reminder_at < now
                       and not t.reminder_fired and t.status != "done")
        overdue_str = f"  ⚠ {overdue} en retard" if overdue else ""

        self._title_label.configure(
            text=f"📋  {cat_name}  ({len(tasks)} tâche(s)){overdue_str}"
        )

        for w in self._scroll.winfo_children():
            w.destroy()

        # Mettre a jour le compteur des terminées
        done_count = get_done_count(category_id=category_id)
        if done_count > 0:
            self._done_count_label.configure(
                text=f"✅ {done_count} terminée(s)",
                text_color="#32CD32"
            )
        else:
            self._done_count_label.configure(text="")

        if not tasks:
            if category_id is not None:
                msg = (
                    "Aucune tâche dans cette catégorie.\n\n"
                    "Note : des tâches créées sans catégorie\n"
                    "apparaissent uniquement dans \"Toutes les tâches\"."
                )
            else:
                msg = "Aucune tâche ici. Clique sur ＋ pour commencer !"
            ctk.CTkLabel(self._scroll,
                text=msg,
                text_color="gray",
                font=ctk.CTkFont(size=12),
                justify="center"
            ).pack(pady=40)
            return

        # Separateurs de groupe
        last_group = None
        GROUP_LABELS = {
            0: ("⚠️  En retard",        "#FF4444"),
            1: ("🔔  Aujourd'hui",       "#FF8C00"),
            2: ("📅  Cette semaine",      "#FFD700"),
            3: ("🗓️  Prochainement",      "#1E90FF"),
            4: ("📋  Sans échéance",      "#888888"),
            99: ("✅  Terminées",         "#32CD32"),
        }

        for t in tasks:
            group = _smart_sort_key(t)[0]
            if group != last_group:
                last_group = group
                label_text, label_color = GROUP_LABELS.get(
                    group, ("", "#888888"))
                if label_text:
                    grp_frame = ctk.CTkFrame(
                        self._scroll, fg_color="transparent")
                    grp_frame.pack(fill="x", padx=8, pady=(10, 2))
                    ctk.CTkFrame(grp_frame, height=1,
                        fg_color=label_color
                    ).pack(fill="x", side="left", expand=True, padx=(0,8))
                    ctk.CTkLabel(grp_frame, text=label_text,
                        font=ctk.CTkFont(size=11, weight="bold"),
                        text_color=label_color
                    ).pack(side="left")
                    ctk.CTkFrame(grp_frame, height=1,
                        fg_color=label_color
                    ).pack(fill="x", side="left", expand=True, padx=(8,0))

            self._make_card(t, cats)

    def _make_card(self, task: Task, cats: dict):
        icon, color              = PRIORITY_META.get(task.priority, ("🔵","#1E90FF"))
        s_icon, s_label, s_color = STATUS_META.get(task.status, ("📋","À faire","#888888"))
        cat                      = cats.get(task.category_id)
        badge                    = _get_badge(task)

        # Couleur bordure : rouge si en retard, sinon couleur priorite
        border_color = "#FF4444" if (badge and "RETARD" in badge[0]) else color

        card = ctk.CTkFrame(self._scroll, corner_radius=10,
                            border_width=1, border_color=border_color)
        card.pack(fill="x", padx=8, pady=4)

        # ── Ligne 1 : priorité + titre + badge échéance + statut ─────────────
        row1 = ctk.CTkFrame(card, fg_color="transparent")
        row1.pack(fill="x", padx=10, pady=(8, 2))

        ctk.CTkLabel(row1, text=icon, width=20).pack(side="left")
        ctk.CTkLabel(row1, text=task.title,
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w"
        ).pack(side="left", padx=6, fill="x", expand=True)

        # Badge échéance (EN RETARD / AUJOURD HUI / DEMAIN / J-N)
        if badge:
            badge_text, badge_color = badge
            ctk.CTkLabel(row1,
                text=badge_text,
                font=ctk.CTkFont(size=10, weight="bold"),
                text_color=badge_color
            ).pack(side="right", padx=(4,6))

        # Badge statut cliquable
        next_s = NEXT_STATUS[task.status]
        ctk.CTkButton(row1,
            text=f"{s_icon} {s_label}",
            font=ctk.CTkFont(size=11),
            height=24, width=110, corner_radius=6,
            fg_color=s_color,
            hover_color=STATUS_META[next_s][2],
            text_color="white",
            command=lambda tid=task.id, ns=next_s: self._cycle_status(tid, ns)
        ).pack(side="right", padx=(0,0))

        # ── Ligne 2 : description tronquée ───────────────────────────────────
        if task.description:
            desc_full  = task.description.strip()
            desc_short = desc_full.replace("\n", " ")[:DESC_MAX_CHARS]
            is_long    = len(desc_full) > DESC_MAX_CHARS or "\n" in desc_full

            desc_row = ctk.CTkFrame(card, fg_color="transparent")
            desc_row.pack(fill="x", padx=36, pady=(0, 2))

            desc_label = ctk.CTkLabel(desc_row,
                text=desc_short + ("..." if is_long else ""),
                text_color="gray", anchor="w",
                font=ctk.CTkFont(size=11),
                wraplength=500, justify="left")
            desc_label.pack(side="left", fill="x", expand=True)

            if is_long:
                _state = {"expanded": False}
                toggle_btn = ctk.CTkButton(desc_row,
                    text="▼ plus", width=60, height=18,
                    fg_color="transparent",
                    hover_color=("gray80","gray25"),
                    text_color="#1E90FF",
                    font=ctk.CTkFont(size=10),
                    anchor="n")
                toggle_btn.pack(side="right", anchor="n", padx=(4,0))

                def _toggle(lbl=desc_label, btn=toggle_btn,
                            full=desc_full, short=desc_short, state=_state):
                    if state["expanded"]:
                        lbl.configure(text=short + "...", wraplength=500)
                        btn.configure(text="▼ plus")
                        state["expanded"] = False
                    else:
                        lbl.configure(text=full, wraplength=500)
                        btn.configure(text="▲ moins")
                        state["expanded"] = True
                toggle_btn.configure(command=_toggle)

        # ── Ligne 3 : meta ────────────────────────────────────────────────────
        row3 = ctk.CTkFrame(card, fg_color="transparent")
        row3.pack(fill="x", padx=10, pady=(0, 4))

        if cat:
            ctk.CTkLabel(row3, text=f"● {cat.name}",
                text_color=cat.color,
                font=ctk.CTkFont(size=10)).pack(side="left", padx=4)

        if task.reminder_at:
            fired  = " ✓" if task.reminder_fired else ""
            now    = datetime.now()
            is_late = task.reminder_at < now and not task.reminder_fired
            r_color = "#FF4444" if is_late else "#FFD700"
            ctk.CTkLabel(row3,
                text=f"⏰ {task.reminder_at.strftime('%d/%m/%Y %H:%M')}{fired}",
                text_color=r_color,
                font=ctk.CTkFont(size=10)
            ).pack(side="left", padx=8)

        # Badge recurrence
        rec_text = RecurrenceWidget.format_recurrence(
            task.recurrence, task.recurrence_days)
        if rec_text:
            ctk.CTkLabel(row3, text=rec_text,
                text_color="#9370DB",
                font=ctk.CTkFont(size=10)
            ).pack(side="left", padx=4)

        # ── Ligne 4 : pièces jointes ──────────────────────────────────────────
        attachments = get_task_attachments(task)
        if attachments:
            att_frame = ctk.CTkFrame(card, fg_color="transparent")
            att_frame.pack(fill="x", padx=10, pady=(0, 4))
            for path in attachments:
                if os.path.exists(path):
                    fname = os.path.basename(path)
                    ext   = os.path.splitext(fname)[1].lower()
                    icons = {".pdf":"📕",".docx":"📘",".doc":"📘",
                             ".xlsx":"📗",".xls":"📗",".txt":"📄",
                             ".png":"🖼️",".jpg":"🖼️",".jpeg":"🖼️"}
                    att_icon = icons.get(ext, "📎")
                    ctk.CTkButton(att_frame,
                        text=f"{att_icon} {fname}",
                        height=22, fg_color="transparent",
                        hover_color=("gray80","gray25"),
                        text_color="#88BBFF",
                        font=ctk.CTkFont(size=10), anchor="w",
                        command=lambda p=path: os.startfile(p)
                    ).pack(side="left", padx=(0,6))

        # ── Sous-taches ───────────────────────────────────────────────────────
        sub_frame = ctk.CTkFrame(card,
            fg_color=("gray92", "gray17"), corner_radius=6)
        sub_frame.pack(fill="x", padx=10, pady=(0, 6))

        SubTaskWidget(
            sub_frame,
            task_id=task.id,
            task_title=task.title,
            task_desc=task.description or "",
            on_change=lambda: self.refresh(self._cat_id)
        ).pack(fill="x", padx=8, pady=6)

        # ── Boutons actions ───────────────────────────────────────────────────
        actions = ctk.CTkFrame(card, fg_color="transparent")
        actions.pack(fill="x", padx=10, pady=(2, 6))

        ctk.CTkButton(actions, text="✏️ Éditer", width=80, height=26,
            command=lambda t=task: self._open_edit_form(t)
        ).pack(side="left", padx=4)

        ctk.CTkButton(actions, text="🗑 Supprimer", width=100, height=26,
            fg_color="#5a2a2a", hover_color="#8b0000",
            command=lambda tid=task.id: (
                delete_task(tid), self.refresh(self._cat_id))
        ).pack(side="right", padx=4)

    def _cycle_status(self, task_id: int, new_status: str):
        update_task(task_id, status=new_status)
        self.refresh(self._cat_id)

    def _archive_done(self):
        """Archive toutes les taches terminees."""
        count = archive_all_done(category_id=self._cat_id)
        self.refresh(self._cat_id)
        print(f"[Archive] {count} tache(s) archivee(s)")

    def _delete_done(self):
        """Supprime definitivement les taches terminees."""
        import tkinter.messagebox as mb
        count = get_done_count(category_id=self._cat_id)
        if count == 0:
            return
        if mb.askyesno(
            "Confirmer la suppression",
            f"Supprimer definitivement {count} tache(s) terminee(s) ?\n"
            "Cette action est irreversible.",
            icon="warning"
        ):
            deleted = delete_all_done(category_id=self._cat_id)
            self.refresh(self._cat_id)
            print(f"[Archive] {deleted} tache(s) supprimee(s)")

    def _show_archives(self):
        """Ouvre la fenetre des taches archivees."""
        ArchiveWindow(self, category_id=self._cat_id,
                      on_restore=lambda: self.refresh(self._cat_id))

    def _open_add_form(self):
        TaskForm(self, task=None, category_id=self._cat_id,
                 on_save=lambda: self.refresh(self._cat_id))

    def _open_edit_form(self, task: Task):
        TaskForm(self, task=task, category_id=task.category_id,
                 on_save=lambda: self.refresh(self._cat_id))


class ArchiveWindow(ctk.CTkToplevel):
    """Fenetre des taches archivees avec restauration possible."""

    def __init__(self, master, category_id=None, on_restore=None):
        super().__init__(master)
        self._cat_id    = category_id
        self._on_restore = on_restore
        self.title("🗂 Archives")
        self.geometry("700x500")
        self.minsize(600, 400)
        self.grab_set()
        self._build()

    def _build(self):
        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=14, pady=(12, 6))

        ctk.CTkLabel(header, text="🗂  Tâches archivées",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color="#888"
        ).pack(side="left")

        ctk.CTkButton(header, text="🗑 Tout supprimer",
            height=28, width=130,
            fg_color="#3a1a1a", hover_color="#5a2a2a",
            font=ctk.CTkFont(size=11),
            command=self._delete_all
        ).pack(side="right")

        # Liste
        self._scroll = ctk.CTkScrollableFrame(self)
        self._scroll.pack(fill="both", expand=True, padx=10, pady=4)

        # Bouton fermer
        ctk.CTkButton(self, text="Fermer", height=34,
            fg_color="gray30", command=self.destroy
        ).pack(padx=14, pady=(4, 12))

        self._refresh()

    def _refresh(self):
        from core.database import get_archived_tasks, get_categories
        for w in self._scroll.winfo_children():
            w.destroy()

        tasks = get_archived_tasks(category_id=self._cat_id)
        cats  = {c.id: c for c in get_categories()}

        if not tasks:
            ctk.CTkLabel(self._scroll,
                text="Aucune tâche archivée.",
                text_color="gray", font=ctk.CTkFont(size=13)
            ).pack(pady=30)
            return

        for t in tasks:
            cat = cats.get(t.category_id)
            row = ctk.CTkFrame(self._scroll,
                fg_color=("gray85","gray20"), corner_radius=8)
            row.pack(fill="x", padx=6, pady=3)

            info = ctk.CTkFrame(row, fg_color="transparent")
            info.pack(side="left", fill="x", expand=True, padx=10, pady=6)

            ctk.CTkLabel(info, text=t.title,
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color="#888", anchor="w"
            ).pack(fill="x")

            meta = f"{cat.name if cat else ''}"
            if t.updated_at:
                meta += f"  |  Archivée le {t.updated_at.strftime('%d/%m/%Y')}"
            ctk.CTkLabel(info, text=meta,
                font=ctk.CTkFont(size=10), text_color="#555", anchor="w"
            ).pack(fill="x")

            # Boutons
            btns = ctk.CTkFrame(row, fg_color="transparent")
            btns.pack(side="right", padx=8)

            ctk.CTkButton(btns, text="↩ Restaurer",
                height=26, width=90,
                fg_color="#1a3a1a", hover_color="#2a5a2a",
                font=ctk.CTkFont(size=10),
                command=lambda tid=t.id: self._restore(tid)
            ).pack(side="left", padx=3)

            ctk.CTkButton(btns, text="✕",
                height=26, width=30,
                fg_color="#3a1a1a", hover_color="#5a2a2a",
                font=ctk.CTkFont(size=10),
                command=lambda tid=t.id: self._delete_one(tid)
            ).pack(side="left", padx=3)

    def _restore(self, task_id: int):
        from core.database import unarchive_task
        unarchive_task(task_id)
        self._refresh()
        if self._on_restore:
            self._on_restore()

    def _delete_one(self, task_id: int):
        from core.database import delete_task
        delete_task(task_id)
        self._refresh()

    def _delete_all(self):
        import tkinter.messagebox as mb
        tasks = get_archived_tasks(category_id=self._cat_id)
        if not tasks:
            return
        if mb.askyesno("Confirmer",
            f"Supprimer definitivement {len(tasks)} tache(s) archivee(s) ?",
            icon="warning"):
            from core.database import delete_task
            for t in tasks:
                delete_task(t.id)
            self._refresh()
            if self._on_restore:
                self._on_restore()
