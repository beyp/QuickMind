"""
Vue Kanban — 3 colonnes : A faire / En cours / Termine
Drag & drop entre colonnes via windnd sur les cartes.
"""
import customtkinter as ctk
from core.database import (get_tasks, get_categories, update_task,
                           delete_task, get_subtask_progress,
                           create_next_recurrence)
from core.models import Task
from ui.task_form import TaskForm
from ui.recurrence_widget import RecurrenceWidget
import os

COLUMNS = [
    ("todo",        "📋 À faire",   "#888888"),
    ("in_progress", "⚙️  En cours",  "#FF8C00"),
    ("done",        "✅ Terminé",   "#32CD32"),
]

PRIORITY_META = {
    "urgent": ("🔴", "#FF4444"),
    "high":   ("🟠", "#FF8C00"),
    "normal": ("🔵", "#1E90FF"),
    "low":    ("⚪", "#888888"),
}


class KanbanPanel(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master, corner_radius=12)
        self._cat_id       = None
        self._drag_task_id = None
        self._build()

    def _build(self):
        # Header
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=12, pady=(12,6))

        self._title_label = ctk.CTkLabel(header,
            text="📊  Vue Kanban",
            font=ctk.CTkFont(size=16, weight="bold"))
        self._title_label.pack(side="left")

        ctk.CTkButton(header, text="+ Nouvelle tache",
            height=32, corner_radius=8,
            command=self._open_add_form).pack(side="right")

        # Colonnes
        self._cols_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._cols_frame.pack(fill="both", expand=True, padx=8, pady=8)
        self._cols_frame.grid_columnconfigure(0, weight=1)
        self._cols_frame.grid_columnconfigure(1, weight=1)
        self._cols_frame.grid_columnconfigure(2, weight=1)
        self._cols_frame.grid_rowconfigure(0, weight=1)

        self._col_frames  = {}
        self._col_scrolls = {}

        for i, (status, label, color) in enumerate(COLUMNS):
            # Frame colonne
            col = ctk.CTkFrame(self._cols_frame, corner_radius=10,
                               border_width=1, border_color=color)
            col.grid(row=0, column=i, sticky="nsew", padx=6, pady=4)
            col.grid_rowconfigure(1, weight=1)
            col.grid_columnconfigure(0, weight=1)

            # Header colonne
            col_header = ctk.CTkFrame(col, fg_color="transparent")
            col_header.grid(row=0, column=0, sticky="ew", padx=8, pady=(8,4))

            self._col_count_labels = getattr(self, "_col_count_labels", {})
            ctk.CTkLabel(col_header, text=label,
                font=ctk.CTkFont(size=13, weight="bold"),
                text_color=color).pack(side="left")

            count_lbl = ctk.CTkLabel(col_header, text="0",
                font=ctk.CTkFont(size=11),
                text_color=color)
            count_lbl.pack(side="right")
            self._col_count_labels[status] = count_lbl

            # Zone scroll des cartes
            scroll = ctk.CTkScrollableFrame(col, corner_radius=0,
                                            fg_color="transparent")
            scroll.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)

            # Zone de drop (indicateur visuel)
            drop_zone = ctk.CTkFrame(col,
                height=4, fg_color="transparent", corner_radius=2)
            drop_zone.grid(row=2, column=0, sticky="ew", padx=8, pady=(0,4))

            self._col_frames[status]  = col
            self._col_scrolls[status] = scroll

            # Activer drop sur la colonne entiere
            self._setup_column_drop(col, scroll, drop_zone, status, color)

    def _setup_column_drop(self, col, scroll, drop_zone, target_status, color):
        """Active le drop sur une colonne Kanban via windnd."""
        try:
            import windnd

            def _on_enter(event=None):
                drop_zone.configure(fg_color=color, height=6)

            def _on_leave(event=None):
                drop_zone.configure(fg_color="transparent", height=4)

            def _on_drop(files):
                drop_zone.configure(fg_color="transparent", height=4)
                if self._drag_task_id is not None:
                    tid = self._drag_task_id
                    self._drag_task_id = None
                    # Recurrence si done
                    if target_status == "done":
                        from core.database import get_tasks as _gt
                        tasks = _gt()
                        task  = next((t for t in tasks if t.id == tid), None)
                        if task and task.recurrence and task.recurrence != "none":
                            create_next_recurrence(tid)
                    update_task(tid, status=target_status)
                    self.after(0, lambda: self.refresh(self._cat_id))

            windnd.hook_dropfiles(scroll, func=_on_drop)
            windnd.hook_dropfiles(col,    func=_on_drop)
        except Exception:
            pass

    def refresh(self, category_id=None):
        self._cat_id = category_id
        cats = {c.id: c for c in get_categories()}

        cat_name = cats[category_id].name if category_id and category_id in cats else "Toutes"
        self._title_label.configure(text=f"📊  Kanban — {cat_name}")

        for status, _, _ in COLUMNS:
            scroll = self._col_scrolls[status]
            for w in scroll.winfo_children():
                w.destroy()

            tasks = get_tasks(category_id=category_id, status=status)

            # Mettre a jour le compteur
            if hasattr(self, "_col_count_labels"):
                lbl = self._col_count_labels.get(status)
                if lbl: lbl.configure(text=str(len(tasks)))

            for task in tasks:
                self._make_kanban_card(scroll, task, cats, status)

    def _make_kanban_card(self, parent, task: Task, cats: dict, status: str):
        """Cree une carte Kanban draggable."""
        icon, color = PRIORITY_META.get(task.priority, ("🔵","#1E90FF"))
        cat         = cats.get(task.category_id)

        card = ctk.CTkFrame(parent, corner_radius=8,
                            border_width=1, border_color=color)
        card.pack(fill="x", padx=4, pady=3)

        # Header carte
        row1 = ctk.CTkFrame(card, fg_color="transparent")
        row1.pack(fill="x", padx=8, pady=(6,2))

        ctk.CTkLabel(row1, text=icon, width=16,
            font=ctk.CTkFont(size=11)).pack(side="left")
        ctk.CTkLabel(row1, text=task.title,
            font=ctk.CTkFont(size=11, weight="bold"),
            anchor="w", wraplength=180
        ).pack(side="left", padx=4, fill="x", expand=True)

        # Sous-taches progress
        done, total = get_subtask_progress(task.id)
        if total > 0:
            prog_row = ctk.CTkFrame(card, fg_color="transparent")
            prog_row.pack(fill="x", padx=8, pady=(0,2))
            pct = done / total
            pct_color = "#32CD32" if pct == 1.0 else "#1E90FF"
            ctk.CTkLabel(prog_row,
                text=f"{done}/{total}",
                font=ctk.CTkFont(size=9),
                text_color=pct_color, width=28
            ).pack(side="left")
            bar = ctk.CTkProgressBar(prog_row, height=5, corner_radius=2)
            bar.pack(side="left", fill="x", expand=True)
            bar.set(pct)
            bar.configure(progress_color=pct_color)

        # Meta
        meta = ctk.CTkFrame(card, fg_color="transparent")
        meta.pack(fill="x", padx=8, pady=(0,4))

        if cat:
            ctk.CTkLabel(meta, text=f"● {cat.name}",
                text_color=cat.color,
                font=ctk.CTkFont(size=9)).pack(side="left")

        if task.reminder_at:
            from datetime import datetime
            is_late = task.reminder_at < datetime.now() and not task.reminder_fired
            ctk.CTkLabel(meta,
                text=f"⏰ {task.reminder_at.strftime('%d/%m')}",
                text_color="#FF4444" if is_late else "#FFD700",
                font=ctk.CTkFont(size=9)).pack(side="left", padx=4)

        # Badge recurrence
        rec_text = RecurrenceWidget.format_recurrence(
            task.recurrence, task.recurrence_days)
        if rec_text:
            ctk.CTkLabel(meta, text=rec_text,
                text_color="#9370DB",
                font=ctk.CTkFont(size=9)).pack(side="left", padx=2)

        # Boutons
        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill="x", padx=8, pady=(0,6))

        # Fleches de deplacement entre colonnes
        col_order = ["todo","in_progress","done"]
        idx       = col_order.index(status)

        if idx > 0:
            prev_status = col_order[idx-1]
            ctk.CTkButton(btn_row, text="←", width=26, height=22,
                fg_color="gray30", hover_color="gray20",
                font=ctk.CTkFont(size=11),
                command=lambda tid=task.id, s=prev_status: (
                    update_task(tid, status=s),
                    self.refresh(self._cat_id))
            ).pack(side="left", padx=2)

        if idx < 2:
            next_status = col_order[idx+1]
            ctk.CTkButton(btn_row, text="→", width=26, height=22,
                fg_color="#1a3a5c", hover_color="#1E90FF",
                font=ctk.CTkFont(size=11),
                command=lambda tid=task.id, s=next_status: self._move_task(tid, s)
            ).pack(side="left", padx=2)

        ctk.CTkButton(btn_row, text="✏", width=26, height=22,
            fg_color="transparent", hover_color="gray30",
            command=lambda t=task: self._open_edit_form(t)
        ).pack(side="right", padx=2)

        ctk.CTkButton(btn_row, text="✕", width=26, height=22,
            fg_color="transparent", hover_color="#550000",
            text_color="#888",
            command=lambda tid=task.id: (
                delete_task(tid), self.refresh(self._cat_id))
        ).pack(side="right", padx=2)

        # Drag — stocker l ID de la tache draguee
        card.bind("<Button-1>",
            lambda e, tid=task.id: setattr(self, "_drag_task_id", tid))
        for w in card.winfo_children():
            w.bind("<Button-1>",
                lambda e, tid=task.id: setattr(self, "_drag_task_id", tid))

    def _move_task(self, task_id, new_status):
        """Deplace une tache et gere la recurrence si done."""
        from core.database import get_tasks as _gt
        tasks = _gt()
        task  = next((t for t in tasks if t.id == task_id), None)
        if task and new_status == "done" and task.recurrence and task.recurrence != "none":
            create_next_recurrence(task_id)
        update_task(task_id, status=new_status)
        self.refresh(self._cat_id)

    def _open_add_form(self):
        TaskForm(self, task=None, category_id=self._cat_id,
                 on_save=lambda: self.refresh(self._cat_id))

    def _open_edit_form(self, task: Task):
        TaskForm(self, task=task, category_id=task.category_id,
                 on_save=lambda: self.refresh(self._cat_id))
