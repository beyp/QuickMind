"""
Widget de sous-taches — checklist avec barre de progression.
Integre dans les cartes de taches de TaskPanel.
"""
import customtkinter as ctk
import threading
from core.database import (get_subtasks, add_subtask, toggle_subtask,
                           delete_subtask, get_subtask_progress,
                           check_auto_complete, MAX_SUBTASKS)


class SubTaskWidget(ctk.CTkFrame):
    """
    Widget checklist pour les sous-taches d une tache.
    Affiche : checkboxes + barre de progression + boutons ajouter/IA.
    """

    def __init__(self, master, task_id: int, task_title: str,
                 task_desc: str = "", on_change=None):
        super().__init__(master, fg_color="transparent")
        self.task_id    = task_id
        self.task_title = task_title
        self.task_desc  = task_desc
        self.on_change  = on_change
        self._build()

    def _build(self):
        self._refresh()

    def _refresh(self):
        for w in self.winfo_children():
            w.destroy()

        subs       = get_subtasks(self.task_id)
        done, total = get_subtask_progress(self.task_id)

        if not subs and not True:  # toujours afficher
            return

        # ── Barre de progression ──────────────────────────────────────────
        if total > 0:
            prog_row = ctk.CTkFrame(self, fg_color="transparent")
            prog_row.pack(fill="x", pady=(2, 4))

            pct = done / total
            pct_color = "#32CD32" if pct == 1.0 else "#1E90FF"

            ctk.CTkLabel(prog_row,
                text=f"{done}/{total}",
                font=ctk.CTkFont(size=10, weight="bold"),
                text_color=pct_color,
                width=32
            ).pack(side="left", padx=(0, 6))

            bar = ctk.CTkProgressBar(prog_row, height=8, corner_radius=4)
            bar.pack(side="left", fill="x", expand=True)
            bar.set(pct)
            bar.configure(progress_color=pct_color)

            pct_label = ctk.CTkLabel(prog_row,
                text=f"{int(pct*100)}%",
                font=ctk.CTkFont(size=10),
                text_color=pct_color,
                width=32
            )
            pct_label.pack(side="left", padx=(6, 0))

        # ── Liste des sous-taches ─────────────────────────────────────────
        for sub in subs:
            row = ctk.CTkFrame(self, fg_color="transparent")
            row.pack(fill="x", pady=1)

            # Checkbox
            var = ctk.BooleanVar(value=sub.done)
            cb  = ctk.CTkCheckBox(
                row,
                text="",
                variable=var,
                width=20,
                checkbox_width=16,
                checkbox_height=16,
                command=lambda sid=sub.id: self._toggle(sid)
            )
            cb.pack(side="left", padx=(4, 2))

            # Titre (barre si done)
            text_color = "#555555" if sub.done else ("gray80", "gray90")
            font       = ctk.CTkFont(size=11,
                                     overstrike=sub.done)  # barre si done
            title_lbl  = ctk.CTkLabel(
                row,
                text=sub.title,
                font=font,
                text_color=text_color if isinstance(text_color, str)
                           else text_color[0],
                anchor="w"
            )
            title_lbl.pack(side="left", fill="x", expand=True, padx=(0, 4))

            # Bouton supprimer
            ctk.CTkButton(row,
                text="✕", width=20, height=20,
                fg_color="transparent",
                hover_color="#550000",
                text_color="#666",
                font=ctk.CTkFont(size=10),
                command=lambda sid=sub.id: self._delete(sid)
            ).pack(side="right", padx=(0, 4))

        # ── Barre d ajout ─────────────────────────────────────────────────
        add_row = ctk.CTkFrame(self, fg_color="transparent")
        add_row.pack(fill="x", pady=(4, 0))
        add_row.grid_columnconfigure(0, weight=1)

        remaining = MAX_SUBTASKS - total

        if remaining > 0:
            self._entry = ctk.CTkEntry(
                add_row,
                height=26,
                placeholder_text=f"＋ Ajouter une sous-tâche... ({remaining} restante(s))",
                font=ctk.CTkFont(size=11)
            )
            self._entry.grid(row=0, column=0, sticky="ew", padx=(0, 4))
            self._entry.bind("<Return>", lambda e: self._add_from_entry())

            ctk.CTkButton(add_row,
                text="＋", width=26, height=26,
                command=self._add_from_entry
            ).grid(row=0, column=1, padx=(0, 4))

            # Bouton IA
            self._ai_btn = ctk.CTkButton(add_row,
                text="🤖 IA", width=50, height=26,
                fg_color="#1a2a4a", hover_color="#1E90FF",
                font=ctk.CTkFont(size=10),
                command=self._generate_with_ai
            )
            self._ai_btn.grid(row=0, column=2)
        else:
            ctk.CTkLabel(add_row,
                text=f"Maximum {MAX_SUBTASKS} sous-tâches atteint",
                text_color="gray", font=ctk.CTkFont(size=10)
            ).grid(row=0, column=0, sticky="w")

    def _toggle(self, subtask_id: int):
        toggle_subtask(subtask_id)
        check_auto_complete(self.task_id)
        self._refresh()
        if self.on_change:
            self.on_change()

    def _add_from_entry(self):
        title = self._entry.get().strip()
        if not title:
            return
        result = add_subtask(self.task_id, title)
        if result:
            self._entry.delete(0, "end")
            self._refresh()
            if self.on_change:
                self.on_change()

    def _delete(self, subtask_id: int):
        delete_subtask(subtask_id)
        self._refresh()
        if self.on_change:
            self.on_change()

    def _generate_with_ai(self):
        """Genere les sous-taches via Mistral."""
        self._ai_btn.configure(state="disabled", text="⏳")

        def _run():
            try:
                from agents.subtask_ai import generate_subtasks
                from core.database import get_subtask_progress
                _, current_count = get_subtask_progress(self.task_id)
                remaining = MAX_SUBTASKS - current_count
                suggestions = generate_subtasks(
                    self.task_title, self.task_desc,
                    max_subtasks=remaining
                )
                self.after(0, lambda: self._on_ai_done(suggestions))
            except Exception as e:
                self.after(0, lambda: self._on_ai_error(str(e)))

        threading.Thread(target=_run, daemon=True).start()

    def _on_ai_done(self, suggestions: list[str]):
        self._ai_btn.configure(state="normal", text="🤖 IA")
        if not suggestions:
            return
        # Ouvrir un dialog de confirmation
        self._show_ai_suggestions(suggestions)

    def _on_ai_error(self, error: str):
        self._ai_btn.configure(state="normal", text="🤖 IA")
        print(f"[SubTask AI] Erreur : {error}")

    def _show_ai_suggestions(self, suggestions: list[str]):
        """Dialog de confirmation des sous-taches generees par IA."""
        dialog = ctk.CTkToplevel(self)
        dialog.title("Sous-tâches suggérées par Mistral")
        dialog.geometry("420x480")
        dialog.resizable(False, True)
        dialog.grab_set()

        ctk.CTkLabel(dialog,
            text="🤖  Sous-tâches suggérées par Mistral",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#1E90FF"
        ).pack(padx=16, pady=(12, 6))

        ctk.CTkLabel(dialog,
            text="Cochez celles que vous voulez ajouter :",
            font=ctk.CTkFont(size=11), text_color="gray"
        ).pack(padx=16, pady=(0, 8))

        # Scroll pour les suggestions
        scroll = ctk.CTkScrollableFrame(dialog, height=280)
        scroll.pack(fill="both", expand=True, padx=16, pady=4)

        vars_list = []
        for suggestion in suggestions:
            var = ctk.BooleanVar(value=True)
            vars_list.append((var, suggestion))
            ctk.CTkCheckBox(scroll,
                text=suggestion,
                variable=var,
                font=ctk.CTkFont(size=12)
            ).pack(anchor="w", pady=3)

        # Boutons
        btn_row = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(8, 14))

        def _confirm():
            for var, title in vars_list:
                if var.get():
                    add_subtask(self.task_id, title)
            dialog.destroy()
            self._refresh()
            if self.on_change:
                self.on_change()

        ctk.CTkButton(btn_row,
            text="✅ Ajouter la sélection",
            fg_color="#2a5a2a", hover_color="#1a4a1a",
            command=_confirm
        ).pack(side="left", expand=True, padx=(0, 6))

        ctk.CTkButton(btn_row,
            text="Annuler",
            fg_color="gray30",
            command=dialog.destroy
        ).pack(side="right", expand=True, padx=(6, 0))
