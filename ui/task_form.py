import customtkinter as ctk
import tkinter.filedialog as fd
from datetime import datetime
from core.database import get_categories, add_task, update_task
from core.file_handler import save_attachment
from ui.datetime_picker import DateTimePicker
from ui.recurrence_widget import RecurrenceWidget


class TaskForm(ctk.CTkToplevel):
    def __init__(self, master, task, category_id, on_save):
        super().__init__(master)
        self.task         = task
        self.on_save      = on_save
        self._attachment  = task.attachment_path if task else None
        self._reminder_dt = task.reminder_at if task else None

        self.title("Editer" if task else "Nouvelle tache")
        self.geometry("540x680")
        self.resizable(False, True)
        self.grab_set()

        cats            = get_categories()
        self._cat_map   = {c.name: c.id for c in cats}
        self._cat_names = [c.name for c in cats]
        default_cat     = next((c.name for c in cats if c.id == category_id),
                               self._cat_names[0] if self._cat_names else "")
        pad = {"padx": 16, "pady": 4}

        scroll = ctk.CTkScrollableFrame(self)
        scroll.pack(fill="both", expand=True)

        ctk.CTkLabel(scroll, text="Titre *", anchor="w").pack(fill="x", **pad)
        self._title_e = ctk.CTkEntry(scroll, height=36)
        self._title_e.pack(fill="x", **pad)
        if task: self._title_e.insert(0, task.title or "")

        ctk.CTkLabel(scroll, text="Description", anchor="w").pack(fill="x", **pad)
        self._desc_e = ctk.CTkTextbox(scroll, height=70)
        self._desc_e.pack(fill="x", **pad)
        if task and task.description:
            self._desc_e.insert("0.0", task.description)

        ctk.CTkLabel(scroll, text="Categorie", anchor="w").pack(fill="x", **pad)
        self._cat_var = ctk.StringVar(value=default_cat)
        ctk.CTkOptionMenu(scroll, values=self._cat_names,
            variable=self._cat_var).pack(fill="x", **pad)

        ctk.CTkLabel(scroll, text="Priorite", anchor="w").pack(fill="x", **pad)
        self._prio_var = ctk.StringVar(value=task.priority if task else "normal")
        ctk.CTkSegmentedButton(scroll,
            values=["low","normal","high","urgent"],
            variable=self._prio_var).pack(fill="x", **pad)

        if task:
            ctk.CTkLabel(scroll, text="Statut", anchor="w").pack(fill="x", **pad)
            self._status_var = ctk.StringVar(value=task.status)
            ctk.CTkSegmentedButton(scroll,
                values=["todo","in_progress","done"],
                variable=self._status_var).pack(fill="x", **pad)

        ctk.CTkLabel(scroll, text="Rappel", anchor="w").pack(fill="x", **pad)
        remind_row = ctk.CTkFrame(scroll, fg_color="transparent")
        remind_row.pack(fill="x", **pad)
        self._remind_label = ctk.CTkLabel(remind_row,
            text=self._fmt(self._reminder_dt),
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#1E90FF" if self._reminder_dt else "gray",
            anchor="w")
        self._remind_label.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(remind_row, text="Choisir", width=90, height=30,
            command=self._open_picker).pack(side="right", padx=(8,0))
        ctk.CTkButton(remind_row, text="X", width=30, height=30,
            fg_color="gray30",
            command=self._clear_reminder).pack(side="right", padx=(4,0))

        ctk.CTkFrame(scroll, height=1,
            fg_color=("gray70","gray30")).pack(fill="x", padx=8, pady=6)

        self._rec_widget = RecurrenceWidget(scroll,
            recurrence=task.recurrence if task else None,
            recurrence_days=task.recurrence_days if task else None)
        self._rec_widget.pack(fill="x", **pad)

        ctk.CTkFrame(scroll, height=1,
            fg_color=("gray70","gray30")).pack(fill="x", padx=8, pady=6)

        att_row = ctk.CTkFrame(scroll, fg_color="transparent")
        att_row.pack(fill="x", **pad)
        self._att_label = ctk.CTkLabel(att_row,
            text=f"PJ : {self._attachment}" if self._attachment else "Aucun fichier",
            text_color="#88BBFF" if self._attachment else "gray", anchor="w")
        self._att_label.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(att_row, text="Parcourir", width=100,
            command=self._browse).pack(side="right")

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(8,16))
        ctk.CTkButton(btn_row, text="Enregistrer",
            command=self._save).pack(side="left", expand=True, padx=4)
        ctk.CTkButton(btn_row, text="Annuler", fg_color="gray30",
            command=self.destroy).pack(side="right", expand=True, padx=4)

    def _fmt(self, dt):
        if not dt: return "Aucun rappel"
        DAYS   = ["Lundi","Mardi","Mercredi","Jeudi","Vendredi","Samedi","Dimanche"]
        MONTHS = ["jan","fev","mar","avr","mai","jun","jul","aou","sep","oct","nov","dec"]
        return f"{DAYS[dt.weekday()]} {dt.day} {MONTHS[dt.month-1]} {dt.year}  {dt.hour:02d}:{dt.minute:02d}"

    def _open_picker(self):
        DateTimePicker(self, on_select=self._on_dt, initial=self._reminder_dt)

    def _on_dt(self, dt):
        self._reminder_dt = dt
        self._remind_label.configure(
            text=self._fmt(dt) if dt else "Aucun rappel",
            text_color="#1E90FF" if dt else "gray")

    def _clear_reminder(self):
        self._reminder_dt = None
        self._remind_label.configure(text="Aucun rappel", text_color="gray")

    def _browse(self):
        path = fd.askopenfilename()
        if path:
            import os
            self._attachment = path
            self._att_label.configure(
                text=f"PJ : {os.path.basename(path)}", text_color="#88BBFF")

    def _save(self):
        title = self._title_e.get().strip()
        if not title: return
        desc     = self._desc_e.get("0.0","end").strip()
        cat_id   = self._cat_map.get(self._cat_var.get())
        prio     = self._prio_var.get()
        rec      = self._rec_widget.get_recurrence()
        rec_days = self._rec_widget.get_recurrence_days()

        if self.task:
            status = self._status_var.get()
            update_task(self.task.id,
                title=title, description=desc, category_id=cat_id,
                priority=prio, status=status, reminder_at=self._reminder_dt,
                reminder_fired=False if self._reminder_dt else self.task.reminder_fired,
                recurrence=rec, recurrence_days=rec_days)
            if status == "done" and self.task.status != "done" and rec and rec != "none":
                from core.database import create_next_recurrence
                create_next_recurrence(self.task.id)
            if self._attachment and self._attachment != self.task.attachment_path:
                new_path = save_attachment(self._attachment, self.task.id)
                from core.database import get_task_attachments, set_task_attachments
                existing = get_task_attachments(self.task)
                if new_path not in existing: existing.append(new_path)
                set_task_attachments(self.task.id, existing)
        else:
            new_task = add_task(title=title, description=desc,
                category_id=cat_id, priority=prio,
                reminder_at=self._reminder_dt, recurrence=rec,
                recurrence_days=rec_days)
            if self._attachment:
                new_path = save_attachment(self._attachment, new_task.id)
                update_task(new_task.id, attachment_path=new_path)
        self.on_save()
        self.destroy()
