import asyncio
import json
import os
import queue
import threading
import time
import wave
import math
import struct
import shutil
from collections import deque
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from pathlib import Path

import edge_tts
import pygame
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

APP_NAME = "MOORTTYS VOICE"
ROOT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = ROOT_DIR / "settings.json"
AUDIO_PATH = ROOT_DIR / "moorttys_voice_tts.mp3"
SOUNDS_DIR = ROOT_DIR / "sounds"
DEFAULT_SOUND_FILES = {"subscriber": SOUNDS_DIR / "entrada_suscriptor.wav", "visitor": SOUNDS_DIR / "entrada_visitante.wav", "unknown": SOUNDS_DIR / "entrada_sin_verificar.wav"}

COLORS = {
    "bg": "#09090b", "panel": "#131317", "panel2": "#1b1b22",
    "red": "#e50914", "red_hover": "#ff2833", "text": "#f5f5f7",
    "muted": "#a1a1aa", "green": "#22c55e", "border": "#303039",
}

DEFAULTS = {
    "platform": "TikTok LIVE", "api_key": "", "channel_id": "",
    "tiktok_username": "", "tiktok_session_id": "", "tiktok_target_idc": "",
    "use_tiktok_session": False, "voice": "es-MX-DaliaNeural", "rate": "+0%",
    "read_comments": True, "speak_author": True, "read_gifts": False,
    "read_social_events": False, "max_message_length": 220,
    "blocked_users": "", "anti_spam": True,
    "join_alerts_enabled": True, "join_notifications_enabled": True, "join_sound_volume": 75,
    "join_welcome_enabled": True, "join_welcome_template": "¡Bienvenido al directo, {nombre}!",
    "subscriber_sound": "", "visitor_sound": "", "unknown_sound": "",
}


def load_settings():
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        # Never restore or persist TikTok session cookies from settings.json.
        data["tiktok_session_id"] = ""
        data["tiktok_target_idc"] = ""
        return {**DEFAULTS, **data}
    except Exception:
        return DEFAULTS.copy()


def save_settings(settings):
    CONFIG_PATH.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")


class MoorttysVoiceApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Moorttys Voice | YouTube + TikTok LIVE")
        self.root.geometry("1020x790")
        self.root.minsize(900, 700)
        self.root.configure(bg=COLORS["bg"])
        self.settings = load_settings()
        self.stop_event = threading.Event()
        self.poll_thread = None
        self.audio_queue = queue.Queue()
        self.seen_ids = set()
        self.reader_started_at = 0.0
        self.recent_messages = deque(maxlen=100)
        self.last_spoken = deque(maxlen=10)
        self.recent_joins = {}
        self.live_chat_id = None
        self.running = False
        self.tiktok_client = None
        self.tiktok_loop = None
        self._setup_style()
        self._build_ui()
        self._start_audio_worker()
        self._set_status("LISTO", "Elige YouTube LIVE o TikTok LIVE y configura la conexión.")
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def _setup_style(self):
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TCombobox", fieldbackground=COLORS["panel2"], background=COLORS["panel2"],
                        foreground=COLORS["text"], arrowcolor=COLORS["text"])
        style.map("TCombobox", fieldbackground=[("readonly", COLORS["panel2"])],
                  foreground=[("readonly", COLORS["text"])])

    def _label(self, parent, text, color=None, size=10, bold=False):
        return tk.Label(parent, text=text, bg=parent.cget("bg"), fg=color or COLORS["text"],
                        font=("Segoe UI", size, "bold" if bold else "normal"))

    def _entry(self, parent, variable, show=None):
        return tk.Entry(parent, textvariable=variable, show=show, bg=COLORS["panel2"],
                        fg=COLORS["text"], insertbackground=COLORS["text"], relief="flat",
                        highlightthickness=1, highlightbackground=COLORS["border"],
                        highlightcolor=COLORS["red"], font=("Segoe UI", 10))

    def _button(self, parent, text, command, primary=False):
        return tk.Button(parent, text=text, command=command,
                         bg=COLORS["red"] if primary else COLORS["panel2"], fg="white",
                         activebackground=COLORS["red_hover"] if primary else "#292932",
                         activeforeground="white", relief="flat", bd=0, padx=14, pady=9,
                         cursor="hand2", font=("Segoe UI", 9, "bold"))

    def _build_ui(self):
        # Dashboard UI: custom dark studio layout, scrollable control rail, live chat workspace.
        self.root.geometry("1360x900")
        self.root.minsize(1120, 760)
        self.root.configure(bg=COLORS["bg"])

        style = ttk.Style()
        style.configure("TCombobox", fieldbackground=COLORS["panel2"], background=COLORS["panel2"],
                        foreground=COLORS["text"], arrowcolor=COLORS["text"], borderwidth=0, padding=7)
        style.map("TCombobox", fieldbackground=[("readonly", COLORS["panel2"])],
                  foreground=[("readonly", COLORS["text"])])

        # Top brand bar
        header = tk.Frame(self.root, bg="#0c0c10", height=86,
                          highlightbackground=COLORS["border"], highlightthickness=1)
        header.pack(fill="x")
        header.pack_propagate(False)
        brand = tk.Frame(header, bg="#0c0c10")
        brand.pack(side="left", padx=24, pady=14)
        mark = tk.Frame(brand, bg=COLORS["red"], width=48, height=48)
        mark.pack(side="left", padx=(0, 13))
        mark.pack_propagate(False)
        tk.Label(mark, text="☘", bg=COLORS["red"], fg="white",
                 font=("Segoe UI Symbol", 27, "bold")).place(relx=.5, rely=.47, anchor="center")
        brand_text = tk.Frame(brand, bg="#0c0c10")
        brand_text.pack(side="left")
        tk.Label(brand_text, text="MOORTTYS VOICE", bg="#0c0c10", fg=COLORS["text"],
                 font=("Segoe UI", 20, "bold")).pack(anchor="w")
        tk.Label(brand_text, text="LIVE AUDIO STUDIO  /  YOUTUBE + TIKTOK", bg="#0c0c10",
                 fg=COLORS["muted"], font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(2, 0))

        header_right = tk.Frame(header, bg="#0c0c10")
        header_right.pack(side="right", padx=24)
        self.status_badge = tk.Label(header_right, text="●  SISTEMA LISTO", bg="#14251b", fg=COLORS["green"],
                                     padx=15, pady=9, font=("Segoe UI", 9, "bold"),
                                     highlightthickness=1, highlightbackground="#244531")
        self.status_badge.pack(side="right", pady=22)
        tk.Label(header_right, text="DESKTOP  •  v1.1 DEV", bg="#0c0c10", fg="#666671",
                 font=("Segoe UI", 8, "bold")).pack(side="right", padx=(0, 16), pady=30)

        workspace = tk.Frame(self.root, bg=COLORS["bg"], padx=18, pady=18)
        workspace.pack(fill="both", expand=True)

        # Left control rail, using a canvas so the controls remain reachable on smaller screens.
        rail = tk.Frame(workspace, bg=COLORS["panel"], width=365,
                        highlightbackground=COLORS["border"], highlightthickness=1)
        rail.pack(side="left", fill="y", padx=(0, 16))
        rail.pack_propagate(False)
        rail_head = tk.Frame(rail, bg=COLORS["panel"], padx=18, pady=16)
        rail_head.pack(fill="x")
        tk.Label(rail_head, text="CONTROL CENTER", bg=COLORS["panel"], fg=COLORS["text"],
                 font=("Segoe UI", 12, "bold")).pack(anchor="w")
        tk.Label(rail_head, text="Configura tu sesión y tu voz", bg=COLORS["panel"], fg=COLORS["muted"],
                 font=("Segoe UI", 9)).pack(anchor="w", pady=(4, 0))
        tk.Frame(rail, bg=COLORS["border"], height=1).pack(fill="x")

        controls_canvas = tk.Canvas(rail, bg=COLORS["panel"], highlightthickness=0, bd=0)
        controls_scroll = ttk.Scrollbar(rail, orient="vertical", command=controls_canvas.yview)
        controls_canvas.configure(yscrollcommand=controls_scroll.set)
        controls_scroll.pack(side="right", fill="y")
        controls_canvas.pack(side="left", fill="both", expand=True)
        controls = tk.Frame(controls_canvas, bg=COLORS["panel"], padx=18, pady=15)
        controls_window = controls_canvas.create_window((0, 0), window=controls, anchor="nw")
        controls.bind("<Configure>", lambda _e: controls_canvas.configure(scrollregion=controls_canvas.bbox("all")))
        controls_canvas.bind("<Configure>", lambda e: controls_canvas.itemconfigure(controls_window, width=e.width))
        controls_canvas.bind_all("<MouseWheel>", lambda e: controls_canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

        def section(parent, title, subtitle=None):
            tk.Label(parent, text=title, bg=COLORS["panel"], fg=COLORS["red_hover"],
                     font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(8, 6))
            if subtitle:
                tk.Label(parent, text=subtitle, bg=COLORS["panel"], fg=COLORS["muted"],
                         font=("Segoe UI", 8), wraplength=300, justify="left").pack(anchor="w", pady=(0, 6))

        section(controls, "01  /  PLATAFORMA", "Elige el chat que quieres escuchar")
        self.platform_var = tk.StringVar(value=self.settings["platform"])
        self.platform_combo = ttk.Combobox(controls, textvariable=self.platform_var, state="readonly",
                                           values=["TikTok LIVE", "YouTube LIVE"])
        self.platform_combo.pack(fill="x", ipady=3)
        self.platform_combo.bind("<<ComboboxSelected>>", self._switch_platform)

        self.youtube_frame = tk.Frame(controls, bg=COLORS["panel"])
        self._label(self.youtube_frame, "YOUTUBE API KEY", color=COLORS["muted"], size=8, bold=True).pack(anchor="w", pady=(12, 4))
        self.api_var = tk.StringVar(value=self.settings["api_key"])
        self._entry(self.youtube_frame, self.api_var, show="•").pack(fill="x", ipady=7)
        self._label(self.youtube_frame, "ID DEL CANAL", color=COLORS["muted"], size=8, bold=True).pack(anchor="w", pady=(9, 4))
        self.channel_var = tk.StringVar(value=self.settings["channel_id"])
        self._entry(self.youtube_frame, self.channel_var).pack(fill="x", ipady=7)
        self._label(self.youtube_frame, "Requiere YouTube Data API v3.", color=COLORS["muted"], size=8).pack(anchor="w", pady=(5, 0))

        self.tiktok_frame = tk.Frame(controls, bg=COLORS["panel"])
        self._label(self.tiktok_frame, "USUARIO EN DIRECTO", color=COLORS["muted"], size=8, bold=True).pack(anchor="w", pady=(12, 4))
        self.tiktok_username_var = tk.StringVar(value=self.settings["tiktok_username"])
        self._entry(self.tiktok_frame, self.tiktok_username_var).pack(fill="x", ipady=7)
        self._label(self.tiktok_frame, "Escribe @usuario o pega el enlace del LIVE.", color=COLORS["muted"], size=8).pack(anchor="w", pady=(5, 0))
        self.use_session_var = tk.BooleanVar(value=self.settings["use_tiktok_session"])
        tk.Checkbutton(self.tiktok_frame, text="Conexión avanzada con sesión (opcional)",
                       variable=self.use_session_var, command=self._toggle_session_fields,
                       bg=COLORS["panel"], fg=COLORS["text"], selectcolor=COLORS["panel2"],
                       activebackground=COLORS["panel"], activeforeground=COLORS["text"],
                       font=("Segoe UI", 8)).pack(anchor="w", pady=(8, 3))
        self.session_fields = tk.Frame(self.tiktok_frame, bg=COLORS["panel"])
        self._label(self.session_fields, "sessionid (cookie sensible)", color=COLORS["muted"], size=8).pack(anchor="w", pady=(3, 3))
        self.tiktok_session_var = tk.StringVar(value=self.settings["tiktok_session_id"])
        self._entry(self.session_fields, self.tiktok_session_var, show="•").pack(fill="x", ipady=6)
        self._label(self.session_fields, "tt-target-idc", color=COLORS["muted"], size=8).pack(anchor="w", pady=(7, 3))
        self.tiktok_target_var = tk.StringVar(value=self.settings["tiktok_target_idc"])
        self._entry(self.session_fields, self.tiktok_target_var, show="•").pack(fill="x", ipady=6)
        self._label(self.tiktok_frame, "Las cookies no se guardan en settings.json. Usa solo si confías en el proveedor de conexión.",
                    color="#e5a0a4", size=8).pack(anchor="w", pady=(7, 0))

        section(controls, "02  /  MOTOR DE VOZ", "Personaliza cómo suena tu lector")
        self.voice_var = tk.StringVar(value=self.settings["voice"])
        ttk.Combobox(controls, textvariable=self.voice_var, state="readonly",
                     values=["es-MX-DaliaNeural", "es-MX-JorgeNeural", "es-ES-ElviraNeural",
                             "es-ES-AlvaroNeural", "es-CR-MariaNeural", "es-CR-JuanNeural"]).pack(fill="x", ipady=3)
        self._label(controls, "VELOCIDAD DE LECTURA", color=COLORS["muted"], size=8, bold=True).pack(anchor="w", pady=(10, 4))
        self.rate_var = tk.StringVar(value=self.settings["rate"])
        ttk.Combobox(controls, textvariable=self.rate_var, state="readonly",
                     values=["-20%", "-10%", "+0%", "+10%", "+20%"]).pack(fill="x", ipady=3)

        section(controls, "03  /  FILTROS DE EVENTOS")
        self.read_comments_var = tk.BooleanVar(value=self.settings["read_comments"])
        self.speak_author_var = tk.BooleanVar(value=self.settings["speak_author"])
        self.read_gifts_var = tk.BooleanVar(value=self.settings["read_gifts"])
        self.read_social_var = tk.BooleanVar(value=self.settings["read_social_events"])
        self.anti_spam_var = tk.BooleanVar(value=self.settings.get("anti_spam", True))
        self.max_length_var = tk.StringVar(value=str(self.settings.get("max_message_length", 220)))
        self.blocked_users_var = tk.StringVar(value=self.settings.get("blocked_users", ""))
        for text, var in [("Leer comentarios del chat", self.read_comments_var),
                          ("Decir el nombre del usuario", self.speak_author_var),
                          ("Leer regalos de TikTok", self.read_gifts_var),
                          ("Leer follows y compartidos", self.read_social_var)]:
            tk.Checkbutton(controls, text=text, variable=var, bg=COLORS["panel"], fg=COLORS["text"],
                           selectcolor=COLORS["panel2"], activebackground=COLORS["panel"],
                           activeforeground=COLORS["text"], font=("Segoe UI", 9),
                           cursor="hand2").pack(anchor="w", pady=2)

        tk.Checkbutton(controls, text="Filtro anti-spam (evita repetidos)", variable=self.anti_spam_var,
                       bg=COLORS["panel"], fg=COLORS["text"], selectcolor=COLORS["panel2"],
                       activebackground=COLORS["panel"], activeforeground=COLORS["text"],
                       font=("Segoe UI", 9), cursor="hand2").pack(anchor="w", pady=(7, 3))
        self._label(controls, "LONGITUD MÁXIMA DEL MENSAJE", color=COLORS["muted"], size=8, bold=True).pack(anchor="w", pady=(5, 3))
        self._entry(controls, self.max_length_var).pack(fill="x", ipady=5)
        self._label(controls, "USUARIOS BLOQUEADOS (separados por coma)", color=COLORS["muted"], size=8, bold=True).pack(anchor="w", pady=(7, 3))
        self._entry(controls, self.blocked_users_var).pack(fill="x", ipady=5)

        section(controls, "04  /  ALERTAS DE ENTRADA", "Sonidos para entradas detectadas en TikTok LIVE")
        self.join_alerts_var = tk.BooleanVar(value=self.settings.get("join_alerts_enabled", True))
        self.join_notifications_var = tk.BooleanVar(value=self.settings.get("join_notifications_enabled", True))
        tk.Checkbutton(controls, text="Activar sonidos de entrada", variable=self.join_alerts_var,
                       bg=COLORS["panel"], fg=COLORS["text"], selectcolor=COLORS["panel2"],
                       activebackground=COLORS["panel"], activeforeground=COLORS["text"],
                       font=("Segoe UI", 9)).pack(anchor="w", pady=2)
        tk.Checkbutton(controls, text="Mostrar notificación en el chat", variable=self.join_notifications_var,
                       bg=COLORS["panel"], fg=COLORS["text"], selectcolor=COLORS["panel2"],
                       activebackground=COLORS["panel"], activeforeground=COLORS["text"],
                       font=("Segoe UI", 9)).pack(anchor="w", pady=2)
        self.join_welcome_var = tk.BooleanVar(value=self.settings.get("join_welcome_enabled", True))
        tk.Checkbutton(controls, text="Decir bienvenida por voz al entrar", variable=self.join_welcome_var,
                       bg=COLORS["panel"], fg=COLORS["text"], selectcolor=COLORS["panel2"],
                       activebackground=COLORS["panel"], activeforeground=COLORS["text"],
                       font=("Segoe UI", 9)).pack(anchor="w", pady=(5, 2))
        self._label(controls, "FRASE DE BIENVENIDA ({nombre} = nombre del usuario)", color=COLORS["muted"], size=8, bold=True).pack(anchor="w", pady=(6, 3))
        self.join_welcome_template_var = tk.StringVar(value=self.settings.get("join_welcome_template", "¡Bienvenido al directo, {nombre}!"))
        self._entry(controls, self.join_welcome_template_var).pack(fill="x", ipady=5)
        self._label(controls, "VOLUMEN DE ALERTAS", color=COLORS["muted"], size=8, bold=True).pack(anchor="w", pady=(7, 3))
        self.join_volume_var = tk.IntVar(value=int(self.settings.get("join_sound_volume", 75)))
        tk.Scale(controls, from_=0, to=100, orient="horizontal", variable=self.join_volume_var,
                 bg=COLORS["panel"], fg=COLORS["text"], troughcolor=COLORS["panel2"],
                 highlightthickness=0, activebackground=COLORS["red"],
                 command=lambda _v: None).pack(fill="x")
        self.sound_vars = {}
        for key, label in [("subscriber", "Suscriptor confirmado"), ("visitor", "No suscrito confirmado"), ("unknown", "Estado sin verificar")]:
            row = tk.Frame(controls, bg=COLORS["panel"])
            row.pack(fill="x", pady=3)
            tk.Label(row, text=label, bg=COLORS["panel"], fg=COLORS["text"], font=("Segoe UI", 8), anchor="w").pack(fill="x")
            self.sound_vars[key] = tk.StringVar(value=self.settings.get(f"{key}_sound", ""))
            tk.Entry(row, textvariable=self.sound_vars[key], bg=COLORS["panel2"], fg=COLORS["text"],
                     insertbackground=COLORS["text"], relief="flat", font=("Segoe UI", 8)).pack(side="left", fill="x", expand=True, ipady=5)
            self._button(row, "Elegir", lambda k=key: self._choose_sound(k)).pack(side="left", padx=(5, 0))
            self._button(row, "▶", lambda k=key: self._preview_sound(k)).pack(side="left", padx=(4, 0))
        self._label(controls, "WAV, MP3 u OGG. Si el estado no se puede comprobar, se usa el sonido neutral.", color=COLORS["muted"], size=8).pack(anchor="w", pady=(3, 0))

        tk.Frame(controls, bg=COLORS["border"], height=1).pack(fill="x", pady=(14, 12))
        self._button(controls, "▣   GUARDAR CONFIGURACIÓN", self.save_current).pack(fill="x", pady=(0, 7))
        self.start_btn = self._button(controls, "▶   INICIAR LECTOR", self.start_reader, primary=True)
        self.start_btn.pack(fill="x", pady=4, ipady=3)
        self.stop_btn = self._button(controls, "■   DETENER LECTOR", self.stop_reader)
        self.stop_btn.pack(fill="x", pady=4)
        self._button(controls, "♫   PROBAR VOZ", self.test_voice).pack(fill="x", pady=(4, 10))

        # Main studio area
        main = tk.Frame(workspace, bg=COLORS["bg"])
        main.pack(side="left", fill="both", expand=True)
        welcome = tk.Frame(main, bg=COLORS["bg"])
        welcome.pack(fill="x", pady=(0, 15))
        tk.Label(welcome, text="TU LIVE. TU VOZ. TU ESTUDIO.", bg=COLORS["bg"], fg=COLORS["text"],
                 font=("Segoe UI", 18, "bold")).pack(anchor="w")
        tk.Label(welcome, text="Controla el audio y sigue la actividad del chat en tiempo real.",
                 bg=COLORS["bg"], fg=COLORS["muted"], font=("Segoe UI", 10)).pack(anchor="w", pady=(4, 0))

        stats = tk.Frame(main, bg=COLORS["bg"])
        stats.pack(fill="x", pady=(0, 14))
        self._stat_card(stats, "MENSAJES LEÍDOS", "0", "chat", 0)
        self._stat_card(stats, "PLATAFORMA", self.platform_var.get().replace(" LIVE", ""), "broadcast", 1)
        self._stat_card(stats, "MOTOR DE VOZ", "READY", "audio-lines", 2)

        chat_panel = tk.Frame(main, bg=COLORS["panel"],
                              highlightbackground=COLORS["border"], highlightthickness=1)
        chat_panel.pack(fill="both", expand=True)
        chat_header = tk.Frame(chat_panel, bg=COLORS["panel"], padx=18, pady=14)
        chat_header.pack(fill="x")
        chat_title = tk.Frame(chat_header, bg=COLORS["panel"])
        chat_title.pack(side="left")
        tk.Label(chat_title, text="LIVE CHAT FEED", bg=COLORS["panel"], fg=COLORS["text"],
                 font=("Segoe UI", 12, "bold")).pack(anchor="w")
        tk.Label(chat_title, text="Los mensajes nuevos aparecerán aquí", bg=COLORS["panel"], fg=COLORS["muted"],
                 font=("Segoe UI", 8)).pack(anchor="w", pady=(3, 0))
        self.counter_label = tk.Label(chat_header, text="0 mensajes", bg="#251216", fg="#ff6971",
                                      padx=11, pady=6, font=("Segoe UI", 9, "bold"))
        self.counter_label.pack(side="right")
        tk.Frame(chat_panel, bg=COLORS["border"], height=1).pack(fill="x")

        chat_body = tk.Frame(chat_panel, bg="#0b0b0f", padx=12, pady=12)
        chat_body.pack(fill="both", expand=True)
        self.chat = tk.Text(chat_body, bg="#0b0b0f", fg="#e8e8ee", insertbackground="white",
                            relief="flat", wrap="word", font=("Consolas", 10), padx=10, pady=10,
                            state="disabled", highlightthickness=0, spacing1=3, spacing3=5)
        chat_scroll = ttk.Scrollbar(chat_body, orient="vertical", command=self.chat.yview)
        self.chat.configure(yscrollcommand=chat_scroll.set)
        chat_scroll.pack(side="right", fill="y")
        self.chat.pack(side="left", fill="both", expand=True)
        self.chat.tag_configure("author", foreground="#ff5964", font=("Segoe UI", 10, "bold"))
        self.chat.tag_configure("system", foreground="#8f91a0", font=("Segoe UI", 9, "italic"))
        self.chat.tag_configure("event", foreground="#e8a1ff", font=("Segoe UI", 9, "bold"))

        footer = tk.Frame(main, bg=COLORS["panel"], padx=16, pady=13,
                          highlightbackground=COLORS["border"], highlightthickness=1)
        footer.pack(fill="x", pady=(13, 0))
        self.activity_var = tk.StringVar(value="Listo para conectar.")
        tk.Label(footer, text="●", bg=COLORS["panel"], fg=COLORS["green"],
                 font=("Segoe UI", 13, "bold")).pack(side="left", padx=(0, 9))
        activity_text = tk.Frame(footer, bg=COLORS["panel"])
        activity_text.pack(side="left", fill="x", expand=True)
        tk.Label(activity_text, text="ESTADO DEL SISTEMA", bg=COLORS["panel"], fg=COLORS["muted"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        tk.Label(activity_text, textvariable=self.activity_var, bg=COLORS["panel"], fg=COLORS["text"],
                 anchor="w", justify="left", wraplength=680, font=("Segoe UI", 9)).pack(fill="x", pady=(3, 0))
        self._switch_platform()
        self._toggle_session_fields()

    def _stat_card(self, parent, label, value, symbol, column):
        card = tk.Frame(parent, bg=COLORS["panel"], padx=15, pady=13,
                        highlightbackground=COLORS["border"], highlightthickness=1)
        card.grid(row=0, column=column, sticky="nsew", padx=(0 if column == 0 else 8, 0))
        parent.grid_columnconfigure(column, weight=1, uniform="stats")
        tk.Label(card, text=symbol.upper(), bg=COLORS["panel"], fg=COLORS["red"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        value_label = tk.Label(card, text=value, bg=COLORS["panel"], fg=COLORS["text"],
                               font=("Segoe UI", 16, "bold"))
        value_label.pack(anchor="w", pady=(6, 2))
        tk.Label(card, text=label, bg=COLORS["panel"], fg=COLORS["muted"],
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        if label == "MENSAJES LEÍDOS":
            self.messages_stat_var = value_label
        elif label == "PLATAFORMA":
            self.platform_stat_label = value_label
        elif label == "MOTOR DE VOZ":
            self.voice_stat_label = value_label

    def _switch_platform(self, _event=None):
        if hasattr(self, "platform_stat_label"):
            self.platform_stat_label.configure(text=self.platform_var.get().replace(" LIVE", ""))
        self.youtube_frame.pack_forget()
        self.tiktok_frame.pack_forget()
        if self.platform_var.get() == "YouTube LIVE":
            self.youtube_frame.pack(fill="x")
        else:
            self.tiktok_frame.pack(fill="x")

    def _toggle_session_fields(self):
        self.session_fields.pack_forget()
        if self.use_session_var.get():
            self.session_fields.pack(fill="x", pady=(2, 0))

    def _set_status(self, status, message):
        color = COLORS["green"] if status in ("LISTO", "CONECTADO") else COLORS["red"]
        self.status_badge.configure(text=f"● {status}", fg=color)
        self.activity_var.set(message)
        if hasattr(self, "voice_stat_label"):
            self.voice_stat_label.configure(text="ACTIVE" if status == "CONECTADO" else ("LINKING" if status == "CONECTANDO" else "READY"))

    def _append_chat(self, author, text, system=False):
        self.chat.configure(state="normal")
        if system:
            self.chat.insert("end", f"• {text}\n", "system")
        else:
            self.chat.insert("end", f"{author}: ", "author")
            self.chat.insert("end", f"{text}\n\n")
        self.chat.see("end")
        self.chat.configure(state="disabled")
        if not system:
            try:
                count = int(self.counter_label.cget("text").split()[0]) + 1
            except Exception:
                count = 1
            self.counter_label.configure(text=f"{count} mensajes")
            if hasattr(self, "messages_stat_var"):
                self.messages_stat_var.configure(text=str(count))

    def save_current(self, silent=False):
        self.settings.update({
            "platform": self.platform_var.get(), "api_key": self.api_var.get().strip(),
            "channel_id": self.channel_var.get().strip(), "tiktok_username": self.tiktok_username_var.get().strip(),
            # TikTok session cookies intentionally remain in memory only.
            "tiktok_session_id": "", "tiktok_target_idc": "",
            "use_tiktok_session": self.use_session_var.get(), "voice": self.voice_var.get(),
            "rate": self.rate_var.get(), "read_comments": self.read_comments_var.get(),
            "speak_author": self.speak_author_var.get(), "read_gifts": self.read_gifts_var.get(),
            "read_social_events": self.read_social_var.get(),
            "anti_spam": self.anti_spam_var.get(),
            "max_message_length": self._max_message_length(),
            "blocked_users": self.blocked_users_var.get().strip(),
            "join_alerts_enabled": self.join_alerts_var.get(),
            "join_notifications_enabled": self.join_notifications_var.get(),
            "join_welcome_enabled": self.join_welcome_var.get(),
            "join_welcome_template": self.join_welcome_template_var.get().strip() or "¡Bienvenido al directo, {nombre}!",
            "join_sound_volume": max(0, min(100, int(self.join_volume_var.get()))),
            "subscriber_sound": self.sound_vars["subscriber"].get().strip(),
            "visitor_sound": self.sound_vars["visitor"].get().strip(),
            "unknown_sound": self.sound_vars["unknown"].get().strip(),
        })
        save_settings(self.settings)
        if not silent:
            messagebox.showinfo(APP_NAME, "Configuración guardada localmente en settings.json.")

    def _choose_sound(self, key):
        path = filedialog.askopenfilename(title="Elige un sonido de entrada", filetypes=[("Audio", "*.wav *.mp3 *.ogg"), ("Todos los archivos", "*.*")])
        if path:
            self.sound_vars[key].set(path)
            self.save_current(silent=True)

    def _play_alert_sound(self, key):
        if not self.join_alerts_var.get():
            return
        path = self.sound_vars.get(key).get().strip() if key in self.sound_vars else ""
        if not path or not Path(path).is_file():
            path = str(DEFAULT_SOUND_FILES.get(key, DEFAULT_SOUND_FILES["unknown"]))
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            sound = pygame.mixer.Sound(path)
            sound.set_volume(max(0, min(100, int(self.join_volume_var.get()))) / 100.0)
            sound.play()
        except Exception as exc:
            self._ui(lambda e=str(exc): self._append_chat("", f"No se pudo reproducir el sonido de entrada: {e[:150]}", system=True))

    def _preview_sound(self, key):
        self.save_current(silent=True)
        threading.Thread(target=self._play_alert_sound, args=(key,), daemon=True).start()

    def _handle_join(self, user, event=None):
        if self.stop_event.is_set():
            return
        username = str(getattr(user, "unique_id", None) or getattr(user, "nickname", None) or "Usuario").strip()
        display_name = str(getattr(user, "nickname", None) or username).strip()
        now = time.monotonic()
        join_key = username.casefold()
        if now - self.recent_joins.get(join_key, -1000) < 30:
            return
        self.recent_joins[join_key] = now
        # Only classify membership when the event explicitly exposes a boolean field.
        status = None
        for attr in ("is_subscriber", "is_subscribed", "subscribed"):
            value = getattr(user, attr, None)
            if isinstance(value, bool):
                status = value
                break
        sound_key = "subscriber" if status is True else ("visitor" if status is False else "unknown")
        if self.join_notifications_var.get():
            label = "suscriptor confirmado" if status is True else ("no suscrito confirmado" if status is False else "estado de suscripción sin verificar")
            self._ui(lambda n=display_name, l=label: self._append_chat(n, f"se unió al directo ({l}) [ENTRADA]"))
        threading.Thread(target=self._play_alert_sound, args=(sound_key,), daemon=True).start()
        if self.join_welcome_var.get():
            template = self.join_welcome_template_var.get().strip() or "¡Bienvenido al directo, {nombre}!"
            # Treat the template as plain text and replace only the supported placeholder.
            welcome = template.replace("{nombre}", display_name).replace("{name}", display_name).strip()
            if welcome:
                # Keep entry announcements near the front when chat traffic is busy.
                try:
                    while self.audio_queue.qsize() >= 8:
                        self.audio_queue.get_nowait()
                        self.audio_queue.task_done()
                except queue.Empty:
                    pass
                self.audio_queue.put((welcome, self.voice_var.get(), self.rate_var.get()))

    def test_voice(self):
        self.save_current(silent=True)
        self.audio_queue.put(("Moorttys Voice está listo para leer tu chat.", self.voice_var.get(), self.rate_var.get()))
        self._set_status("LISTO", "Prueba de voz enviada a la cola de audio.")

    def start_reader(self):
        if self.running:
            return
        self.save_current(silent=True)
        if not self.read_comments_var.get() and not (self.platform_var.get() == "TikTok LIVE" and (self.read_gifts_var.get() or self.read_social_var.get() or self.join_alerts_var.get() or self.join_notifications_var.get())):
            messagebox.showwarning(APP_NAME, "Activa al menos un tipo de evento para leer.")
            return
        self.stop_event.clear()
        self.reader_started_at = time.time()
        self.recent_messages.clear()
        self.seen_ids.clear()
        # Start clean: remove pending audio from before this reading session.
        self._clear_audio_queue()
        self.running = True
        self.start_btn.configure(state="disabled")
        if self.platform_var.get() == "YouTube LIVE":
            if not self.api_var.get().strip() or not self.channel_var.get().strip():
                self.running = False
                self.start_btn.configure(state="normal")
                messagebox.showwarning(APP_NAME, "Introduce tu YouTube API key y el ID del canal.")
                return
            target = self._poll_loop
            self._set_status("CONECTANDO", "Buscando un directo público activo de YouTube…")
        else:
            if not self.tiktok_username_var.get().strip():
                self.running = False
                self.start_btn.configure(state="normal")
                messagebox.showwarning(APP_NAME, "Introduce el @usuario que está transmitiendo en TikTok LIVE.")
                return
            if self.use_session_var.get() and (not self.tiktok_session_var.get().strip() or not self.tiktok_target_var.get().strip()):
                self.running = False
                self.start_btn.configure(state="normal")
                messagebox.showwarning(APP_NAME, "Para usar sesión avanzada debes introducir ambas cookies. Para directos públicos, desactiva esa opción.")
                return
            if self.use_session_var.get():
                confirmed = messagebox.askyesno(
                    APP_NAME,
                    "La conexión avanzada usará cookies de sesión sensibles y la biblioteca puede enviarlas al proveedor externo de firma Euler Stream para conectar con TikTok. No es un inicio de sesión oficial.\n\n¿Confías en ese proveedor y quieres continuar?"
                )
                if not confirmed:
                    self.running = False
                    self.start_btn.configure(state="normal")
                    return
            target = self._tiktok_loop
            self._set_status("CONECTANDO", "Intentando conectar con TikTok LIVE…")
        self._append_chat("", "Iniciando conexión…", system=True)
        self.poll_thread = threading.Thread(target=target, daemon=True)
        self.poll_thread.start()

    def stop_reader(self):
        self.stop_event.set()
        self._disconnect_tiktok()
        self.running = False
        self.start_btn.configure(state="normal")
        self._set_status("LISTO", "Lector detenido.")
        self._append_chat("", "Solicitud de detener el lector enviada.", system=True)

    def _poll_loop(self):
        try:
            youtube = build("youtube", "v3", developerKey=self.api_var.get().strip(), cache_discovery=False)
            self.live_chat_id = self._find_live_chat(youtube)
            if not self.live_chat_id:
                self._ui(lambda: self._set_status("SIN DIRECTO", "No se encontró un directo público activo con chat habilitado."))
                self._ui(lambda: self._append_chat("", "No se encontró un directo activo con chat habilitado.", system=True))
                return
            self._ui(lambda: self._set_status("CONECTADO", "YouTube conectado. Esperando comentarios…"))
            self._ui(lambda: self._append_chat("", "Conectado al chat del directo de YouTube.", system=True))
            page_token = None
            while not self.stop_event.is_set():
                response = youtube.liveChatMessages().list(liveChatId=self.live_chat_id, part="snippet,authorDetails",
                                                           pageToken=page_token, maxResults=200).execute()
                page_token = response.get("nextPageToken", page_token)
                for item in response.get("items", []):
                    if self.stop_event.is_set():
                        break
                    msg_id = item.get("id")
                    if msg_id and msg_id in self.seen_ids:
                        continue
                    if msg_id:
                        self.seen_ids.add(msg_id)
                    snippet = item.get("snippet", {})
                    published = snippet.get("publishedAt", "")
                    # YouTube may return chat history on the first page; skip anything
                    # published before this reader session started.
                    if published:
                        try:
                            from datetime import datetime
                            published_ts = datetime.fromisoformat(published.replace("Z", "+00:00")).timestamp()
                            if published_ts < self.reader_started_at:
                                continue
                        except (ValueError, TypeError):
                            pass
                    author = item.get("authorDetails", {}).get("displayName", "Usuario")
                    text = snippet.get("displayMessage", "")
                    if text:
                        self._handle_message(author, text)
                self.stop_event.wait(max(1.0, response.get("pollingIntervalMillis", 5000) / 1000.0))
        except HttpError as exc:
            details = str(exc)
            self._ui(lambda: self._set_status("ERROR", "Error de YouTube API. Revisa API key, cuota y chat."))
            self._ui(lambda d=details: self._append_chat("", f"Error de YouTube API: {d[:350]}", system=True))
        except Exception as exc:
            details = str(exc)
            self._ui(lambda: self._set_status("ERROR", "No se pudo conectar con YouTube."))
            self._ui(lambda d=details: self._append_chat("", f"Error: {d[:350]}", system=True))
        finally:
            self.running = False
            self._ui(lambda: self.start_btn.configure(state="normal"))

    def _find_live_chat(self, youtube):
        response = youtube.search().list(part="id,snippet", channelId=self.channel_var.get().strip(),
                                         type="video", eventType="live", maxResults=10).execute()
        for item in response.get("items", []):
            video_id = item.get("id", {}).get("videoId")
            if not video_id:
                continue
            video = youtube.videos().list(part="liveStreamingDetails", id=video_id).execute()
            for v in video.get("items", []):
                live_id = v.get("liveStreamingDetails", {}).get("activeLiveChatId")
                if live_id:
                    return live_id
        return None

    def _tiktok_loop(self):
        try:
            from TikTokLive import TikTokLiveClient
            from TikTokLive.events import CommentEvent, GiftEvent, FollowEvent, ShareEvent, JoinEvent

            username = self.tiktok_username_var.get().strip()
            if username.startswith("https://www.tiktok.com/@"):
                username = username.split("@", 1)[1].split("/", 1)[0]
            username = username.lstrip("@")
            client = TikTokLiveClient(unique_id=username)
            self.tiktok_client = client
            if self.use_session_var.get():
                # Explicitly allow the documented signing host only after user confirmation.
                os.environ["WHITELIST_AUTHENTICATED_SESSION_ID_HOST"] = "api.eulerstream.com"
                client.web.set_session(self.tiktok_session_var.get().strip(), self.tiktok_target_var.get().strip())

            @client.on(JoinEvent)
            async def on_join(event):
                if self.stop_event.is_set():
                    return
                user = getattr(event, "user", None)
                if user is not None:
                    self._handle_join(user, event)

            @client.on(CommentEvent)
            async def on_comment(event):
                if self.stop_event.is_set() or not self.read_comments_var.get():
                    return
                user = getattr(event, "user", None)
                author = getattr(user, "nickname", None) or getattr(user, "unique_id", None) or "Usuario"
                text = getattr(event, "comment", None) or getattr(event, "content", None) or ""
                if text:
                    self._handle_message(author, text)

            @client.on(GiftEvent)
            async def on_gift(event):
                if self.stop_event.is_set() or not self.read_gifts_var.get():
                    return
                user = getattr(event, "user", None)
                author = getattr(user, "nickname", None) or "Alguien"
                gift = getattr(event, "gift", None)
                gift_name = getattr(gift, "name", None) or "regalo"
                count = getattr(event, "repeat_count", 1) or 1
                text = f"envió {count} {gift_name}"
                self._handle_message(author, text, event_type="REGALO")

            @client.on(FollowEvent)
            async def on_follow(event):
                if self.stop_event.is_set() or not self.read_social_var.get():
                    return
                user = getattr(event, "user", None)
                author = getattr(user, "nickname", None) or "Alguien"
                self._handle_message(author, "ahora te sigue", event_type="FOLLOW")

            @client.on(ShareEvent)
            async def on_share(event):
                if self.stop_event.is_set() or not self.read_social_var.get():
                    return
                user = getattr(event, "user", None)
                author = getattr(user, "nickname", None) or "Alguien"
                self._handle_message(author, "compartió el directo", event_type="COMPARTIDO")

            self._ui(lambda: self._set_status("CONECTANDO", f"Conectando con el LIVE de @{username}…"))
            self._ui(lambda: self._append_chat("", f"Buscando el directo público de @{username}…", system=True))
            asyncio.run(self._run_tiktok_client(client))
        except Exception as exc:
            details = str(exc)
            self._ui(lambda: self._set_status("ERROR", "TikTok no pudo conectar. Confirma que el usuario esté LIVE y revisa internet."))
            self._ui(lambda d=details: self._append_chat("", f"Error de TikTok: {d[:400]}", system=True))
        finally:
            self.tiktok_client = None
            self.tiktok_loop = None
            self.running = False
            self._ui(lambda: self.start_btn.configure(state="normal"))

    async def _run_tiktok_client(self, client):
        self.tiktok_loop = asyncio.get_running_loop()
        self._ui(lambda: self._set_status("CONECTANDO", "Abriendo conexión con TikTok LIVE…"))
        self._ui(lambda: self._append_chat("", "Solicitando conexión a TikTok LIVE…", system=True))
        if self.stop_event.is_set():
            return
        await client.connect()

    def _disconnect_tiktok(self):
        client = self.tiktok_client
        loop = self.tiktok_loop
        if client is not None and loop is not None and loop.is_running():
            try:
                loop.call_soon_threadsafe(lambda: asyncio.create_task(client.disconnect()))
            except Exception:
                pass

    def _max_message_length(self):
        try:
            return max(20, min(1000, int(self.max_length_var.get())))
        except (ValueError, AttributeError):
            return 220

    def _clear_audio_queue(self):
        try:
            while True:
                self.audio_queue.get_nowait()
                self.audio_queue.task_done()
        except queue.Empty:
            pass

    def _handle_message(self, author, text, event_type="COMENTARIO"):
        author = str(author or "Usuario").strip()
        text = " ".join(str(text or "").split()).strip()
        if not text:
            return
        blocked = {u.strip().casefold().lstrip("@") for u in self.blocked_users_var.get().split(",") if u.strip()}
        if author.casefold().lstrip("@") in blocked:
            return
        max_len = self._max_message_length()
        if len(text) > max_len:
            text = text[:max_len].rstrip() + "…"
        now = time.monotonic()
        key = (author.casefold(), text.casefold(), event_type)
        if self.anti_spam_var.get():
            if any(old_key == key and now - old_time < 20 for old_time, old_key in self.recent_messages):
                return
            self.recent_messages.append((now, key))
        self._ui(lambda a=author, t=text, et=event_type: self._append_chat(a, f"[{et}] {t}" if et != "COMENTARIO" else t))
        spoken = f"{author} dice: {text}" if self.speak_author_var.get() else text
        # Smart queue: when overloaded, discard the oldest pending items and keep recent chat.
        try:
            while self.audio_queue.qsize() >= 8:
                self.audio_queue.get_nowait()
                self.audio_queue.task_done()
        except queue.Empty:
            pass
        self.audio_queue.put((spoken, self.voice_var.get(), self.rate_var.get()))

    def _ui(self, callback):
        try:
            self.root.after(0, callback)
        except tk.TclError:
            pass

    def _start_audio_worker(self):
        threading.Thread(target=self._audio_loop, daemon=True).start()

    def _audio_loop(self):
        while True:
            item = self.audio_queue.get()
            if item is None:
                return
            text, voice, rate = item
            try:
                asyncio.run(self._speak(text, voice, rate))
            except Exception as exc:
                self._ui(lambda e=str(exc): self._append_chat("", f"No se pudo reproducir voz: {e[:180]}", system=True))

    async def _speak(self, text, voice, rate):
        communicate = edge_tts.Communicate(text, voice=voice, rate=rate)
        await communicate.save(str(AUDIO_PATH))
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        pygame.mixer.music.load(str(AUDIO_PATH))
        pygame.mixer.music.play()
        while pygame.mixer.music.get_busy():
            await asyncio.sleep(0.1)
        pygame.mixer.music.unload()

    def close(self):
        self.stop_event.set()
        self._disconnect_tiktok()
        self.audio_queue.put(None)
        try:
            pygame.mixer.quit()
        except Exception:
            pass
        self.root.destroy()


def main():
    root = tk.Tk()
    MoorttysVoiceApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
