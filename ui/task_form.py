import customtkinter as ctk
import tkinter.filedialog as fd
from datetime import datetime
from core.database import (get_categories, add_task, update_task,
                           get_task_attachments, set_task_attachments)
from core.file_handler import save_attachment
from ui.datetime_picker import DateTimePicker
from ui.recurrence_widget import RecurrenceWidget


# ── Widget Accordeon ──────────────────────────────────────────────────────────

class AccordionSection(ctk.CTkFrame):
    """
    Section accordeon — titre cliquable qui masque/affiche le contenu.
    """
    def __init__(self, master, title: str, expanded: bool = True,
                 accent_color: str = "#1E90FF"):
        super().__init__(master, fg_color="transparent")
        self._expanded     = expanded
        self._accent_color = accent_color
        self._content      = None
        self._build(title)

    def _build(self, title: str):
        # Header cliquable
        self._header = ctk.CTkFrame(self, fg_color=("gray85","gray20"),
                                    corner_radius=6)
        self._header.pack(fill="x", pady=(4, 0))

        self._arrow = ctk.CTkLabel(
            self._header,
            text="▼" if self._expanded else "▶",
            font=ctk.CTkFont(size=11),
            text_color=self._accent_color,
            width=20
        )
        self._arrow.pack(side="left", padx=(8, 4), pady=6)

        self._title_lbl = ctk.CTkLabel(
            self._header,
            text=title,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=self._accent_color,
            anchor="w"
        )
        self._title_lbl.pack(side="left", fill="x", expand=True, pady=6)

        # Bind click sur tout le header
        for w in [self._header, self._arrow, self._title_lbl]:
            w.bind("<Button-1>", lambda e: self.toggle())
        self._header.configure(cursor="hand2")

        # Zone de contenu
        self._content_frame = ctk.CTkFrame(self, fg_color="transparent")
        if self._expanded:
            self._content_frame.pack(fill="x", padx=4, pady=(2, 6))

    def get_content(self) -> ctk.CTkFrame:
        """Retourne le frame de contenu pour y ajouter des widgets."""
        return self._content_frame

    def toggle(self):
        self._expanded = not self._expanded
        self._arrow.configure(text="▼" if self._expanded else "▶")
        if self._expanded:
            self._content_frame.pack(fill="x", padx=4, pady=(2, 6))
        else:
            self._content_frame.pack_forget()
        # Forcer le recalcul du scroll parent
        self.update_idletasks()
        p = self.master
        while p and not isinstance(p, ctk.CTkScrollableFrame):
            p = p.master
        if p:
            p.update_idletasks()


# ── Formulaire principal ──────────────────────────────────────────────────────

class TaskForm(ctk.CTkToplevel):
    """
    Formulaire d ajout / edition de tache.
    Layout accordeon pour voir tous les champs et le bouton Enregistrer.
    """

    def __init__(self, master, task, category_id, on_save):
        super().__init__(master)
        self.task         = task
        self.on_save      = on_save
        self._attachment  = task.attachment_path if task else None
        self._reminder_dt = task.reminder_at if task else None
        self._task_id_tmp = task.id if task else None
        self._thumb_refs  = []
        self._thumbs_visible = False

        self.title("Editer la tache" if task else "Nouvelle tache")
        self.geometry("580x700")
        self.minsize(520, 500)
        self.resizable(True, True)
        self.grab_set()

        cats            = get_categories()
        self._cat_map   = {c.name: c.id for c in cats}
        self._cat_names = [c.name for c in cats]
        default_cat     = next(
            (c.name for c in cats if c.id == category_id),
            self._cat_names[0] if self._cat_names else ""
        )

        # Layout : scroll + boutons fixes en bas
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)
        self.grid_columnconfigure(0, weight=1)

        # Zone scrollable
        self._scroll = ctk.CTkScrollableFrame(self)
        self._scroll.grid(row=0, column=0, sticky="nsew", padx=8, pady=(8,0))

        # Boutons FIXES en bas (toujours visibles)
        self._btn_row = ctk.CTkFrame(self, fg_color=("gray90","gray15"),
                                     corner_radius=0)
        self._btn_row.grid(row=1, column=0, sticky="ew", padx=0, pady=0)
        self._btn_row.grid_columnconfigure(0, weight=1)
        self._btn_row.grid_columnconfigure(1, weight=1)

        self._save_btn = ctk.CTkButton(
            self._btn_row,
            text="💾  Enregistrer",
            height=42,
            fg_color="#1E90FF", hover_color="#0060CC",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._save
        )
        self._save_btn.grid(row=0, column=0, padx=(12,6), pady=10, sticky="ew")

        ctk.CTkButton(
            self._btn_row,
            text="Annuler",
            height=42,
            fg_color="gray30", hover_color="gray20",
            font=ctk.CTkFont(size=13),
            command=self.destroy
        ).grid(row=0, column=1, padx=(6,12), pady=10, sticky="ew")

        # Construire les sections
        self._build_sections(task, default_cat)

        # Verifier clipboard
        self.after(200, self._check_clipboard)

    def _build_sections(self, task, default_cat):
        s = self._scroll
        pad = {"padx": 4, "pady": 2}

        # ── Section 1 : Titre + Description (toujours ouverte) ───────────────
        sec1 = AccordionSection(s, "📝  Titre & Description",
                                expanded=True, accent_color="#1E90FF")
        sec1.pack(fill="x", **pad)
        c1 = sec1.get_content()

        ctk.CTkLabel(c1, text="Titre *", anchor="w",
            font=ctk.CTkFont(size=11)).pack(fill="x", padx=4, pady=(4,2))
        self._title_e = ctk.CTkEntry(c1, height=36)
        self._title_e.pack(fill="x", padx=4, pady=(0,6))
        if task: self._title_e.insert(0, task.title or "")

        # Description + bouton coller image
        desc_hdr = ctk.CTkFrame(c1, fg_color="transparent")
        desc_hdr.pack(fill="x", padx=4)
        ctk.CTkLabel(desc_hdr, text="Description", anchor="w",
            font=ctk.CTkFont(size=11)).pack(side="left")
        self._clip_label = ctk.CTkLabel(desc_hdr, text="",
            font=ctk.CTkFont(size=10), text_color="#9370DB")
        self._clip_label.pack(side="right", padx=6)
        self._paste_btn = ctk.CTkButton(desc_hdr, text="📋 Coller image",
            width=110, height=22,
            fg_color="#4a2a6a", hover_color="#7B2FBE",
            font=ctk.CTkFont(size=10), command=self._paste_image)
        self._paste_btn.pack(side="right")

        self._desc_e = ctk.CTkTextbox(c1, height=80)
        self._desc_e.pack(fill="x", padx=4, pady=(2,4))
        if task and task.description:
            self._desc_e.insert("0.0", task.description)
        self._desc_e.bind("<Control-v>", self._on_ctrl_v)
        self._desc_e.bind("<Control-V>", self._on_ctrl_v)

        # Miniatures
        self._thumbs_frame = ctk.CTkFrame(c1, fg_color="transparent")
        self._thumb_refs   = []
        self._thumbs_visible = False

        # ── Section 2 : Catégorie + Priorité + Statut (ouverte) ──────────────
        sec2 = AccordionSection(s, "🏷️  Classification",
                                expanded=True, accent_color="#FF8C00")
        sec2.pack(fill="x", **pad)
        c2 = sec2.get_content()

        # Ligne catégorie + priorité côte à côte
        row_cp = ctk.CTkFrame(c2, fg_color="transparent")
        row_cp.pack(fill="x", padx=4, pady=4)
        row_cp.grid_columnconfigure(0, weight=1)
        row_cp.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(row_cp, text="Catégorie", anchor="w",
            font=ctk.CTkFont(size=11)).grid(row=0, column=0, sticky="w", padx=(0,4))
        ctk.CTkLabel(row_cp, text="Priorité", anchor="w",
            font=ctk.CTkFont(size=11)).grid(row=0, column=1, sticky="w", padx=(4,0))

        self._cat_var = ctk.StringVar(value=default_cat)
        ctk.CTkOptionMenu(row_cp, values=self._cat_names,
            variable=self._cat_var, height=32
        ).grid(row=1, column=0, sticky="ew", padx=(0,4), pady=(2,0))

        self._prio_var = ctk.StringVar(value=task.priority if task else "normal")
        ctk.CTkSegmentedButton(row_cp,
            values=["low","normal","high","urgent"],
            variable=self._prio_var
        ).grid(row=1, column=1, sticky="ew", padx=(4,0), pady=(2,0))

        # Statut (édition seulement)
        if task:
            ctk.CTkLabel(c2, text="Statut", anchor="w",
                font=ctk.CTkFont(size=11)).pack(fill="x", padx=4, pady=(8,2))
            self._status_var = ctk.StringVar(value=task.status)
            ctk.CTkSegmentedButton(c2,
                values=["todo","in_progress","done"],
                variable=self._status_var
            ).pack(fill="x", padx=4, pady=(0,4))

        # ── Section 3 : Rappel + Récurrence (fermée par défaut) ──────────────
        has_reminder = task and task.reminder_at
        has_recur    = task and task.recurrence and task.recurrence != "none"
        sec3 = AccordionSection(s, "⏰  Rappel & Récurrence",
                                expanded=bool(has_reminder or has_recur),
                                accent_color="#FFD700")
        sec3.pack(fill="x", **pad)
        c3 = sec3.get_content()

        ctk.CTkLabel(c3, text="Rappel", anchor="w",
            font=ctk.CTkFont(size=11)).pack(fill="x", padx=4, pady=(4,2))
        remind_row = ctk.CTkFrame(c3, fg_color="transparent")
        remind_row.pack(fill="x", padx=4, pady=(0,6))
        self._remind_label = ctk.CTkLabel(remind_row,
            text=self._fmt(self._reminder_dt),
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#1E90FF" if self._reminder_dt else "gray",
            anchor="w")
        self._remind_label.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(remind_row, text="📅 Choisir", width=90, height=30,
            command=self._open_picker).pack(side="right", padx=(8,0))
        ctk.CTkButton(remind_row, text="✕", width=30, height=30,
            fg_color="gray30",
            command=self._clear_reminder).pack(side="right", padx=(4,0))

        self._rec_widget = RecurrenceWidget(c3,
            recurrence=task.recurrence if task else None,
            recurrence_days=task.recurrence_days if task else None)
        self._rec_widget.pack(fill="x", padx=4, pady=(0,4))

        # ── Section 4 : Sous-tâches (fermée si nouvelle tâche) ───────────────
        if task:
            sec4 = AccordionSection(s, "✅  Sous-tâches",
                                    expanded=False, accent_color="#32CD32")
            sec4.pack(fill="x", **pad)
            c4 = sec4.get_content()
            from ui.subtask_widget import SubTaskWidget
            SubTaskWidget(c4, task_id=task.id,
                          task_title=task.title,
                          task_desc=task.description or "",
                          on_change=None
            ).pack(fill="x", padx=4, pady=6)

        # ── Section 5 : Pièce jointe (fermée par défaut) ─────────────────────
        sec5 = AccordionSection(s, "📎  Pièce jointe",
                                expanded=bool(self._attachment),
                                accent_color="#9370DB")
        sec5.pack(fill="x", **pad)
        c5 = sec5.get_content()

        att_row = ctk.CTkFrame(c5, fg_color="transparent")
        att_row.pack(fill="x", padx=4, pady=4)
        self._att_label = ctk.CTkLabel(att_row,
            text=f"📎 {self._attachment}" if self._attachment else "Aucun fichier",
            text_color="#88BBFF" if self._attachment else "gray",
            anchor="w", font=ctk.CTkFont(size=11))
        self._att_label.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(att_row, text="Parcourir", width=100,
            command=self._browse).pack(side="right")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _fmt(self, dt):
        if not dt: return "Aucun rappel"
        DAYS   = ["Lundi","Mardi","Mercredi","Jeudi","Vendredi","Samedi","Dimanche"]
        MONTHS = ["jan","fev","mar","avr","mai","jun",
                  "jul","aou","sep","oct","nov","dec"]
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
                text=f"📎 {os.path.basename(path)}", text_color="#88BBFF")

    # ── Clipboard ─────────────────────────────────────────────────────────────

    def _check_clipboard(self):
        try:
            from core.clipboard_image import has_image_in_clipboard
            if has_image_in_clipboard():
                self._clip_label.configure(
                    text="🖼️ Image detectee !", text_color="#9370DB")
                self._paste_btn.configure(fg_color="#7B2FBE")
        except Exception:
            pass

    def _on_ctrl_v(self, event):
        try:
            from core.clipboard_image import has_image_in_clipboard
            if has_image_in_clipboard():
                self._paste_image()
                return "break"
        except Exception:
            pass
        return None

    def _paste_image(self):
        try:
            from core.clipboard_image import save_clipboard_image
            tmp_id = self._task_id_tmp or 0
            result = save_clipboard_image(tmp_id)
            if not result:
                self._clip_label.configure(
                    text="Aucune image", text_color="gray")
                return
            img_path, thumb_path = result
            self._attachment = img_path
            self._show_thumbnail(thumb_path, img_path)
            self._clip_label.configure(
                text="✅ Image collee !", text_color="#32CD32")
            self._paste_btn.configure(fg_color="#4a2a6a")
            import os
            self._att_label.configure(
                text=f"🖼️ {os.path.basename(img_path)}",
                text_color="#88BBFF")
        except Exception as e:
            self._clip_label.configure(
                text=f"Erreur : {e}", text_color="#FF4444")

    def _show_thumbnail(self, thumb_path, img_path):
        try:
            from core.clipboard_image import get_thumbnail
            thumb = get_thumbnail(thumb_path)
            if not thumb: return
            self._thumb_refs.append(thumb)
            if not self._thumbs_visible:
                self._thumbs_frame.pack(fill="x", padx=4, pady=4)
                self._thumbs_visible = True
            tf = ctk.CTkFrame(self._thumbs_frame,
                fg_color=("gray85","gray20"), corner_radius=6)
            tf.pack(side="left", padx=4, pady=4)
            import tkinter as tk
            lbl = tk.Label(tf, image=thumb, bg="#2b2b2b", cursor="hand2")
            lbl.pack(padx=4, pady=4)
            lbl.bind("<Button-1>",
                lambda e, p=img_path: __import__("os").startfile(p))
            ctk.CTkButton(tf, text="✕", width=20, height=20,
                fg_color="transparent", hover_color="#550000",
                text_color="#888", font=ctk.CTkFont(size=10),
                command=lambda f=tf: (
                    f.destroy(),
                    self._att_label.configure(
                        text="Aucun fichier", text_color="gray"))
            ).pack()
        except Exception as e:
            print(f"[Clipboard] Miniature : {e}")

    # ── Sauvegarde ────────────────────────────────────────────────────────────

    def _save(self):
        title = self._title_e.get().strip()
        if not title:
            self._title_e.configure(border_color="#FF4444")
            self._title_e.focus()
            return
        self._title_e.configure(border_color=("gray70","gray30"))

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
                title=title, description=desc,
                category_id=cat_id, priority=prio,
                reminder_at=self._reminder_dt,
                recurrence=rec, recurrence_days=rec_days)
            if self._attachment:
                new_path = save_attachment(self._attachment, new_task.id)
                set_task_attachments(new_task.id, [new_path])

        self.on_save()
        self.destroy()
