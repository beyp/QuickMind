import customtkinter as ctk
import tkinter.filedialog as fd
from datetime import datetime
from core.database import get_categories, add_task, update_task
from core.file_handler import save_attachment
from ui.datetime_picker import DateTimePicker


class TaskForm(ctk.CTkToplevel):
    """Formulaire d ajout / edition de tache avec DateTimePicker integre."""

    def __init__(self, master, task, category_id, on_save):
        super().__init__(master)
        self.task        = task
        self.on_save     = on_save
        self._attachment = task.attachment_path if task else None
        self._reminder_dt: datetime | None = task.reminder_at if task else None

        self.title("Editer la tache" if task else "Nouvelle tache")
        self.geometry("520x600")
        self.resizable(False, False)
        self.grab_set()

        cats = get_categories()
        self._cat_map   = {c.name: c.id for c in cats}
        self._cat_names = [c.name for c in cats]
        default_cat = next(
            (c.name for c in cats if c.id == category_id),
            self._cat_names[0] if self._cat_names else ""
        )

        pad = {"padx": 16, "pady": 5}

        # ── Titre ─────────────────────────────────────────────────────────
        ctk.CTkLabel(self, text="Titre *", anchor="w").pack(fill="x", **pad)
        self._title_e = ctk.CTkEntry(self, height=36)
        self._title_e.pack(fill="x", **pad)
        if task:
            self._title_e.insert(0, task.title or "")

        # ── Description ───────────────────────────────────────────────────
        ctk.CTkLabel(self, text="Description", anchor="w").pack(fill="x", **pad)
        self._desc_e = ctk.CTkTextbox(self, height=70)
        self._desc_e.pack(fill="x", **pad)
        if task and task.description:
            self._desc_e.insert("0.0", task.description)

        # ── Categorie ─────────────────────────────────────────────────────
        ctk.CTkLabel(self, text="Categorie", anchor="w").pack(fill="x", **pad)
        self._cat_var = ctk.StringVar(value=default_cat)
        ctk.CTkOptionMenu(
            self, values=self._cat_names,
            variable=self._cat_var
        ).pack(fill="x", **pad)

        # ── Priorite ──────────────────────────────────────────────────────
        ctk.CTkLabel(self, text="Priorite", anchor="w").pack(fill="x", **pad)
        self._prio_var = ctk.StringVar(value=task.priority if task else "normal")
        ctk.CTkSegmentedButton(
            self,
            values=["low", "normal", "high", "urgent"],
            variable=self._prio_var
        ).pack(fill="x", **pad)

        # ── Statut (edition seulement) ────────────────────────────────────
        if task:
            ctk.CTkLabel(self, text="Statut", anchor="w").pack(fill="x", **pad)
            self._status_var = ctk.StringVar(value=task.status)
            ctk.CTkSegmentedButton(
                self,
                values=["todo", "in_progress", "done"],
                variable=self._status_var
            ).pack(fill="x", **pad)

        # ── Rappel — DateTimePicker ────────────────────────────────────────
        ctk.CTkLabel(self, text="Rappel", anchor="w").pack(fill="x", **pad)

        remind_row = ctk.CTkFrame(self, fg_color="transparent")
        remind_row.pack(fill="x", **pad)

        # Label affichant la date choisie
        self._remind_label = ctk.CTkLabel(
            remind_row,
            text=self._format_reminder(self._reminder_dt),
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#1E90FF" if self._reminder_dt else "gray",
            anchor="w"
        )
        self._remind_label.pack(side="left", fill="x", expand=True)

        ctk.CTkButton(
            remind_row,
            text="📅 Choisir",
            width=100, height=30,
            command=self._open_picker
        ).pack(side="right", padx=(8, 0))

        ctk.CTkButton(
            remind_row,
            text="✕",
            width=30, height=30,
            fg_color="gray30",
            command=self._clear_reminder
        ).pack(side="right", padx=(4, 0))

        # ── Piece jointe ──────────────────────────────────────────────────
        att_row = ctk.CTkFrame(self, fg_color="transparent")
        att_row.pack(fill="x", **pad)
        self._att_label = ctk.CTkLabel(
            att_row,
            text=f"Fichier : {self._attachment}" if self._attachment else "Aucun fichier joint",
            text_color="#88BBFF" if self._attachment else "gray",
            anchor="w"
        )
        self._att_label.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            att_row, text="Parcourir", width=100,
            command=self._browse
        ).pack(side="right")

        # ── Boutons ───────────────────────────────────────────────────────
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(12, 16))
        ctk.CTkButton(
            btn_row, text="Enregistrer",
            command=self._save
        ).pack(side="left", expand=True, padx=4)
        ctk.CTkButton(
            btn_row, text="Annuler",
            fg_color="gray30",
            command=self.destroy
        ).pack(side="right", expand=True, padx=4)

    # ── Helpers ──────────────────────────────────────────────────────────
    def _format_reminder(self, dt: datetime | None) -> str:
        if not dt:
            return "Aucun rappel defini"
        DAYS_FR   = ["Lundi","Mardi","Mercredi","Jeudi","Vendredi","Samedi","Dimanche"]
        MONTHS_FR = ["jan","fev","mar","avr","mai","jun",
                     "jul","aou","sep","oct","nov","dec"]
        return (
            f"{DAYS_FR[dt.weekday()]} {dt.day} {MONTHS_FR[dt.month-1]}"
            f" {dt.year}  a  {dt.hour:02d}:{dt.minute:02d}"
        )

    def _open_picker(self):
        DateTimePicker(
            self,
            on_select=self._on_datetime_selected,
            initial=self._reminder_dt
        )

    def _on_datetime_selected(self, dt: datetime | None):
        self._reminder_dt = dt
        if dt:
            self._remind_label.configure(
                text=self._format_reminder(dt),
                text_color="#1E90FF"
            )
        else:
            self._remind_label.configure(
                text="Aucun rappel defini",
                text_color="gray"
            )

    def _clear_reminder(self):
        self._reminder_dt = None
        self._remind_label.configure(
            text="Aucun rappel defini", text_color="gray"
        )

    def _browse(self):
        path = fd.askopenfilename()
        if path:
            self._attachment = path
            import os
            self._att_label.configure(
                text=f"Fichier : {os.path.basename(path)}",
                text_color="#88BBFF"
            )

    def _save(self):
        title = self._title_e.get().strip()
        if not title:
            return

        desc     = self._desc_e.get("0.0", "end").strip()
        cat_name = self._cat_var.get()
        cat_id   = self._cat_map.get(cat_name)
        prio     = self._prio_var.get()

        if self.task:
            status = self._status_var.get()
            update_task(
                self.task.id,
                title=title, description=desc,
                category_id=cat_id, priority=prio,
                status=status, reminder_at=self._reminder_dt,
                reminder_fired=False if self._reminder_dt else self.task.reminder_fired
            )
            if self._attachment and self._attachment != self.task.attachment_path:
                new_path = save_attachment(self._attachment, self.task.id)
                from core.database import get_task_attachments, set_task_attachments
                existing = get_task_attachments(self.task)
                if new_path not in existing:
                    existing.append(new_path)
                set_task_attachments(self.task.id, existing)
        else:
            new_task = add_task(
                title=title, description=desc,
                category_id=cat_id, priority=prio,
                reminder_at=self._reminder_dt
            )
            if self._attachment:
                new_path = save_attachment(self._attachment, new_task.id)
                update_task(new_task.id, attachment_path=new_path)

        self.on_save()
        self.destroy()
