import customtkinter as ctk


class PromptBar(ctk.CTkFrame):
    """Barre du bas : IA, Outlook, recherche, badge mise a jour."""

    def __init__(self, master, on_submit, on_toggle_ai=None, on_outlook=None):
        super().__init__(master, height=48, corner_radius=10)
        self.on_submit    = on_submit
        self.on_toggle_ai = on_toggle_ai
        self.on_outlook   = on_outlook
        self._update_btn  = None
        self._build()

    def _build(self):
        self.grid_columnconfigure(2, weight=1)

        # Bouton IA
        self._ai_btn = ctk.CTkButton(
            self, text="🤖 IA", width=70, height=36,
            fg_color="#1a3a5c", hover_color="#1E90FF",
            command=self._toggle_ai
        )
        self._ai_btn.grid(row=0, column=0, padx=(10, 4), pady=6)

        # Bouton Outlook
        self._ol_btn = ctk.CTkButton(
            self, text="📬 Outlook", width=100, height=36,
            fg_color="#0078D4", hover_color="#005a9e",
            command=self._open_outlook
        )
        self._ol_btn.grid(row=0, column=1, padx=(0, 6), pady=6)

        # Champ de recherche
        self._entry = ctk.CTkEntry(
            self, height=36,
            placeholder_text="Recherche rapide : urgent, a faire, rapport...",
            font=ctk.CTkFont(size=12)
        )
        self._entry.grid(row=0, column=2, sticky="ew", padx=(0, 8), pady=6)
        self._entry.bind("<Return>", lambda e: self._submit())

        ctk.CTkButton(
            self, text="Chercher", width=90, height=36,
            command=self._submit
        ).grid(row=0, column=3, padx=(0, 6), pady=6)

        # Bouton mise a jour — cree mais pas visible par defaut
        self._update_btn = ctk.CTkButton(
            self,
            text="",
            width=0, height=36,
            fg_color="#FF8C00", hover_color="#CC6600",
            font=ctk.CTkFont(size=11, weight="bold"),
        )
        # Ne pas le grid ici — il sera affiche par show_update_badge()

    def show_update_badge(self, version: str):
        """Affiche le badge de mise a jour dans la barre."""
        self._update_btn.configure(
            text=f"⬆️ v{version}",
            width=90,
            command=lambda: self._on_update_click(version)
        )
        self._update_btn.grid(row=0, column=4, padx=(0, 10), pady=6)

    def _on_update_click(self, version: str):
        from core.updater import check_for_update
        from ui.update_dialog import UpdateDialog
        release = check_for_update()
        if release:
            UpdateDialog(self.master, release_info=release)

    def _submit(self):
        text = self._entry.get().strip()
        if text:
            self.on_submit(text)
            self._entry.delete(0, "end")

    def _toggle_ai(self):
        if self.on_toggle_ai:
            self.on_toggle_ai()
            current = self._ai_btn.cget("fg_color")
            if current == "#1a3a5c":
                self._ai_btn.configure(fg_color="#1E90FF")
            else:
                self._ai_btn.configure(fg_color="#1a3a5c")

    def _open_outlook(self):
        if self.on_outlook:
            self.on_outlook()
