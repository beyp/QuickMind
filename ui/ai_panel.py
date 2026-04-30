"""
Panneau de chat IA — affichage propre avec retours a la ligne corrects.
"""
import customtkinter as ctk
import threading
from agents.local_ai import ask_ai


WELCOME = (
    "Bonjour ! Je suis votre assistant Mistral local.\n"
    "\n"
    "Exemples de commandes :\n"
    "  - Cree une tache urgente : appel client vendredi 14h\n"
    "  - Quelles sont mes taches en retard ?\n"
    "  - Resume mes taches de la semaine\n"
    "  - Marque la tache #3 comme terminee\n"
    "  - Ajoute un rappel demain 9h sur la tache #1"
)


class AIPanel(ctk.CTkFrame):
    def __init__(self, master, on_action_done=None):
        super().__init__(master, corner_radius=12, border_width=1,
                         border_color="#1E90FF")
        self.on_action_done = on_action_done
        self._build()

    def _build(self):
        # ── Header ────────────────────────────────────────────────────────
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=12, pady=(8, 4))

        ctk.CTkLabel(
            header,
            text="  Assistant IA — Mistral (local)",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#1E90FF"
        ).pack(side="left")

        self._status_label = ctk.CTkLabel(
            header,
            text="● offline / local",
            font=ctk.CTkFont(size=10),
            text_color="#32CD32"
        )
        self._status_label.pack(side="right")

        # ── Zone de conversation (Textbox avec tag de couleur) ─────────────
        self._chat = ctk.CTkTextbox(
            self, height=200,
            font=ctk.CTkFont(family="Consolas", size=12),
            state="disabled", wrap="word"
        )
        self._chat.pack(fill="both", expand=True, padx=10, pady=4)

        # ── Zone de saisie ────────────────────────────────────────────────
        input_row = ctk.CTkFrame(self, fg_color="transparent")
        input_row.pack(fill="x", padx=10, pady=(0, 10))
        input_row.grid_columnconfigure(0, weight=1)

        self._entry = ctk.CTkEntry(
            input_row, height=36,
            placeholder_text="Ex: Cree une tache urgente pour vendredi...",
            font=ctk.CTkFont(size=12)
        )
        self._entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self._entry.bind("<Return>", lambda e: self._send())

        self._send_btn = ctk.CTkButton(
            input_row, text="Envoyer", width=90, height=36,
            command=self._send
        )
        self._send_btn.grid(row=0, column=1)

        ctk.CTkButton(
            input_row, text="Effacer", width=80, height=36,
            fg_color="gray30", hover_color="gray20",
            command=self._clear
        ).grid(row=0, column=2, padx=(6, 0))

        # Message de bienvenue
        self._append("IA", WELCOME)

    # ── Methodes privees ──────────────────────────────────────────────────

    def _append(self, role: str, text: str):
        """
        Insere un bloc de texte dans le chat avec une mise en forme claire.
        role : "user" | "IA"
        """
        self._chat.configure(state="normal")

        sep = "─" * 52 + "\n"

        if role == "user":
            header_line = "Vous\n"
        else:
            header_line = "IA\n"

        # Separateur + qui parle
        self._chat.insert("end", sep)
        self._chat.insert("end", header_line)

        # Corps du message — on force les sauts de ligne
        clean_text = text.replace("\\n", "\n")
        self._chat.insert("end", clean_text + "\n\n")

        self._chat.configure(state="disabled")
        self._chat.see("end")

    def _send(self):
        prompt = self._entry.get().strip()
        if not prompt:
            return

        self._append("user", prompt)
        self._entry.delete(0, "end")
        self._send_btn.configure(state="disabled", text="⏳ Mistral...")
        self._status_label.configure(text="● traitement...", text_color="#FFD700")

        def _run():
            result = ask_ai(prompt)
            self.after(0, lambda: self._on_response(result))

        threading.Thread(target=_run, daemon=True).start()

    def _on_response(self, result: str):
        self._append("IA", result)
        self._send_btn.configure(state="normal", text="Envoyer")
        self._status_label.configure(text="● offline / local", text_color="#32CD32")
        if self.on_action_done:
            self.on_action_done()

    def _clear(self):
        self._chat.configure(state="normal")
        self._chat.delete("0.0", "end")
        self._chat.configure(state="disabled")
        self._append("IA", WELCOME)
