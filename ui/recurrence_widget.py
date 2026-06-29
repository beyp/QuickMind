import customtkinter as ctk
import json

RECURRENCE_OPTIONS = {
    "none":    "Aucune",
    "daily":   "Quotidienne",
    "weekly":    "Hebdomadaire",
    "biweekly":  "Bi-hebdomadaire (2 sem.)",
    "monthly": "Mensuelle",
    "yearly":  "Annuelle",
    "custom":  "Jours specifiques",
}
RECURRENCE_ICONS = {
    "none":    "",
    "daily":   "🔁 Quotidien",
    "weekly":    "🔁 Hebdo",
    "biweekly":  "🔁 Bi-hebdo",
    "monthly": "🔁 Mensuel",
    "yearly":  "🔁 Annuel",
    "custom":  "🔁 Perso",
}
DAYS_OPTIONS = [
    ("Lun", "mon"), ("Mar", "tue"), ("Mer", "wed"),
    ("Jeu", "thu"), ("Ven", "fri"), ("Sam", "sat"), ("Dim", "sun"),
]


class RecurrenceWidget(ctk.CTkFrame):
    """
    Widget de selection de la recurrence.
    Fix : utilise pack/forget au lieu de grid pour le re-layout
    dans un CTkScrollableFrame.
    """

    def __init__(self, master, recurrence=None, recurrence_days=None):
        super().__init__(master, fg_color="transparent")
        self._rec_var  = ctk.StringVar(value=recurrence or "none")
        self._day_vars = {}
        self._build()

        # Init jours si custom
        if recurrence == "custom" and recurrence_days:
            try:
                days = json.loads(recurrence_days)
                for d in days:
                    if d in self._day_vars:
                        self._day_vars[d].set(True)
            except Exception:
                pass

        # Afficher le bon panel selon la valeur initiale
        self._update_panels()

    def _build(self):
        # Label + OptionMenu
        ctk.CTkLabel(self, text="Récurrence :", anchor="w").pack(
            fill="x", pady=(0, 2))

        self._rec_menu = ctk.CTkOptionMenu(
            self,
            values=list(RECURRENCE_OPTIONS.values()),
            command=self._on_change,
            height=32
        )
        self._rec_menu.pack(fill="x", pady=(0, 6))
        self._rec_menu.set(RECURRENCE_OPTIONS.get(self._rec_var.get(), "Aucune"))

        # ── Panel "Jours specifiques" (custom) ───────────────────────────────
        self._custom_frame = ctk.CTkFrame(self,
            fg_color=("gray90", "gray20"), corner_radius=6)

        ctk.CTkLabel(self._custom_frame,
            text="Jours de répétition :",
            anchor="w", font=ctk.CTkFont(size=11, weight="bold")
        ).pack(fill="x", padx=8, pady=(6, 2))

        days_row = ctk.CTkFrame(self._custom_frame, fg_color="transparent")
        days_row.pack(fill="x", padx=8, pady=(0, 6))

        for label, code in DAYS_OPTIONS:
            var = ctk.BooleanVar(value=False)
            self._day_vars[code] = var
            ctk.CTkCheckBox(
                days_row, text=label, variable=var,
                width=52, checkbox_width=16, checkbox_height=16,
                font=ctk.CTkFont(size=11)
            ).pack(side="left", padx=2)

        # ── Panel info (pour les autres types) ────────────────────────────────
        self._info_frame = ctk.CTkFrame(self,
            fg_color=("gray90", "gray20"), corner_radius=6)

        self._info_label = ctk.CTkLabel(
            self._info_frame,
            text="",
            anchor="w",
            font=ctk.CTkFont(size=11),
            text_color="#1E90FF",
            wraplength=380
        )
        self._info_label.pack(fill="x", padx=10, pady=8)

    def _on_change(self, value: str):
        """Callback quand l utilisateur change la recurrence."""
        # Retrouver la cle
        for k, v in RECURRENCE_OPTIONS.items():
            if v == value:
                self._rec_var.set(k)
                break
        self._update_panels()

    def _update_panels(self):
        """Affiche/masque les panels selon le type de recurrence choisi."""
        rec = self._rec_var.get()

        # Masquer les deux panels
        self._custom_frame.pack_forget()
        self._info_frame.pack_forget()

        if rec == "custom":
            # Afficher le selecteur de jours
            self._custom_frame.pack(fill="x", pady=(0, 4))

        elif rec == "daily":
            self._info_label.configure(
                text="🔁  La tâche sera recréée automatiquement chaque jour "
                     "une fois marquée comme terminée.")
            self._info_frame.pack(fill="x", pady=(0, 4))

        elif rec == "weekly":
            self._info_label.configure(
                text="🔁  La tâche sera recréée automatiquement chaque semaine "
                     "(même jour) une fois marquée comme terminée.")
            self._info_frame.pack(fill="x", pady=(0, 4))

        elif rec == "monthly":
            self._info_label.configure(
                text="🔁  La tâche sera recréée automatiquement chaque mois "
                     "(même date) une fois marquée comme terminée.")
            self._info_frame.pack(fill="x", pady=(0, 4))

        elif rec == "yearly":
            self._info_label.configure(
                text="🔁  La tâche sera recréée automatiquement chaque année "
                     "(même date) une fois marquée comme terminée.")
            self._info_frame.pack(fill="x", pady=(0, 4))

        # Forcer le re-layout du parent
        self.update_idletasks()

    def get_recurrence(self) -> str:
        return self._rec_var.get()

    def get_recurrence_days(self) -> str | None:
        if self._rec_var.get() != "custom":
            return None
        selected = [code for code, var in self._day_vars.items() if var.get()]
        return json.dumps(selected) if selected else None

    @staticmethod
    def format_recurrence(recurrence: str, recurrence_days: str = None) -> str:
        """Retourne un texte lisible pour affichage dans les cartes."""
        if not recurrence or recurrence == "none":
            return ""
        if recurrence == "custom" and recurrence_days:
            try:
                days = json.loads(recurrence_days)
                FR   = {
                    "mon": "Lun", "tue": "Mar", "wed": "Mer",
                    "thu": "Jeu", "fri": "Ven", "sat": "Sam", "sun": "Dim"
                }
                days_str = ", ".join(FR.get(d, d) for d in days)
                return f"🔁 {days_str}"
            except Exception:
                pass
        return RECURRENCE_ICONS.get(recurrence, "🔁")
