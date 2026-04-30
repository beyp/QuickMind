import customtkinter as ctk


class PromptBar(ctk.CTkFrame):
    """Barre du bas : recherche rapide + boutons IA et Outlook."""

    def __init__(self, master, on_submit, on_toggle_ai=None, on_outlook=None):
        super().__init__(master, height=48, corner_radius=10)
        self.on_submit    = on_submit
        self.on_toggle_ai = on_toggle_ai
        self.on_outlook   = on_outlook
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
            self, text="📬 Outlook", width=90, height=36,
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
        ).grid(row=0, column=3, padx=(0, 10), pady=6)

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
