"""
Panneau Outlook integre dans QuickMind.
Recupere automatiquement les pieces jointes et le corps du mail.
IA peut resumer ou afficher le corps complet d un mail.
"""
import customtkinter as ctk
import threading
import os
from agents.outlook_ai import ask_outlook, summarize_mail
from agents.outlook_agent import (
    save_mail_attachments, save_mail_body_as_file, get_mail_info
)
from core.database import add_task, update_task, init_db, get_categories


class MailToTaskDialog(ctk.CTkToplevel):
    """
    Dialog de confirmation avant de creer une tache depuis un mail.
    """
    def __init__(self, master, mail: dict, on_confirm):
        super().__init__(master)
        self.mail       = mail
        self.on_confirm = on_confirm
        self.title("Convertir en tache QuickMind")
        self.geometry("520x540")
        self.minsize(480, 460)
        self.resizable(True, True)
        self.grab_set()
        init_db()
        cats = get_categories()
        self._cat_map   = {c.name: c.id for c in cats}
        self._cat_names = [c.name for c in cats]
        self._build()

    def _build(self):
        pad = {"padx": 16, "pady": 5}
        scroll = ctk.CTkScrollableFrame(self)
        scroll.pack(fill="both", expand=True, padx=0, pady=0)

        ctk.CTkLabel(
            scroll,
            text="📬  Conversion mail → tâche QuickMind",
            font=ctk.CTkFont(size=13, weight="bold"),
            text_color="#0078D4"
        ).pack(**pad)

        info_frame = ctk.CTkFrame(scroll, fg_color=("gray85","gray20"), corner_radius=8)
        info_frame.pack(fill="x", **pad)
        ctk.CTkLabel(
            info_frame,
            text=(
                f"De    : {self.mail.get('sender','?')}\n"
                f"Objet : {self.mail.get('subject','?')[:60]}\n"
                f"Recu  : {self.mail.get('received','?')}\n"
                f"PJ    : {self.mail.get('att_count',0)} fichier(s)"
            ),
            font=ctk.CTkFont(family="Consolas", size=11),
            justify="left", anchor="w"
        ).pack(padx=10, pady=8, fill="x")

        ctk.CTkLabel(scroll, text="Titre de la tâche :", anchor="w").pack(fill="x", **pad)
        self._title_e = ctk.CTkEntry(scroll, height=34)
        self._title_e.pack(fill="x", **pad)
        self._title_e.insert(0, self.mail.get("subject","")[:100])

        ctk.CTkLabel(scroll, text="Catégorie :", anchor="w").pack(fill="x", **pad)
        self._cat_var = ctk.StringVar(value=self._cat_names[0] if self._cat_names else "")
        ctk.CTkOptionMenu(scroll, values=self._cat_names,
                          variable=self._cat_var, height=34).pack(fill="x", **pad)

        ctk.CTkLabel(scroll, text="Priorité :", anchor="w").pack(fill="x", **pad)
        self._prio_var = ctk.StringVar(value="normal")
        ctk.CTkSegmentedButton(scroll,
            values=["low","normal","high","urgent"],
            variable=self._prio_var).pack(fill="x", **pad)

        ctk.CTkLabel(scroll, text="Que voulez-vous récupérer ?",
            anchor="w", font=ctk.CTkFont(size=12, weight="bold")
        ).pack(fill="x", **pad)

        options_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        options_frame.pack(fill="x", **pad)

        self._get_body = ctk.BooleanVar(value=True)
        self._get_atts = ctk.BooleanVar(value=self.mail.get("att_count",0) > 0)

        ctk.CTkCheckBox(options_frame,
            text="Corps du mail  (sauvegardé en .txt joint à la tâche)",
            variable=self._get_body,
            font=ctk.CTkFont(size=12)).pack(anchor="w", pady=4)

        att_count = self.mail.get("att_count", 0)
        ctk.CTkCheckBox(options_frame,
            text=f"Pièces jointes  ({att_count} fichier(s))" if att_count > 0 else "Pièces jointes  (aucune)",
            variable=self._get_atts,
            font=ctk.CTkFont(size=12),
            state="normal" if att_count > 0 else "disabled").pack(anchor="w", pady=4)

        for name in self.mail.get("att_names", []):
            ctk.CTkLabel(options_frame, text=f"     📎 {name}",
                text_color="#88BBFF", font=ctk.CTkFont(size=11)).pack(anchor="w")

        ctk.CTkLabel(scroll, text="").pack()

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(6,14), side="bottom")
        ctk.CTkButton(btn_row, text="✅  Créer la tâche", height=38,
            fg_color="#2a5a2a", hover_color="#1a4a1a",
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._confirm).pack(side="left", expand=True, padx=(0,6))
        ctk.CTkButton(btn_row, text="Annuler", height=38,
            fg_color="gray30", hover_color="gray20",
            command=self.destroy).pack(side="right", expand=True, padx=(6,0))

    def _confirm(self):
        title    = self._title_e.get().strip() or self.mail.get("subject","Tache")
        cat_id   = self._cat_map.get(self._cat_var.get())
        priority = self._prio_var.get()
        get_body = self._get_body.get()
        get_atts = self._get_atts.get()
        mail     = self.mail
        self.destroy()
        self.on_confirm(mail, title, cat_id, priority, get_body, get_atts)


class OutlookPanel(ctk.CTkToplevel):
    def __init__(self, master, on_task_created=None):
        super().__init__(master)
        self.on_task_created = on_task_created
        self._last_mails     = []
        self.title("Outlook — Agent IA")
        self.geometry("720x660")
        self.minsize(600, 520)
        self.grab_set()
        self._build()

    def _build(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=14, pady=(12,6))
        ctk.CTkLabel(header, text="📬  Outlook — Agent IA",
            font=ctk.CTkFont(size=15, weight="bold"),
            text_color="#0078D4").pack(side="left")
        self._status = ctk.CTkLabel(header, text="● prêt",
            font=ctk.CTkFont(size=10), text_color="#32CD32")
        self._status.pack(side="right")

        # Boutons rapides
        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=14, pady=(0,4))
        for label, cmd in [
            ("📬 Mails non lus",  "Montre mes mails non lus"),
            ("📅 Agenda 7j",      "Montre mon agenda des 7 prochains jours"),
            ("✅ Tâches Outlook", "Montre mes taches Outlook"),
            ("📨 Derniers mails", "Montre mes derniers mails recus"),
        ]:
            ctk.CTkButton(btn_row, text=label, height=30,
                fg_color="#1a3a5c", hover_color="#0078D4",
                command=lambda c=cmd: self._run_cmd(c)).pack(side="left", padx=4)

        # Boutons résumé IA
        ai_row = ctk.CTkFrame(self, fg_color="transparent")
        ai_row.pack(fill="x", padx=14, pady=(0,8))
        ctk.CTkLabel(ai_row, text="🤖 IA :", font=ctk.CTkFont(size=11),
            text_color="#1E90FF").pack(side="left", padx=(0,6))
        ctk.CTkButton(ai_row, text="📝 Résumé mail #...", height=26, width=150,
            fg_color="#1a2a4a", hover_color="#1E90FF",
            font=ctk.CTkFont(size=11),
            command=lambda: self._open_summarize_dialog("auto")
        ).pack(side="left", padx=4)
        ctk.CTkButton(ai_row, text="📄 Corps complet #...", height=26, width=160,
            fg_color="#1a2a4a", hover_color="#1E90FF",
            font=ctk.CTkFont(size=11),
            command=lambda: self._open_summarize_dialog("full")
        ).pack(side="left", padx=4)

        self._chat = ctk.CTkTextbox(self,
            font=ctk.CTkFont(family="Consolas", size=12),
            state="disabled", wrap="word")
        self._chat.pack(fill="both", expand=True, padx=10, pady=4)

        self._action_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._action_frame.pack(fill="x", padx=10, pady=(0,4))

        input_row = ctk.CTkFrame(self, fg_color="transparent")
        input_row.pack(fill="x", padx=10, pady=(0,12))
        input_row.grid_columnconfigure(0, weight=1)

        self._entry = ctk.CTkEntry(input_row, height=36,
            placeholder_text="Ex: Resume le mail #2 | Montre mes mails non lus...",
            font=ctk.CTkFont(size=12))
        self._entry.grid(row=0, column=0, sticky="ew", padx=(0,8))
        self._entry.bind("<Return>", lambda e: self._send())

        self._send_btn = ctk.CTkButton(input_row, text="Envoyer",
            width=90, height=36, fg_color="#0078D4", hover_color="#005a9e",
            command=self._send)
        self._send_btn.grid(row=0, column=1)
        ctk.CTkButton(input_row, text="Effacer", width=80, height=36,
            fg_color="gray30", command=self._clear).grid(row=0, column=2, padx=(6,0))

        self._append("Outlook",
            "Agent Outlook connecte.\n\n"
            "Commandes disponibles :\n"
            "  - Montre mes mails non lus\n"
            "  - Montre mon agenda des 7 prochains jours\n"
            "  - Cree un evenement : reunion equipe vendredi 14h\n"
            "  - Envoie un mail a prenom@domaine.com pour...\n"
            "  - Montre mes taches Outlook\n\n"
            "Boutons IA :\n"
            "  Resume mail #N  : Mistral resume le mail numero N\n"
            "  Corps complet #N: affiche le corps entier du mail N\n\n"
            "Apres avoir liste des mails, des boutons [Convertir]\n"
            "apparaissent pour creer une tache QuickMind avec\n"
            "categorie, priorite, PJ et corps du mail."
        )

    def _append(self, role: str, text: str):
        self._chat.configure(state="normal")
        self._chat.insert("end", "-" * 60 + "\n")
        self._chat.insert("end", role + "\n")
        self._chat.insert("end", text + "\n\n")
        self._chat.configure(state="disabled")
        self._chat.see("end")

    def _run_cmd(self, cmd: str):
        self._entry.delete(0, "end")
        self._entry.insert(0, cmd)
        self._send()

    # ── Résumé / corps complet ─────────────────────────────────────────────
    def _open_summarize_dialog(self, mode: str):
        """Demande le numéro du mail puis lance le résumé IA."""
        if not self._last_mails:
            self._append("Info", "Listez d abord des mails (Mails non lus ou Derniers mails).")
            return

        dialog = ctk.CTkToplevel(self)
        dialog.title("Quel mail ?")
        dialog.geometry("340x160")
        dialog.resizable(False, False)
        dialog.grab_set()

        label = "Résumé IA" if mode == "auto" else "Corps complet"
        ctk.CTkLabel(dialog,
            text=f"{label} — numéro du mail (1 à {len(self._last_mails)}) :",
            font=ctk.CTkFont(size=12)
        ).pack(padx=16, pady=(16,6))

        entry = ctk.CTkEntry(dialog, height=34, width=80)
        entry.pack(padx=16, pady=4)
        entry.insert(0, "1")
        entry.focus()

        def _go():
            try:
                idx = int(entry.get().strip()) - 1
                if idx < 0 or idx >= len(self._last_mails):
                    return
                mail = self._last_mails[idx]
                entry_id = mail.get("entry_id") or mail.get("id")
                dialog.destroy()
                self._run_summarize(entry_id, mail.get("subject",""), mode)
            except ValueError:
                pass

        entry.bind("<Return>", lambda e: _go())
        ctk.CTkButton(dialog, text="OK", height=34, command=_go).pack(pady=8)

    def _run_summarize(self, entry_id: str, subject: str, mode: str):
        label = "Résumé IA" if mode == "auto" else "Corps complet"
        self._append("Vous", f"{label} du mail : {subject}")
        self._status.configure(text="● Mistral...", text_color="#FFD700")
        self._send_btn.configure(state="disabled")

        def _run():
            result = summarize_mail(entry_id, mode=mode)
            self.after(0, lambda: self._on_summarize_done(result))

        threading.Thread(target=_run, daemon=True).start()

    def _on_summarize_done(self, result: str):
        self._status.configure(text="● prêt", text_color="#32CD32")
        self._send_btn.configure(state="normal")
        self._append("IA 🤖", result)

    # ── Send ───────────────────────────────────────────────────────────────
    def _send(self):
        prompt = self._entry.get().strip()
        if not prompt:
            return

        # Detecte si c est une demande de resume directe : "resume mail #2"
        import re
        m = re.match(r"(resum[ée]|corps|complet).*#(\d+)", prompt.lower())
        if m and self._last_mails:
            mode = "full" if "corps" in m.group(1) or "complet" in m.group(1) else "auto"
            idx  = int(m.group(2)) - 1
            if 0 <= idx < len(self._last_mails):
                mail     = self._last_mails[idx]
                entry_id = mail.get("entry_id") or mail.get("id")
                self._append("Vous", prompt)
                self._entry.delete(0, "end")
                self._run_summarize(entry_id, mail.get("subject",""), mode)
                return

        self._append("Vous", prompt)
        self._entry.delete(0, "end")
        self._send_btn.configure(state="disabled", text="...")
        self._status.configure(text="● traitement...", text_color="#FFD700")
        for w in self._action_frame.winfo_children():
            w.destroy()

        def _run():
            result, mails = ask_outlook(prompt)
            self.after(0, lambda: self._on_response(result, mails))

        threading.Thread(target=_run, daemon=True).start()

    def _on_response(self, result: str, mails):
        self._send_btn.configure(state="normal", text="Envoyer")
        self._status.configure(text="● prêt", text_color="#32CD32")

        if result.startswith("MAIL_TO_TASK:"):
            mail = mails[0] if mails else None
            if mail:
                self._open_dialog(mail)
            return

        self._append("Outlook", result)

        if mails:
            self._last_mails = mails
            self._show_mail_actions(mails)

    def _show_mail_actions(self, mails: list):
        for w in self._action_frame.winfo_children():
            w.destroy()
        ctk.CTkLabel(self._action_frame, text="→ Convertir en tâche :",
            text_color="gray", font=ctk.CTkFont(size=11)
        ).pack(side="left", padx=(4,8))
        for i, m in enumerate(mails[:5]):
            short    = m["subject"][:20] + ("..." if len(m["subject"]) > 20 else "")
            att_icon = " 📎" if m.get("att_count",0) > 0 else ""
            ctk.CTkButton(self._action_frame,
                text=f"#{i+1} {short}{att_icon}",
                height=26, width=170,
                fg_color="#1a3a1a", hover_color="#2a5a2a",
                font=ctk.CTkFont(size=10),
                command=lambda mail=m: self._open_dialog(mail)
            ).pack(side="left", padx=3)

    def _open_dialog(self, mail: dict):
        entry_id = mail.get("entry_id") or mail.get("id")
        if entry_id:
            try:
                full = get_mail_info(entry_id)
                mail = {**mail, **full}
            except Exception:
                pass
        self._current_dialog = MailToTaskDialog(
            self, mail=mail, on_confirm=self._do_create_task)

    def _do_create_task(self, mail, title, cat_id, priority, get_body, get_atts):
        init_db()
        entry_id = mail.get("entry_id") or mail.get("id")
        sep  = "-" * 40
        desc = (
            f"De    : {mail.get('sender','?')} <{mail.get('sender_email','')}>\n"
            f"Recu  : {mail.get('received','?')}\n"
            f"{sep}\n"
            + (mail.get("body_full") or mail.get("body_preview",""))[:500]
        )
        task = add_task(title=title, description=desc,
                        category_id=cat_id, priority=priority)
        saved_files = []
        if get_body and entry_id:
            try:
                p = save_mail_body_as_file(entry_id, task.id, mail.get("subject","mail"))
                saved_files.append(p)
            except Exception as e:
                self._append("Erreur", f"Corps du mail : {e}")
        if get_atts and entry_id:
            try:
                paths = save_mail_attachments(entry_id, task.id)
                saved_files.extend(paths)
            except Exception as e:
                self._append("Erreur", f"Pieces jointes : {e}")
        if saved_files:
            from core.database import set_task_attachments
            set_task_attachments(task.id, saved_files)
        report = ""
        if saved_files:
            report = "\nFichiers recuperes :\n"
            for p in saved_files:
                report += f"  📎 {os.path.basename(p)}\n"
        self._append("QuickMind", f"✅ Tache #{task.id} creee : {title}" + report)
        if self.on_task_created:
            self.on_task_created()

    def _clear(self):
        self._chat.configure(state="normal")
        self._chat.delete("0.0", "end")
        self._chat.configure(state="disabled")
        for w in self._action_frame.winfo_children():
            w.destroy()
