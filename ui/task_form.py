import customtkinter as ctk
import tkinter.filedialog as fd
from datetime import datetime
from core.database import (get_categories, add_task, update_task,
                           get_task_attachments, set_task_attachments)
from core.file_handler import save_attachment
from ui.datetime_picker import DateTimePicker
from ui.recurrence_widget import RecurrenceWidget


class TaskForm(ctk.CTkToplevel):
    """Formulaire d ajout / edition de tache avec sous-taches."""

    def __init__(self, master, task, category_id, on_save):
        super().__init__(master)
        self.task         = task
        self.on_save      = on_save
        self._attachment  = task.attachment_path if task else None
        self._reminder_dt = task.reminder_at if task else None
        self._task_id_tmp = task.id if task else None

        self.title("Editer la tache" if task else "Nouvelle tache")
        self.geometry("560x820")
        self.resizable(False, True)
        self.grab_set()

        cats            = get_categories()
        self._cat_map   = {c.name: c.id for c in cats}
        self._cat_names = [c.name for c in cats]
        default_cat     = next(
            (c.name for c in cats if c.id == category_id),
            self._cat_names[0] if self._cat_names else ""
        )
        pad = {"padx": 16, "pady": 4}

        scroll = ctk.CTkScrollableFrame(self)
        scroll.pack(fill="both", expand=True)

        # Titre
        ctk.CTkLabel(scroll, text="Titre *", anchor="w").pack(fill="x", **pad)
        self._title_e = ctk.CTkEntry(scroll, height=36)
        self._title_e.pack(fill="x", **pad)
        if task: self._title_e.insert(0, task.title or "")

        # Description + Coller image
        desc_header = ctk.CTkFrame(scroll, fg_color="transparent")
        desc_header.pack(fill="x", **pad)
        ctk.CTkLabel(desc_header, text="Description", anchor="w").pack(side="left")
        self._paste_btn = ctk.CTkButton(desc_header,
            text="Coller image", width=110, height=24,
            fg_color="#4a2a6a", hover_color="#7B2FBE",
            font=ctk.CTkFont(size=11), command=self._paste_image)
        self._paste_btn.pack(side="right")
        self._clip_label = ctk.CTkLabel(desc_header,
            text="", font=ctk.CTkFont(size=10), text_color="#9370DB")
        self._clip_label.pack(side="right", padx=6)

        self._desc_e = ctk.CTkTextbox(scroll, height=80)
        self._desc_e.pack(fill="x", **pad)
        if task and task.description:
            self._desc_e.insert("0.0", task.description)
        self._desc_e.bind("<Control-v>", self._on_ctrl_v)
        self._desc_e.bind("<Control-V>", self._on_ctrl_v)

        # Zone miniatures — masquee par defaut, visible seulement si image collee
        self._thumbs_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        # NE PAS pack ici — sera affiche seulement quand une image est collee
        self._thumb_refs = []
        self._thumbs_visible = False

        # Categorie
        ctk.CTkLabel(scroll, text="Categorie", anchor="w").pack(fill="x", **pad)
        self._cat_var = ctk.StringVar(value=default_cat)
        ctk.CTkOptionMenu(scroll, values=self._cat_names,
            variable=self._cat_var).pack(fill="x", **pad)

        # Priorite
        ctk.CTkLabel(scroll, text="Priorite", anchor="w").pack(fill="x", **pad)
        self._prio_var = ctk.StringVar(value=task.priority if task else "normal")
        ctk.CTkSegmentedButton(scroll,
            values=["low","normal","high","urgent"],
            variable=self._prio_var).pack(fill="x", **pad)

        # Statut (edition seulement)
        if task:
            ctk.CTkLabel(scroll, text="Statut", anchor="w").pack(fill="x", **pad)
            self._status_var = ctk.StringVar(value=task.status)
            ctk.CTkSegmentedButton(scroll,
                values=["todo","in_progress","done"],
                variable=self._status_var).pack(fill="x", **pad)

        # Rappel
        ctk.CTkLabel(scroll, text="Rappel", anchor="w").pack(fill="x", **pad)
        remind_row = ctk.CTkFrame(scroll, fg_color="transparent")
        remind_row.pack(fill="x", **pad)
        self._remind_label = ctk.CTkLabel(remind_row,
            text=self._fmt(self._reminder_dt),
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#1E90FF" if self._reminder_dt else "gray", anchor="w")
        self._remind_label.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(remind_row, text="Choisir", width=90, height=30,
            command=self._open_picker).pack(side="right", padx=(8,0))
        ctk.CTkButton(remind_row, text="X", width=30, height=30,
            fg_color="gray30",
            command=self._clear_reminder).pack(side="right", padx=(4,0))

        # Recurrence
        ctk.CTkFrame(scroll, height=1,
            fg_color=("gray70","gray30")).pack(fill="x", padx=8, pady=6)
        self._rec_widget = RecurrenceWidget(scroll,
            recurrence=task.recurrence if task else None,
            recurrence_days=task.recurrence_days if task else None)
        self._rec_widget.pack(fill="x", **pad)
        ctk.CTkFrame(scroll, height=1,
            fg_color=("gray70","gray30")).pack(fill="x", padx=8, pady=6)

        # Sous-taches (edition seulement)
        if task:
            ctk.CTkLabel(scroll,
                text="Sous-taches",
                anchor="w",
                font=ctk.CTkFont(size=13, weight="bold")
            ).pack(fill="x", **pad)

            sub_frame = ctk.CTkFrame(scroll,
                fg_color=("gray90","gray17"), corner_radius=8)
            sub_frame.pack(fill="x", padx=16, pady=(0, 6))

            from ui.subtask_widget import SubTaskWidget
            SubTaskWidget(
                sub_frame,
                task_id=task.id,
                task_title=task.title,
                task_desc=task.description or "",
                on_change=None
            ).pack(fill="x", padx=8, pady=6)

            ctk.CTkFrame(scroll, height=1,
                fg_color=("gray70","gray30")).pack(fill="x", padx=8, pady=6)

        # Piece jointe
        att_row = ctk.CTkFrame(scroll, fg_color="transparent")
        att_row.pack(fill="x", **pad)
        self._att_label = ctk.CTkLabel(att_row,
            text=f"PJ : {self._attachment}" if self._attachment else "Aucun fichier",
            text_color="#88BBFF" if self._attachment else "gray", anchor="w")
        self._att_label.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(att_row, text="Parcourir", width=100,
            command=self._browse).pack(side="right")

        # Boutons
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(8, 16))
        ctk.CTkButton(btn_row, text="Enregistrer",
            command=self._save).pack(side="left", expand=True, padx=4)
        ctk.CTkButton(btn_row, text="Annuler",
            fg_color="gray30",
            command=self.destroy).pack(side="right", expand=True, padx=4)

        self.after(200, self._check_clipboard)

    def _check_clipboard(self):
        try:
            from core.clipboard_image import has_image_in_clipboard
            if has_image_in_clipboard():
                self._clip_label.configure(text="Image detectee !", text_color="#9370DB")
                self._paste_btn.configure(fg_color="#7B2FBE")
            else:
                self._clip_label.configure(text="")
                self._paste_btn.configure(fg_color="#4a2a6a")
        except Exception:
            pass

    def _on_ctrl_v(self, event):
        try:
            from core.clipboard_image import has_image_in_clipboard
            if has_image_in_clipboard():
                self._paste_image()
                return "break"
            return None
        except Exception:
            return None

    def _paste_image(self):
        try:
            from core.clipboard_image import save_clipboard_image
            tmp_id = self._task_id_tmp or 0
            result = save_clipboard_image(tmp_id)
            if not result:
                self._clip_label.configure(
                    text="Aucune image dans le presse-papier", text_color="gray")
                return
            img_path, thumb_path = result
            self._attachment = img_path
            self._show_thumbnail(thumb_path, img_path)
            self._clip_label.configure(text="Image collee !", text_color="#32CD32")
            self._paste_btn.configure(fg_color="#4a2a6a")
            import os
            self._att_label.configure(
                text=f"Image : {os.path.basename(img_path)}", text_color="#88BBFF")
        except Exception as e:
            self._clip_label.configure(text=f"Erreur : {e}", text_color="#FF4444")

    def _show_thumbnail(self, thumb_path, img_path):
        try:
            from core.clipboard_image import get_thumbnail
            thumb = get_thumbnail(thumb_path)
            if not thumb: return
            self._thumb_refs.append(thumb)
            # Afficher le conteneur seulement si premiere image
            if not self._thumbs_visible:
                self._thumbs_frame.pack(fill="x", padx=16, pady=(0, 4))
                self._thumbs_visible = True
            thumb_frame = ctk.CTkFrame(self._thumbs_frame,
                fg_color=("gray85","gray20"), corner_radius=6)
            thumb_frame.pack(side="left", padx=4, pady=4)
            import tkinter as tk
            lbl = tk.Label(thumb_frame, image=thumb, bg="#2b2b2b", cursor="hand2")
            lbl.pack(padx=4, pady=4)
            lbl.bind("<Button-1>", lambda e, p=img_path: __import__("os").startfile(p))
            ctk.CTkButton(thumb_frame, text="X", width=20, height=20,
                fg_color="transparent", hover_color="#550000", text_color="#888",
                font=ctk.CTkFont(size=10),
                command=lambda f=thumb_frame: (
                    f.destroy(),
                    self._att_label.configure(text="Aucun fichier", text_color="gray")
                )).pack()
        except Exception as e:
            print(f"[Clipboard] Miniature : {e}")

    def _fmt(self, dt):
        if not dt: return "Aucun rappel"
        DAYS   = ["Lundi","Mardi","Mercredi","Jeudi","Vendredi","Samedi","Dimanche"]
        MONTHS = ["jan","fev","mar","avr","mai","jun","jul","aou","sep","oct","nov","dec"]
        return (f"{DAYS[dt.weekday()]} {dt.day} {MONTHS[dt.month-1]}"
                f" {dt.year}  {dt.hour:02d}:{dt.minute:02d}")

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
        desc     = self._desc_e.get("0.0", "end").strip()
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
                existing = get_task_attachments(self.task)
                if new_path not in existing:
                    existing.append(new_path)
                set_task_attachments(self.task.id, existing)
        else:
            new_task = add_task(
                title=title, description=desc, category_id=cat_id,
                priority=prio, reminder_at=self._reminder_dt,
                recurrence=rec, recurrence_days=rec_days)
            if self._attachment:
                new_path = save_attachment(self._attachment, new_task.id)
                set_task_attachments(new_task.id, [new_path])

        self.on_save()
        self.destroy()
