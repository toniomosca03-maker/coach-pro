#!/usr/bin/env python3
"""
main.py — Scacchiera Mondiale: Generatore Video Geopolitici
Applicazione desktop Tkinter per creare video MP4 con mappe animate.

Avvio:
    python main.py

Dipendenze:
    pip install -r requirements.txt
"""
from __future__ import annotations

import json
import os
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Optional

# Aggiunge la root del progetto al PYTHONPATH
_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.scene_parser import SceneParser, SceneParserError
from src.video_generator import VideoGenerator


# ---------------------------------------------------------------------------
# Colori tema Scacchiera Mondiale
# ---------------------------------------------------------------------------
BG_DARK    = "#1a1a2e"
BG_CARD    = "#16213e"
BG_DEEP    = "#0f3460"
BG_INPUT   = "#111122"
ACCENT_GOLD = "#e2b96f"
ACCENT_RED  = "#e74c3c"
ACCENT_BLUE = "#2980b9"
ACCENT_GRN  = "#27ae60"
ACCENT_PURP = "#6c3483"
TEXT_MAIN   = "#e8e8f0"
TEXT_DIM    = "#8888aa"
TEXT_GREEN  = "#00e87a"


# ---------------------------------------------------------------------------
# Widget ausiliari
# ---------------------------------------------------------------------------

class _HoverButton(tk.Button):
    """Pulsante con effetto hover colore."""

    def __init__(self, master, hover_bg: str, normal_bg: str, **kw):
        super().__init__(master, bg=normal_bg, **kw)
        self._normal = normal_bg
        self._hover = hover_bg
        self.bind("<Enter>", lambda _: self.config(bg=self._hover))
        self.bind("<Leave>", lambda _: self.config(bg=self._normal))


class _ScrolledText(tk.Frame):
    """Text widget con scrollbar verticale integrata."""

    def __init__(self, master, **kw):
        super().__init__(master, bg=kw.pop("bg", BG_INPUT))
        self.text = tk.Text(self, **kw)
        sb = ttk.Scrollbar(self, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=sb.set)
        self.text.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

    def set_content(self, content: str) -> None:
        self.text.config(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("end", content)
        self.text.config(state="disabled")


# ---------------------------------------------------------------------------
# Finestra anteprima
# ---------------------------------------------------------------------------

class _PreviewWindow(tk.Toplevel):
    def __init__(self, master, project: dict, scene_idx: int = 0) -> None:
        super().__init__(master)
        self.title("Anteprima Scena")
        self.configure(bg=BG_DARK)

        scenes = project.get("scene", [])
        if not scenes:
            self.destroy()
            return

        self._project = project
        self._scenes = scenes
        self._scene_idx = scene_idx
        self._loading = False

        # Selettore scena
        top = tk.Frame(self, bg=BG_DARK)
        top.pack(fill="x", padx=10, pady=8)

        tk.Label(top, text="Scena:", bg=BG_DARK, fg=TEXT_DIM,
                 font=("Arial", 11)).pack(side="left")

        self._scene_var = tk.IntVar(value=scene_idx + 1)
        for i in range(len(scenes)):
            rb = tk.Radiobutton(
                top,
                text=str(i + 1),
                variable=self._scene_var,
                value=i + 1,
                command=self._refresh,
                bg=BG_DARK, fg=TEXT_MAIN,
                selectcolor=BG_DEEP,
                activebackground=BG_DARK,
            )
            rb.pack(side="left", padx=3)

        # Canvas immagine
        preview_w, preview_h = 960, 540
        self._canvas = tk.Canvas(self, width=preview_w, height=preview_h,
                                 bg=BG_DEEP, highlightthickness=0)
        self._canvas.pack(padx=10, pady=(0, 10))

        self._tk_img = None
        self._loading_label = tk.Label(
            self, text="Caricamento in corso…",
            bg=BG_DARK, fg=ACCENT_GOLD, font=("Arial", 14),
        )

        self._refresh()

    def _refresh(self) -> None:
        if self._loading:
            return
        self._loading = True
        idx = self._scene_var.get() - 1
        self._scene_idx = idx
        self._loading_label.place(x=380, y=250)
        threading.Thread(target=self._render_thread, daemon=True).start()

    def _render_thread(self) -> None:
        try:
            from src.map_renderer import MapRenderer
            from PIL import ImageTk, Image

            meta = self._project.get("metadata", {})
            # Forza risoluzione ridotta per l'anteprima
            meta_preview = dict(meta)
            meta_preview["risoluzione"] = "960x540"

            renderer = MapRenderer(meta_preview)
            scene = self._scenes[self._scene_idx]
            img = renderer.render_preview(scene)

            tk_img = ImageTk.PhotoImage(img)
            self.after(0, self._show_image, tk_img)
        except Exception as exc:
            self.after(0, lambda: messagebox.showerror(
                "Errore anteprima", str(exc), parent=self
            ))
        finally:
            self._loading = False

    def _show_image(self, tk_img) -> None:
        self._tk_img = tk_img  # mantieni riferimento
        self._canvas.delete("all")
        self._canvas.create_image(480, 270, image=tk_img)
        self._loading_label.place_forget()


# ---------------------------------------------------------------------------
# Finestra Guida JSON
# ---------------------------------------------------------------------------

_GUIDA_TESTO = """\
GUIDA AL FORMATO JSON — Scacchiera Mondiale
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STRUTTURA:
{
  "metadata": { ... },   ← info del video
  "scene":    [ ... ]    ← lista delle scene
}

METADATA:
  titolo      : Titolo del video (string)
  canale      : Es. "Scacchiera Mondiale"
  risoluzione : "1920x1080" oppure "1280x720"
  fps         : 24, 30 o 60
  tema        : "scuro" oppure "chiaro"

SCENE – ogni scena ha:
  id          : numero progressivo
  durata      : durata in secondi (es. 8)
  titolo      : testo del titolo
  sottotitolo : testo sottotitolo
  mappa       : configurazione mappa
  paesi       : lista paesi da colorare
  frecce      : frecce animate
  icone       : icone sulla mappa
  testo_overlay : testi aggiuntivi
  transizione : tipo di transizione

MAPPA:
  centro  : {"lat": 50, "lon": 15}
  zoom    : 1=mondo, 3=continente, 6=paese
  sfondo  : colore hex es. "#1a1a2e"
  oceani  : colore hex es. "#0f3460"

PAESI:
  nome        : nome inglese (es. "Ukraine")
  colore      : hex es. "#e74c3c"
  opacita     : 0.0–1.0
  etichetta   : testo sovrapposto
  animazione  : "fade_in" | "nessuna" | "pulse"

FRECCE:
  da      : {"lat": X, "lon": Y}
  a       : {"lat": X, "lon": Y}
  colore  : hex
  spessore: 1–10
  etichetta: testo sulla freccia
  stile   : "solido" | "tratteggiato" | "punteggiato"

ICONE (tipi):
  "base_militare"  — stella arancione
  "zona_conflitto" — X rossa
  "risorsa"        — diamante giallo
  "porto"          — ancora blu
  "capitale"       — cerchio bianco
  "aeroporto"      — croce viola

TRANSIZIONI:
  tipo   : "fade" | "nessuna"
  durata : secondi (es. 0.5)

TESTO OVERLAY:
  testo      : testo da mostrare
  posizione  : "alto" | "centro" | "basso"
  dimensione : grandezza font (es. 32)
  colore     : hex
  sfondo     : hex (opzionale, riquadro sfondo)

COLORI GEOPOLITICI CONSIGLIATI:
  Aggressione  : "#e74c3c"
  Tensione     : "#e67e22"
  Alleato NATO : "#2980b9"
  Neutrale     : "#7f8c8d"
  Verde alleato: "#27ae60"
  Risorsa      : "#f1c40f"
  Occupazione  : "#8e44ad"
"""


class _HelpWindow(tk.Toplevel):
    def __init__(self, master) -> None:
        super().__init__(master)
        self.title("Guida al formato JSON")
        self.geometry("720x640")
        self.configure(bg=BG_DARK)

        frame = tk.Frame(self, bg=BG_DARK)
        frame.pack(fill="both", expand=True, padx=10, pady=10)

        txt = _ScrolledText(
            frame,
            bg=BG_INPUT, fg=TEXT_MAIN,
            font=("Courier", 10), wrap="word",
            state="normal", padx=12, pady=12,
            relief="flat",
        )
        txt.pack(fill="both", expand=True)
        txt.set_content(_GUIDA_TESTO)


# ---------------------------------------------------------------------------
# Applicazione principale
# ---------------------------------------------------------------------------

class ScacchieraMondiale(tk.Tk):
    """Finestra principale dell'applicazione."""

    def __init__(self) -> None:
        super().__init__()
        self.title("Scacchiera Mondiale — Generatore Video Geopolitici")
        self.geometry("960x780")
        self.minsize(760, 620)
        self.configure(bg=BG_DARK)

        self._project: Optional[dict] = None
        self._generating = False

        self._setup_styles()
        self._build_ui()

    # ------------------------------------------------------------------ #
    #  Stili ttk                                                           #
    # ------------------------------------------------------------------ #

    def _setup_styles(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TProgressbar",
                         troughcolor=BG_CARD,
                         background=ACCENT_GOLD,
                         bordercolor=BG_CARD,
                         lightcolor=ACCENT_GOLD,
                         darkcolor=ACCENT_GOLD)

    # ------------------------------------------------------------------ #
    #  Costruzione UI                                                      #
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        self._build_header()
        self._build_file_section()
        self._build_info_section()
        self._build_output_section()
        self._build_progress_section()
        self._build_buttons()

    def _build_header(self) -> None:
        hdr = tk.Frame(self, bg=BG_DEEP, height=80)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        tk.Label(
            hdr, text="\u265f  SCACCHIERA MONDIALE",
            font=("Arial", 22, "bold"),
            fg=ACCENT_GOLD, bg=BG_DEEP,
        ).pack(pady=(12, 0))
        tk.Label(
            hdr, text="Generatore Video Geopolitici con Mappe Animate",
            font=("Arial", 11), fg=TEXT_DIM, bg=BG_DEEP,
        ).pack()

    def _build_file_section(self) -> None:
        frame = self._make_section("File Progetto JSON")

        row = tk.Frame(frame, bg=BG_CARD)
        row.pack(fill="x", padx=10, pady=10)

        self._file_var = tk.StringVar(value="Nessun file selezionato…")
        entry = tk.Entry(
            row, textvariable=self._file_var,
            bg=BG_INPUT, fg=TEXT_MAIN,
            font=("Courier", 10), state="readonly",
            relief="flat", insertbackground=TEXT_MAIN,
        )
        entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        for label, cmd, bg in [
            ("Apri…",            self._browse_open,   BG_DEEP),
            ("Nuovo",            self._create_new,    ACCENT_PURP),
            ("Carica Esempio",   self._load_example,  "#1a472a"),
        ]:
            _HoverButton(
                row, text=label, command=cmd,
                hover_bg=self._lighten(bg), normal_bg=bg,
                fg="white", font=("Arial", 10),
                cursor="hand2", relief="flat", padx=12, pady=4,
            ).pack(side="left", padx=3)

    def _build_info_section(self) -> None:
        frame = self._make_section("Informazioni Progetto")
        self._info_box = _ScrolledText(
            frame,
            bg=BG_INPUT, fg=TEXT_GREEN,
            font=("Courier", 10), state="disabled",
            height=9, relief="flat", padx=10, pady=8,
        )
        self._info_box.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self._info_box.set_content("Carica un file JSON per visualizzare le informazioni.")

    def _build_output_section(self) -> None:
        frame = self._make_section("File di Output")

        row = tk.Frame(frame, bg=BG_CARD)
        row.pack(fill="x", padx=10, pady=10)

        tk.Label(row, text="Salva in:", bg=BG_CARD, fg=TEXT_DIM,
                 font=("Arial", 10)).pack(side="left", padx=(0, 6))

        self._output_var = tk.StringVar(value="output_video.mp4")
        tk.Entry(
            row, textvariable=self._output_var,
            bg=BG_INPUT, fg=TEXT_MAIN,
            font=("Courier", 10), relief="flat",
        ).pack(side="left", fill="x", expand=True, padx=(0, 8))

        _HoverButton(
            row, text="Scegli…", command=self._browse_output,
            hover_bg=self._lighten(BG_DEEP), normal_bg=BG_DEEP,
            fg="white", font=("Arial", 10),
            cursor="hand2", relief="flat", padx=12, pady=4,
        ).pack(side="left")

    def _build_progress_section(self) -> None:
        frame = self._make_section("Avanzamento")

        self._progress_var = tk.DoubleVar(value=0)
        self._pbar = ttk.Progressbar(
            frame, variable=self._progress_var,
            maximum=100, length=900, mode="determinate",
            style="TProgressbar",
        )
        self._pbar.pack(fill="x", padx=10, pady=(8, 4))

        self._status_var = tk.StringVar(
            value="Pronto. Carica un file JSON per iniziare."
        )
        tk.Label(
            frame, textvariable=self._status_var,
            bg=BG_CARD, fg=TEXT_DIM, font=("Arial", 10),
        ).pack(pady=(0, 8))

    def _build_buttons(self) -> None:
        bar = tk.Frame(self, bg=BG_DARK)
        bar.pack(fill="x", padx=20, pady=12)

        self._btn_generate = _HoverButton(
            bar, text="\u25b6  GENERA VIDEO MP4",
            command=self._generate_video,
            hover_bg="#c0392b", normal_bg=ACCENT_RED,
            fg="white", font=("Arial", 14, "bold"),
            cursor="hand2", relief="flat", padx=28, pady=14,
            state="disabled",
        )
        self._btn_generate.pack(side="left", padx=(0, 10))

        self._btn_preview = _HoverButton(
            bar, text="\U0001f441  ANTEPRIMA",
            command=self._preview_scene,
            hover_bg=self._lighten(ACCENT_BLUE), normal_bg=ACCENT_BLUE,
            fg="white", font=("Arial", 12),
            cursor="hand2", relief="flat", padx=20, pady=14,
            state="disabled",
        )
        self._btn_preview.pack(side="left", padx=(0, 10))

        _HoverButton(
            bar, text="? Guida JSON",
            command=self._show_help,
            hover_bg=self._lighten(BG_CARD), normal_bg=BG_CARD,
            fg=TEXT_DIM, font=("Arial", 10),
            cursor="hand2", relief="flat", padx=16, pady=14,
        ).pack(side="right")

    # ------------------------------------------------------------------ #
    #  Helper layout                                                       #
    # ------------------------------------------------------------------ #

    def _make_section(self, title: str) -> tk.Frame:
        outer = tk.LabelFrame(
            self, text=f"  {title}  ",
            bg=BG_CARD, fg=TEXT_DIM,
            font=("Arial", 10, "bold"),
            relief="flat",
            bd=1,
        )
        outer.pack(fill="x", padx=16, pady=(6, 0))
        return outer

    @staticmethod
    def _lighten(hex_color: str, amount: int = 20) -> str:
        try:
            r = min(255, int(hex_color[1:3], 16) + amount)
            g = min(255, int(hex_color[3:5], 16) + amount)
            b = min(255, int(hex_color[5:7], 16) + amount)
            return f"#{r:02x}{g:02x}{b:02x}"
        except Exception:
            return hex_color

    # ------------------------------------------------------------------ #
    #  Azioni utente                                                       #
    # ------------------------------------------------------------------ #

    def _browse_open(self) -> None:
        path = filedialog.askopenfilename(
            title="Apri progetto JSON",
            filetypes=[("JSON", "*.json"), ("Tutti i file", "*.*")],
        )
        if path:
            self._load_project(path)

    def _load_project(self, path: str) -> None:
        try:
            project = SceneParser.load(path)
        except SceneParserError as exc:
            messagebox.showerror("Errore nel file JSON", str(exc))
            return
        except Exception as exc:
            messagebox.showerror("Errore", f"Impossibile aprire il file:\n{exc}")
            return

        self._project = project
        self._file_var.set(path)

        # Aggiorna infobox
        summary = SceneParser.summary(project)
        self._info_box.set_content(summary)

        # Abilita pulsanti
        self._btn_generate.config(state="normal")
        self._btn_preview.config(state="normal")
        self._set_status(f"Progetto caricato: {len(project.get('scene', []))} scene.")

    def _create_new(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Crea nuovo progetto",
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
            initialfile="mio_progetto.json",
        )
        if not path:
            return
        template = SceneParser.get_template()
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(template, fh, indent=2, ensure_ascii=False)
        except OSError as exc:
            messagebox.showerror("Errore", f"Impossibile creare il file:\n{exc}")
            return
        messagebox.showinfo(
            "Progetto creato",
            f"File creato:\n{path}\n\n"
            "Aprilo con un editor di testo (es. VS Code, Notepad++) "
            "e modifica le scene secondo le tue esigenze."
        )
        self._load_project(path)

    def _load_example(self) -> None:
        examples_dir = os.path.join(_ROOT, "examples")
        path = os.path.join(examples_dir, "esempio_ucraina.json")
        if not os.path.isfile(path):
            messagebox.showwarning(
                "File non trovato",
                f"File di esempio non trovato:\n{path}"
            )
            return
        self._load_project(path)

    def _browse_output(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Salva video MP4",
            defaultextension=".mp4",
            filetypes=[("Video MP4", "*.mp4")],
            initialfile="video_geopolitico.mp4",
        )
        if path:
            self._output_var.set(path)

    def _generate_video(self) -> None:
        if not self._project:
            messagebox.showwarning("Attenzione", "Carica prima un file JSON.")
            return
        if self._generating:
            return

        output = self._output_var.get().strip()
        if not output:
            messagebox.showwarning("Attenzione", "Specifica il percorso del file di output.")
            return

        self._generating = True
        self._btn_generate.config(state="disabled")
        self._btn_preview.config(state="disabled")
        self._progress_var.set(0)

        def _run() -> None:
            try:
                gen = VideoGenerator(
                    project=self._project,
                    output_path=output,
                    progress_callback=self._set_progress,
                    status_callback=self._set_status,
                )
                gen.generate()
                self.after(0, lambda: messagebox.showinfo(
                    "Completato!",
                    f"Video generato con successo!\n\n{output}"
                ))
            except Exception as exc:
                self.after(0, lambda: messagebox.showerror(
                    "Errore generazione",
                    f"Si è verificato un errore:\n{exc}"
                ))
                self.after(0, lambda: self._set_status(f"Errore: {exc}"))
            finally:
                self._generating = False
                self.after(0, lambda: self._btn_generate.config(state="normal"))
                self.after(0, lambda: self._btn_preview.config(state="normal"))

        threading.Thread(target=_run, daemon=True).start()

    def _preview_scene(self) -> None:
        if not self._project:
            return
        _PreviewWindow(self, self._project, scene_idx=0)

    def _show_help(self) -> None:
        _HelpWindow(self)

    # ------------------------------------------------------------------ #
    #  Callback progresso/status (thread-safe tramite after())            #
    # ------------------------------------------------------------------ #

    def _set_progress(self, value: float) -> None:
        self.after(0, lambda: self._progress_var.set(value))

    def _set_status(self, text: str) -> None:
        self.after(0, lambda: self._status_var.set(text))


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app = ScacchieraMondiale()
    app.mainloop()
