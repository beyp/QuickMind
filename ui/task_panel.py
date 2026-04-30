import customtkinter as ctk
from core.database import (get_tasks, get_categories, add_task,
                           update_task, delete_task, get_task_attachments)
from core.models import Task
from ui.task_form import TaskForm
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

DESC_MAX_CHARS = 120


def _separator(parent):
    ctk.CTkFrame(parent, height=1, fg_color=("gray70", "gray30")).pack(
        fill="x", padx=8, pady=2)


class TaskPanel(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, corner_radius=12)
        self._cat_id = None
        self._build()

    def _build(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=12, pady=(12, 6))

        self._title_label = ctk.CTkLabel(
            header, text="📋  Toutes les tâches",
            font=ctk.CTkFont(size=16, weight="bold"))
        self._title_label.pack(side="left")

        ctk.CTkButton(header, text="＋  Nouvelle tâche",
            height=32, corner_radius=8,
            command=self._open_add_form).pack(side="right")

        filter_row = ctk.CTkFrame(self, fg_color="transparent")
        filter_row.pack(fill="x", padx=12, pady=(0, 6))

        self._status_var = ctk.StringVar(value="all")
        for val, label in [("all","Toutes"),("todo","À faire"),
                           ("in_progress","En cours"),("done","Terminées")]:
            ctk.CTkRadioButton(filter_row, text=label,
                variable=self._status_var, value=val,
                command=lambda: self.refresh(self._cat_id)
            ).pack(side="left", padx=8)

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

        cats = {c.id: c for c in get_categories()}
        cat_name = cats[category_id].name if category_id and category_id in cats else "Toutes"
        self._title_label.configure(text=f"📋  {cat_name}  ({len(tasks)} tâche(s))")

        for w in self._scroll.winfo_children():
            w.destroy()

        if not tasks:
            ctk.CTkLabel(self._scroll,
                text="Aucune tâche ici. Clique sur ＋ pour commencer !",
                text_color="gray", font=ctk.CTkFont(size=13)).pack(pady=40)
            return

        for t in tasks:
            self._make_card(t, cats)

    def _make_card(self, task: Task, cats: dict):
        icon, color              = PRIORITY_META.get(task.priority, ("🔵","#1E90FF"))
        s_icon, s_label, s_color = STATUS_META.get(task.status, ("📋","À faire","#888888"))
        cat                      = cats.get(task.category_id)

        card = ctk.CTkFrame(self._scroll, corner_radius=10,
                            border_width=1, border_color=color)
        card.pack(fill="x", padx=8, pady=5)

        # ── Ligne 1 : priorité + titre + badge statut cliquable ──────────
        row1 = ctk.CTkFrame(card, fg_color="transparent")
        row1.pack(fill="x", padx=10, pady=(8, 2))

        ctk.CTkLabel(row1, text=icon, width=20).pack(side="left")
        ctk.CTkLabel(row1, text=task.title,
            font=ctk.CTkFont(size=13, weight="bold"),
            anchor="w").pack(side="left", padx=6, fill="x", expand=True)

        next_s = NEXT_STATUS[task.status]
        ctk.CTkButton(row1,
            text=f"{s_icon} {s_label}",
            font=ctk.CTkFont(size=11),
            height=24, width=110, corner_radius=6,
            fg_color=s_color,
            hover_color=STATUS_META[next_s][2],
            text_color="white",
            command=lambda tid=task.id, ns=next_s: self._cycle_status(tid, ns)
        ).pack(side="right", padx=(6, 0))

        # ── Ligne 2 : description tronquée + toggle ───────────────────────
        if task.description:
            desc_full  = task.description.strip()
            # Version courte : on tronque et supprime les sauts de ligne
            desc_short = desc_full.replace("\n", " ")[:DESC_MAX_CHARS]
            is_long    = len(desc_full) > DESC_MAX_CHARS or "\n" in desc_full

            # Conteneur de la description (1 seule ligne avec toggle)
            desc_row = ctk.CTkFrame(card, fg_color="transparent")
            desc_row.pack(fill="x", padx=36, pady=(0, 2))

            # Label de description (gauche, expand)
            desc_label = ctk.CTkLabel(
                desc_row,
                text=desc_short + ("..." if is_long else ""),
                text_color="gray", anchor="w",
                font=ctk.CTkFont(size=11),
                wraplength=500, justify="left")
            desc_label.pack(side="left", fill="x", expand=True)

            if is_long:
                _state = {"expanded": False}

                # Bouton toggle ancré à droite EN HAUT (side="top" dans un sous-frame)
                toggle_btn = ctk.CTkButton(
                    desc_row,
                    text="▼ plus",
                    width=60, height=18,
                    fg_color="transparent",
                    hover_color=("gray80", "gray25"),
                    text_color="#1E90FF",
                    font=ctk.CTkFont(size=10),
                    anchor="n"
                )
                toggle_btn.pack(side="right", anchor="n", padx=(4, 0))

                def _toggle(lbl=desc_label, btn=toggle_btn,
                            full=desc_full, short=desc_short,
                            state=_state):
                    if state["expanded"]:
                        lbl.configure(text=short + "...", wraplength=500)
                        btn.configure(text="▼ plus")
                        state["expanded"] = False
                    else:
                        lbl.configure(text=full, wraplength=500)
                        btn.configure(text="▲ moins")
                        state["expanded"] = True

                toggle_btn.configure(command=_toggle)

        # ── Ligne 3 : meta (catégorie, rappel) ───────────────────────────
        row3 = ctk.CTkFrame(card, fg_color="transparent")
        row3.pack(fill="x", padx=10, pady=(0, 4))

        if cat:
            ctk.CTkLabel(row3, text=f"● {cat.name}",
                text_color=cat.color,
                font=ctk.CTkFont(size=10)).pack(side="left", padx=4)

        if task.reminder_at:
            fired = " ✓" if task.reminder_fired else ""
            ctk.CTkLabel(row3,
                text=f"⏰ {task.reminder_at.strftime('%d/%m/%Y %H:%M')}{fired}",
                text_color="#FFD700",
                font=ctk.CTkFont(size=10)).pack(side="left", padx=8)

        # ── Ligne 4 : TOUTES les pièces jointes ──────────────────────────
        attachments = get_task_attachments(task)
        if attachments:
            att_frame = ctk.CTkFrame(card, fg_color="transparent")
            att_frame.pack(fill="x", padx=10, pady=(0, 4))

            for path in attachments:
                if os.path.exists(path):
                    fname = os.path.basename(path)
                    # Icône selon extension
                    ext = os.path.splitext(fname)[1].lower()
                    if ext == ".pdf":
                        att_icon = "📕"
                    elif ext in (".doc", ".docx"):
                        att_icon = "📘"
                    elif ext in (".xls", ".xlsx"):
                        att_icon = "📗"
                    elif ext in (".txt",):
                        att_icon = "📄"
                    elif ext in (".png", ".jpg", ".jpeg", ".gif"):
                        att_icon = "🖼️"
                    else:
                        att_icon = "📎"

                    ctk.CTkButton(
                        att_frame,
                        text=f"{att_icon} {fname}",
                        height=22, fg_color="transparent",
                        hover_color=("gray80","gray25"),
                        text_color="#88BBFF",
                        font=ctk.CTkFont(size=10),
                        anchor="w",
                        command=lambda p=path: os.startfile(p)
                    ).pack(side="left", padx=(0, 6))

        # ── Boutons actions ──────────────────────────────────────────────
        actions = ctk.CTkFrame(card, fg_color="transparent")
        actions.pack(fill="x", padx=10, pady=(2, 6))

        ctk.CTkButton(actions, text="✏️ Éditer", width=80, height=26,
            command=lambda t=task: self._open_edit_form(t)).pack(side="left", padx=4)

        ctk.CTkButton(actions, text="🗑 Supprimer", width=100, height=26,
            fg_color="#5a2a2a", hover_color="#8b0000",
            command=lambda tid=task.id: (
                delete_task(tid), self.refresh(self._cat_id))
        ).pack(side="right", padx=4)

    def _cycle_status(self, task_id: int, new_status: str):
        update_task(task_id, status=new_status)
        self.refresh(self._cat_id)

    def _open_add_form(self):
        TaskForm(self, task=None, category_id=self._cat_id,
                 on_save=lambda: self.refresh(self._cat_id))

    def _open_edit_form(self, task: Task):
        TaskForm(self, task=task, category_id=task.category_id,
                 on_save=lambda: self.refresh(self._cat_id))
