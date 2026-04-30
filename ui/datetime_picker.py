"""
DateTimePicker — widget de selection de date et heure
Fonctionne avec customtkinter, sans dependance externe.
"""
import customtkinter as ctk
import calendar
from datetime import datetime, date


class DateTimePicker(ctk.CTkToplevel):
    """
    Popup de selection date + heure.
    Retourne la datetime selectionnee via le callback on_select(dt: datetime).
    """

    def __init__(self, master, on_select, initial: datetime = None):
        super().__init__(master)
        self.on_select = on_select
        self.title("Choisir une date et une heure")
        self.resizable(False, False)
        self.grab_set()

        now = initial or datetime.now()
        self._year  = ctk.IntVar(value=now.year)
        self._month = ctk.IntVar(value=now.month)
        self._hour  = ctk.IntVar(value=now.hour)
        self._min   = ctk.IntVar(value=now.minute)
        self._selected_day = ctk.IntVar(value=now.day)

        self._day_buttons = {}
        self._build()
        self._draw_calendar()

    # ── Construction de la fenetre ────────────────────────────────────────
    def _build(self):
        pad = {"padx": 10, "pady": 4}

        # ── Navigation mois / annee ───────────────────────────────────────
        nav = ctk.CTkFrame(self, fg_color="transparent")
        nav.pack(fill="x", **pad)

        ctk.CTkButton(nav, text="◀", width=32, height=28,
                      command=self._prev_month).pack(side="left")

        self._month_label = ctk.CTkLabel(
            nav, text="", width=160,
            font=ctk.CTkFont(size=13, weight="bold")
        )
        self._month_label.pack(side="left", expand=True)

        ctk.CTkButton(nav, text="▶", width=32, height=28,
                      command=self._next_month).pack(side="right")

        # ── En-tetes jours ────────────────────────────────────────────────
        days_header = ctk.CTkFrame(self, fg_color="transparent")
        days_header.pack(fill="x", padx=10)
        for day_name in ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]:
            ctk.CTkLabel(
                days_header, text=day_name, width=38,
                font=ctk.CTkFont(size=11),
                text_color="#888"
            ).pack(side="left")

        # ── Grille des jours ──────────────────────────────────────────────
        self._cal_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._cal_frame.pack(fill="x", padx=10, pady=(2, 6))

        # ── Separateur ────────────────────────────────────────────────────
        ctk.CTkFrame(self, height=1,
                     fg_color=("gray70", "gray30")).pack(fill="x", padx=10, pady=4)

        # ── Heure ─────────────────────────────────────────────────────────
        time_frame = ctk.CTkFrame(self, fg_color="transparent")
        time_frame.pack(fill="x", padx=10, pady=4)

        ctk.CTkLabel(
            time_frame, text="Heure :",
            font=ctk.CTkFont(size=12, weight="bold")
        ).pack(side="left", padx=(0, 10))

        # Heures
        ctk.CTkButton(time_frame, text="▲", width=28, height=22,
                      command=lambda: self._inc("hour", 1)).pack(side="left")
        self._hour_label = ctk.CTkLabel(
            time_frame, text="00", width=36,
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self._hour_label.pack(side="left")
        ctk.CTkButton(time_frame, text="▼", width=28, height=22,
                      command=lambda: self._inc("hour", -1)).pack(side="left")

        ctk.CTkLabel(time_frame, text=":", width=10,
                     font=ctk.CTkFont(size=16, weight="bold")
                     ).pack(side="left")

        # Minutes
        ctk.CTkButton(time_frame, text="▲", width=28, height=22,
                      command=lambda: self._inc("min", 5)).pack(side="left")
        self._min_label = ctk.CTkLabel(
            time_frame, text="00", width=36,
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self._min_label.pack(side="left")
        ctk.CTkButton(time_frame, text="▼", width=28, height=22,
                      command=lambda: self._inc("min", -5)).pack(side="left")

        # Raccourcis horaires
        quick_times = ctk.CTkFrame(self, fg_color="transparent")
        quick_times.pack(fill="x", padx=10, pady=(0, 6))
        ctk.CTkLabel(quick_times, text="Rapide :",
                     font=ctk.CTkFont(size=11), text_color="gray"
                     ).pack(side="left", padx=(0, 6))
        for h, label in [(8,"08:00"),(9,"09:00"),(12,"12:00"),
                         (14,"14:00"),(17,"17:00"),(18,"18:00")]:
            ctk.CTkButton(
                quick_times, text=label, height=24, width=54,
                fg_color="gray30", hover_color="gray20",
                font=ctk.CTkFont(size=11),
                command=lambda hh=h: self._set_time(hh, 0)
            ).pack(side="left", padx=2)

        # ── Separateur ────────────────────────────────────────────────────
        ctk.CTkFrame(self, height=1,
                     fg_color=("gray70", "gray30")).pack(fill="x", padx=10, pady=4)

        # ── Preview + boutons ─────────────────────────────────────────────
        preview_row = ctk.CTkFrame(self, fg_color="transparent")
        preview_row.pack(fill="x", padx=10, pady=(0, 4))

        self._preview = ctk.CTkLabel(
            preview_row, text="",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color="#1E90FF"
        )
        self._preview.pack(side="left")

        btn_row = ctk.CTkFrame(self, fg_color="transparent")
        btn_row.pack(fill="x", padx=10, pady=(0, 12))

        ctk.CTkButton(
            btn_row, text="✅ Confirmer",
            command=self._confirm
        ).pack(side="left", expand=True, padx=(0, 4))

        ctk.CTkButton(
            btn_row, text="🗑 Effacer le rappel",
            fg_color="gray30",
            command=self._clear
        ).pack(side="left", expand=True, padx=(4, 0))

        self._update_labels()

    # ── Calendrier ───────────────────────────────────────────────────────
    def _draw_calendar(self):
        for w in self._cal_frame.winfo_children():
            w.destroy()
        self._day_buttons.clear()

        y = self._year.get()
        m = self._month.get()
        MONTHS_FR = ["Janvier","Fevrier","Mars","Avril","Mai","Juin",
                     "Juillet","Aout","Septembre","Octobre","Novembre","Decembre"]
        self._month_label.configure(text=f"{MONTHS_FR[m-1]} {y}")

        cal = calendar.monthcalendar(y, m)
        today = date.today()

        for week in cal:
            row_frame = ctk.CTkFrame(self._cal_frame, fg_color="transparent")
            row_frame.pack(fill="x", pady=1)
            for day in week:
                if day == 0:
                    ctk.CTkLabel(row_frame, text="", width=38).pack(side="left")
                else:
                    is_today    = (day == today.day and m == today.month and y == today.year)
                    is_selected = (day == self._selected_day.get())
                    fg = "#1E90FF" if is_selected else ("#FF8C00" if is_today else "gray25")
                    btn = ctk.CTkButton(
                        row_frame,
                        text=str(day),
                        width=34, height=28,
                        corner_radius=6,
                        fg_color=fg,
                        hover_color="#1E90FF",
                        font=ctk.CTkFont(size=11,
                                         weight="bold" if is_today or is_selected else "normal"),
                        command=lambda d=day: self._select_day(d)
                    )
                    btn.pack(side="left", padx=1)
                    self._day_buttons[day] = btn

    # ── Navigation ───────────────────────────────────────────────────────
    def _prev_month(self):
        m = self._month.get()
        y = self._year.get()
        if m == 1:
            self._month.set(12)
            self._year.set(y - 1)
        else:
            self._month.set(m - 1)
        self._selected_day.set(1)
        self._draw_calendar()
        self._update_labels()

    def _next_month(self):
        m = self._month.get()
        y = self._year.get()
        if m == 12:
            self._month.set(1)
            self._year.set(y + 1)
        else:
            self._month.set(m + 1)
        self._selected_day.set(1)
        self._draw_calendar()
        self._update_labels()

    def _select_day(self, day: int):
        self._selected_day.set(day)
        self._draw_calendar()
        self._update_labels()

    # ── Heure ────────────────────────────────────────────────────────────
    def _inc(self, field: str, delta: int):
        if field == "hour":
            self._hour.set((self._hour.get() + delta) % 24)
        else:
            self._min.set((self._min.get() + delta) % 60)
        self._update_labels()

    def _set_time(self, h: int, m: int):
        self._hour.set(h)
        self._min.set(m)
        self._update_labels()

    # ── Mise a jour des labels ────────────────────────────────────────────
    def _update_labels(self):
        self._hour_label.configure(text=f"{self._hour.get():02d}")
        self._min_label.configure(text=f"{self._min.get():02d}")
        dt = self._get_datetime()
        DAYS_FR   = ["lundi","mardi","mercredi","jeudi","vendredi","samedi","dimanche"]
        MONTHS_FR = ["jan","fev","mar","avr","mai","jun",
                     "jul","aou","sep","oct","nov","dec"]
        day_name  = DAYS_FR[dt.weekday()]
        self._preview.configure(
            text=f"  {day_name.capitalize()} {dt.day} {MONTHS_FR[dt.month-1]}"
                 f" {dt.year}  a  {dt.hour:02d}:{dt.minute:02d}"
        )

    def _get_datetime(self) -> datetime:
        return datetime(
            self._year.get(), self._month.get(), self._selected_day.get(),
            self._hour.get(), self._min.get()
        )

    # ── Actions finales ───────────────────────────────────────────────────
    def _confirm(self):
        dt = self._get_datetime()
        self.on_select(dt)
        self.destroy()

    def _clear(self):
        self.on_select(None)
        self.destroy()
