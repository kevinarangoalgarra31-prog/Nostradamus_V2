"""
GUI Nostradamus -- Interfaz premium con customtkinter
=====================================================
Panel de control con log en tiempo real, indicadores de pasos,
y visualizacion JSON del estado final.
"""
import asyncio
import json
import logging
import threading
import tkinter as tk
from datetime import datetime, timezone

import customtkinter as ctk

from ..pipeline import run_pipeline

# -- Configuracion de tema ---------------------------------------------
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Paleta de colores premium
COLORS = {
    "bg_dark": "#0a0e17",
    "bg_card": "#111827",
    "bg_card_alt": "#1a2332",
    "border": "#1e293b",
    "accent_blue": "#3b82f6",
    "accent_cyan": "#06b6d4",
    "accent_purple": "#8b5cf6",
    "accent_green": "#10b981",
    "accent_yellow": "#f59e0b",
    "accent_red": "#ef4444",
    "text_primary": "#f1f5f9",
    "text_secondary": "#94a3b8",
    "text_muted": "#64748b",
    "success": "#10b981",
    "warning": "#f59e0b",
    "error": "#ef4444",
    "info": "#94a3b8",
}

STEP_LABELS = {
    1: "Stock Selector",
    2: "Tavily Search",
    3: "Groq Analysis",
    4: "Risk & Execution",
}

STEP_ICONS = {
    "pending": "[.]",
    "running": "[~]",
    "completed": "[+]",
    "failed": "[X]",
    "skipped": "[-]",
}

LOG_COLORS = {
    "INFO": COLORS["text_secondary"],
    "SUCCESS": COLORS["accent_green"],
    "WARNING": COLORS["accent_yellow"],
    "ERROR": COLORS["accent_red"],
    "DEBUG": COLORS["text_muted"],
}


class NostradamusApp(ctk.CTk):
    """Aplicacion principal de Nostradamus."""

    def __init__(self):
        super().__init__()

        self.title("NOSTRADAMUS v1.1 -- AI Trading Pipeline")
        self.geometry("1100x780")
        self.minsize(900, 650)
        self.configure(fg_color=COLORS["bg_dark"])

        self._running = False
        self._step_labels: dict[int, ctk.CTkLabel] = {}
        self._step_status_labels: dict[int, ctk.CTkLabel] = {}
        self._log_count = 0

        self._build_ui()

    # -- UI Construction -----------------------------------------------

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._build_header()
        self._build_steps_panel()
        self._build_main_area()
        self._build_footer()

    def _build_header(self):
        header = ctk.CTkFrame(self, fg_color=COLORS["bg_card"], corner_radius=0, height=70)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_columnconfigure(1, weight=1)
        header.grid_propagate(False)

        title_frame = ctk.CTkFrame(header, fg_color="transparent")
        title_frame.grid(row=0, column=0, padx=20, pady=15, sticky="w")

        ctk.CTkLabel(
            title_frame, text="NOSTRADAMUS",
            font=ctk.CTkFont(family="Consolas", size=22, weight="bold"),
            text_color=COLORS["accent_cyan"],
        ).pack(side="left")

        ctk.CTkLabel(
            title_frame, text="  v1.1",
            font=ctk.CTkFont(family="Consolas", size=14),
            text_color=COLORS["text_muted"],
        ).pack(side="left", padx=(2, 0))

        ctk.CTkLabel(
            title_frame, text="  |  AI Trading Pipeline",
            font=ctk.CTkFont(family="Consolas", size=13),
            text_color=COLORS["text_secondary"],
        ).pack(side="left")

        self._btn_start = ctk.CTkButton(
            header, text=">  Iniciar Simulacion",
            font=ctk.CTkFont(family="Consolas", size=14, weight="bold"),
            fg_color=COLORS["accent_blue"],
            hover_color=COLORS["accent_purple"],
            corner_radius=8, height=38, width=200,
            command=self._on_start_click,
        )
        self._btn_start.grid(row=0, column=1, padx=20, pady=15, sticky="e")

    def _build_steps_panel(self):
        panel = ctk.CTkFrame(self, fg_color=COLORS["bg_card_alt"], corner_radius=0, height=60)
        panel.grid(row=1, column=0, sticky="ew", pady=(1, 0))
        panel.grid_propagate(False)

        for i in range(4):
            panel.grid_columnconfigure(i, weight=1)

        for step_num in range(1, 5):
            frame = ctk.CTkFrame(panel, fg_color="transparent")
            frame.grid(row=0, column=step_num - 1, padx=10, pady=10, sticky="ew")

            icon_label = ctk.CTkLabel(
                frame,
                text=f"{STEP_ICONS['pending']}  Paso {step_num}: {STEP_LABELS[step_num]}",
                font=ctk.CTkFont(family="Consolas", size=12),
                text_color=COLORS["text_muted"],
            )
            icon_label.pack(anchor="center")

            status_label = ctk.CTkLabel(
                frame, text="Pendiente",
                font=ctk.CTkFont(family="Consolas", size=10),
                text_color=COLORS["text_muted"],
            )
            status_label.pack(anchor="center")

            self._step_labels[step_num] = icon_label
            self._step_status_labels[step_num] = status_label

    def _build_main_area(self):
        main = ctk.CTkFrame(self, fg_color=COLORS["bg_dark"], corner_radius=0)
        main.grid(row=2, column=0, sticky="nsew", padx=0, pady=0)
        main.grid_columnconfigure(0, weight=3)
        main.grid_columnconfigure(1, weight=2)
        main.grid_rowconfigure(0, weight=1)

        # Left: Log panel
        log_frame = ctk.CTkFrame(main, fg_color=COLORS["bg_card"], corner_radius=10)
        log_frame.grid(row=0, column=0, sticky="nsew", padx=(12, 6), pady=12)
        log_frame.grid_rowconfigure(1, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            log_frame, text="[LOG] Tiempo Real",
            font=ctk.CTkFont(family="Consolas", size=13, weight="bold"),
            text_color=COLORS["text_primary"],
        ).grid(row=0, column=0, padx=15, pady=(12, 5), sticky="w")

        self._log_text = tk.Text(
            log_frame, bg=COLORS["bg_dark"], fg=COLORS["text_secondary"],
            font=("Consolas", 11), relief="flat", borderwidth=0,
            wrap="word", padx=12, pady=8, insertbackground=COLORS["text_primary"],
            selectbackground=COLORS["accent_blue"],
        )
        self._log_text.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self._log_text.configure(state="disabled")

        for level, color in LOG_COLORS.items():
            self._log_text.tag_configure(level, foreground=color)
        self._log_text.tag_configure(
            "HEADER", foreground=COLORS["accent_cyan"],
            font=("Consolas", 11, "bold"),
        )

        scrollbar = ctk.CTkScrollbar(log_frame, command=self._log_text.yview)
        scrollbar.grid(row=1, column=1, sticky="ns", pady=(0, 8), padx=(0, 4))
        self._log_text.configure(yscrollcommand=scrollbar.set)

        # Right: JSON panel
        json_frame = ctk.CTkFrame(main, fg_color=COLORS["bg_card"], corner_radius=10)
        json_frame.grid(row=0, column=1, sticky="nsew", padx=(6, 12), pady=12)
        json_frame.grid_rowconfigure(1, weight=1)
        json_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            json_frame, text="[JSON] Estado Final",
            font=ctk.CTkFont(family="Consolas", size=13, weight="bold"),
            text_color=COLORS["text_primary"],
        ).grid(row=0, column=0, padx=15, pady=(12, 5), sticky="w")

        self._json_text = tk.Text(
            json_frame, bg=COLORS["bg_dark"], fg=COLORS["accent_cyan"],
            font=("Consolas", 10), relief="flat", borderwidth=0,
            wrap="word", padx=12, pady=8, insertbackground=COLORS["text_primary"],
            selectbackground=COLORS["accent_blue"],
        )
        self._json_text.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 8))
        self._json_text.configure(state="disabled")

        self._json_text.tag_configure("key", foreground=COLORS["accent_purple"])
        self._json_text.tag_configure("string", foreground=COLORS["accent_green"])
        self._json_text.tag_configure("number", foreground=COLORS["accent_yellow"])
        self._json_text.tag_configure("bool", foreground=COLORS["accent_red"])
        self._json_text.tag_configure("null", foreground=COLORS["text_muted"])

        json_scroll = ctk.CTkScrollbar(json_frame, command=self._json_text.yview)
        json_scroll.grid(row=1, column=1, sticky="ns", pady=(0, 8), padx=(0, 4))
        self._json_text.configure(yscrollcommand=json_scroll.set)

    def _build_footer(self):
        footer = ctk.CTkFrame(self, fg_color=COLORS["bg_card"], corner_radius=0, height=32)
        footer.grid(row=3, column=0, sticky="ew")
        footer.grid_propagate(False)
        footer.grid_columnconfigure(0, weight=1)

        self._status_label = ctk.CTkLabel(
            footer, text="[||] Esperando inicio de simulacion...",
            font=ctk.CTkFont(family="Consolas", size=11),
            text_color=COLORS["text_muted"],
        )
        self._status_label.grid(row=0, column=0, padx=15, sticky="w")

    # -- Event Handlers ------------------------------------------------

    def _on_start_click(self):
        if self._running:
            return
        self._running = True
        self._btn_start.configure(
            state="disabled", text="[~] Ejecutando...",
            fg_color=COLORS["text_muted"],
        )
        self._reset_ui()
        self._status_label.configure(
            text="[~] Pipeline en ejecucion...",
            text_color=COLORS["accent_cyan"],
        )

        thread = threading.Thread(target=self._run_async_pipeline, daemon=True)
        thread.start()

    def _reset_ui(self):
        self._log_text.configure(state="normal")
        self._log_text.delete("1.0", "end")
        self._log_text.configure(state="disabled")
        self._log_count = 0

        self._json_text.configure(state="normal")
        self._json_text.delete("1.0", "end")
        self._json_text.configure(state="disabled")

        for step_num in range(1, 5):
            self._update_step_indicator(step_num, "pending")

    def _run_async_pipeline(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                run_pipeline(on_log=self._gui_log, on_step=self._gui_step)
            )
            self.after(0, lambda: self._on_pipeline_complete(result))
        except Exception as e:
            self.after(0, lambda: self._gui_log(f"[FATAL] Error fatal: {e}", "ERROR"))
            self.after(0, lambda: self._on_pipeline_complete(None))
        finally:
            loop.close()

    def _on_pipeline_complete(self, result):
        self._running = False
        self._btn_start.configure(
            state="normal", text=">  Iniciar Simulacion",
            fg_color=COLORS["accent_blue"],
        )

        if result:
            self._display_json(result)
            estado_ej = result.get("ejecucion", {}).get("estado", "")
            decision = result.get("ejecucion", {}).get("decision", "N/A")
            if estado_ej == "completado":
                self._status_label.configure(
                    text=f"[+] Pipeline completado -- Decision: {decision}",
                    text_color=COLORS["accent_green"],
                )
            else:
                self._status_label.configure(
                    text=f"[WARN] Pipeline completado -- Decision: {decision}",
                    text_color=COLORS["accent_yellow"],
                )
        else:
            self._status_label.configure(
                text="[STOP] Pipeline abortado -- ver log para detalles",
                text_color=COLORS["accent_red"],
            )

    # -- GUI Callbacks (thread-safe via after()) -----------------------

    def _gui_log(self, msg: str, level: str = "INFO"):
        self.after(0, lambda: self._append_log(msg, level))

    def _gui_step(self, step_num: int, status: str):
        self.after(0, lambda: self._update_step_indicator(step_num, status))

    def _append_log(self, msg: str, level: str):
        self._log_text.configure(state="normal")

        timestamp = datetime.now().strftime("%H:%M:%S")
        self._log_count += 1

        tag = level if level in LOG_COLORS else "INFO"
        if msg.startswith("=") or msg.startswith("-" * 10):
            tag = "HEADER"

        prefix = f"[{timestamp}] "
        self._log_text.insert("end", prefix, "HEADER")
        self._log_text.insert("end", msg + "\n", tag)
        self._log_text.see("end")
        self._log_text.configure(state="disabled")

    def _update_step_indicator(self, step_num: int, status: str):
        icon = STEP_ICONS.get(status, "[?]")
        label = self._step_labels.get(step_num)
        status_label = self._step_status_labels.get(step_num)

        if not label or not status_label:
            return

        label.configure(text=f"{icon}  Paso {step_num}: {STEP_LABELS[step_num]}")

        status_map = {
            "pending": ("Pendiente", COLORS["text_muted"]),
            "running": ("Ejecutando...", COLORS["accent_cyan"]),
            "completed": ("Completado", COLORS["accent_green"]),
            "failed": ("Fallido", COLORS["accent_red"]),
            "skipped": ("Omitido", COLORS["text_muted"]),
        }
        text, color = status_map.get(status, ("--", COLORS["text_muted"]))
        status_label.configure(text=text, text_color=color)
        label.configure(text_color=color)

    def _display_json(self, data: dict):
        """Muestra JSON con syntax highlighting basico."""
        self._json_text.configure(state="normal")
        self._json_text.delete("1.0", "end")

        formatted = json.dumps(data, indent=2, ensure_ascii=False, default=str)

        for line in formatted.split("\n"):
            if '": ' in line or '":' in line:
                parts = line.split(":", 1)
                self._json_text.insert("end", parts[0] + ":", "key")
                if len(parts) > 1:
                    val = parts[1].strip().rstrip(",")
                    if val.startswith('"'):
                        tag = "string"
                    elif val in ("true", "false"):
                        tag = "bool"
                    elif val == "null":
                        tag = "null"
                    else:
                        try:
                            float(val)
                            tag = "number"
                        except ValueError:
                            tag = "string"
                    self._json_text.insert("end", " " + parts[1], tag)
                self._json_text.insert("end", "\n")
            else:
                self._json_text.insert("end", line + "\n", "key")

        self._json_text.configure(state="disabled")


def launch_app():
    """Punto de entrada para lanzar la GUI."""
    app = NostradamusApp()
    app.mainloop()
