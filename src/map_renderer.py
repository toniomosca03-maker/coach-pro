"""
map_renderer.py — Motore di rendering delle mappe geopolitiche.

Strategia a due passi per le prestazioni:
  1. render_scene_keyframe()  → PIL Image statico (matplotlib, lento, 1 volta per scena)
  2. apply_animations()       → PIL Image animato (Pillow, veloce, 1 volta per frame)

La conversione lat/lon → pixel usa una proiezione di Mercatore semplificata
che è sufficiente per le scale tipicamente usate nei video geopolitici.
"""
from __future__ import annotations

import io
import math
import os
import warnings
from typing import Callable, Optional, Tuple

import matplotlib
matplotlib.use("Agg")  # rendering off-screen, senza display
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------------------
# Caricamento dati geografici (compatibile geopandas < 0.14 e >= 0.14)
# ---------------------------------------------------------------------------
import geopandas as gpd

def _load_world() -> gpd.GeoDataFrame:
    """Carica il dataset Natural Earth con fallback multipli."""
    # 1. geodatasets (geopandas >= 0.14)
    try:
        import geodatasets
        return gpd.read_file(geodatasets.get_path("naturalearth.countries110"))
    except Exception:
        pass
    # 2. API legacy geopandas < 0.14
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return gpd.read_file(gpd.datasets.get_path("naturalearth_lowres"))
    except Exception:
        pass
    # 3. Download diretto da Natural Earth
    url = (
        "https://naturalearth.s3.amazonaws.com/110m_cultural/"
        "ne_110m_admin_0_countries.zip"
    )
    return gpd.read_file(url)


_WORLD: Optional[gpd.GeoDataFrame] = None


def get_world() -> gpd.GeoDataFrame:
    global _WORLD
    if _WORLD is None:
        _WORLD = _load_world()
    return _WORLD


# ---------------------------------------------------------------------------
# Ricerca sistema font
# ---------------------------------------------------------------------------
_FONT_PATHS_BOLD = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "C:/Windows/Fonts/arialbd.ttf",
]
_FONT_PATHS_REGULAR = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
    "C:/Windows/Fonts/arial.ttf",
]


def _find_font(paths: list) -> Optional[str]:
    for p in paths:
        if os.path.isfile(p):
            return p
    return None


def _load_font(paths: list, size: int) -> ImageFont.FreeTypeFont:
    path = _find_font(paths)
    if path:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            pass
    return ImageFont.load_default()


# ---------------------------------------------------------------------------
# Icone simboliche (disegnate con PIL, senza immagini esterne)
# ---------------------------------------------------------------------------

def _draw_icon(draw: ImageDraw.Draw, tipo: str, px: int, py: int,
               colore: str, scala: int = 14) -> None:
    r = scala
    if tipo == "base_militare":
        # Stella a 5 punte
        punti = []
        for k in range(10):
            ang = math.radians(-90 + k * 36)
            raggio = r if k % 2 == 0 else r // 2
            punti.append((px + raggio * math.cos(ang), py + raggio * math.sin(ang)))
        draw.polygon(punti, fill=colore, outline="white")
    elif tipo == "zona_conflitto":
        # X rossa spessa
        draw.line([(px - r, py - r), (px + r, py + r)], fill=colore, width=4)
        draw.line([(px + r, py - r), (px - r, py + r)], fill=colore, width=4)
    elif tipo == "risorsa":
        # Diamante giallo
        draw.polygon([
            (px, py - r), (px + r, py), (px, py + r), (px - r, py)
        ], fill=colore, outline="white")
    elif tipo == "porto":
        # Cerchio con ancora semplificata
        draw.ellipse([(px - r, py - r), (px + r, py + r)],
                     outline=colore, width=3)
        draw.line([(px, py - r + 2), (px, py + r - 2)], fill=colore, width=3)
        draw.line([(px - r // 2, py - r // 4), (px + r // 2, py - r // 4)],
                  fill=colore, width=2)
    elif tipo == "aeroporto":
        # Croce con freccia
        draw.line([(px - r, py), (px + r, py)], fill=colore, width=3)
        draw.line([(px, py - r), (px, py + r)], fill=colore, width=3)
    else:  # "capitale" e default
        draw.ellipse([(px - r // 2, py - r // 2), (px + r // 2, py + r // 2)],
                     fill=colore, outline="white", width=2)


# ---------------------------------------------------------------------------
# Proiezione lat/lon → pixel
# ---------------------------------------------------------------------------

def _latlon_to_pixel(lat: float, lon: float,
                     extent: Tuple[float, float, float, float],
                     width: int, height: int) -> Tuple[int, int]:
    """
    Converti coordinate geografiche in pixel.
    extent = (min_lon, max_lon, min_lat, max_lat)
    """
    min_lon, max_lon, min_lat, max_lat = extent
    # Clamp
    lon = max(min_lon, min(max_lon, lon))
    lat = max(min_lat, min(max_lat, lat))
    px = int((lon - min_lon) / (max_lon - min_lon) * width)
    py = int((max_lat - lat) / (max_lat - min_lat) * height)
    return px, py


def _compute_extent(mappa: dict) -> Tuple[float, float, float, float]:
    centro = mappa.get("centro", {"lat": 20, "lon": 15})
    zoom = max(0.5, float(mappa.get("zoom", 3)))
    lat_range = 90.0 / zoom
    lon_range = 180.0 / zoom
    min_lon = centro["lon"] - lon_range
    max_lon = centro["lon"] + lon_range
    min_lat = max(-90.0, centro["lat"] - lat_range)
    max_lat = min(90.0, centro["lat"] + lat_range)
    return min_lon, max_lon, min_lat, max_lat


# ---------------------------------------------------------------------------
# Colore hex → RGB tuple
# ---------------------------------------------------------------------------

def _hex_to_rgb(hex_str: str, default=(255, 255, 255)) -> Tuple[int, int, int]:
    s = hex_str.lstrip("#")
    if len(s) != 6:
        return default
    try:
        return tuple(int(s[i:i+2], 16) for i in (0, 2, 4))
    except ValueError:
        return default


# ---------------------------------------------------------------------------
# MapRenderer
# ---------------------------------------------------------------------------

class MapRenderer:
    """
    Gestisce il rendering di una singola scena come sequenza di PIL Image.

    Uso tipico:
        renderer = MapRenderer(metadata)
        keyframe = renderer.render_scene_keyframe(scene)          # 1 volta
        for t in frame_times:
            frame = renderer.apply_animations(keyframe, scene, t)  # per ogni frame
    """

    def __init__(self, metadata: dict) -> None:
        self.metadata = metadata
        self.tema = metadata.get("tema", "scuro")
        w_str, h_str = metadata.get("risoluzione", "1920x1080").split("x")
        self.width = int(w_str)
        self.height = int(h_str)
        self.fps = int(metadata.get("fps", 30))

        if self.tema == "scuro":
            self.bg_color = "#1a1a2e"
            self.ocean_color = "#0f3460"
            self.default_country_color = "#16213e"
            self.border_color = "#2a2a4e"
            self.text_color = "#ffffff"
        else:
            self.bg_color = "#f0f4f8"
            self.ocean_color = "#a8c8e0"
            self.default_country_color = "#d8d8d8"
            self.border_color = "#aaaaaa"
            self.text_color = "#111111"

    # ------------------------------------------------------------------ #
    #  Rendering del keyframe statico (matplotlib)                        #
    # ------------------------------------------------------------------ #

    def render_scene_keyframe(self, scene: dict) -> Image.Image:
        """
        Renderizza la mappa base della scena (senza animazioni) e restituisce
        una PIL Image RGB. Chiamata costosa: invocarla 1 volta per scena.
        """
        world = get_world()
        mappa = scene.get("mappa", {})
        extent = _compute_extent(mappa)
        min_lon, max_lon, min_lat, max_lat = extent

        dpi = 96
        fig_w = self.width / dpi
        fig_h = self.height / dpi

        fig, ax = plt.subplots(1, 1, figsize=(fig_w, fig_h), dpi=dpi)
        fig.patch.set_facecolor(mappa.get("sfondo", self.bg_color))
        ax.set_facecolor(mappa.get("oceani", self.ocean_color))

        # Layer base: tutti i paesi
        world.plot(
            ax=ax,
            color=self.default_country_color,
            edgecolor=self.border_color,
            linewidth=0.5,
        )

        # Layer paesi colorati
        paesi = scene.get("paesi", [])
        for paese in paesi:
            nome = paese.get("nome", "")
            colore = paese.get("colore", "#ffffff")
            opacita = float(paese.get("opacita", 0.8))
            animazione = paese.get("animazione", "nessuna")

            # I paesi con fade_in vengono renderizzati a piena opacità nel
            # keyframe; l'alpha viene gestito in apply_animations()
            alpha = opacita if animazione == "nessuna" else opacita

            mask = world["name"].str.lower() == nome.lower()
            if not mask.any():
                mask = world["name"].str.lower().str.contains(
                    nome.lower(), na=False
                )
            if mask.any():
                world[mask].plot(
                    ax=ax,
                    color=colore,
                    edgecolor=self.border_color,
                    linewidth=0.8,
                    alpha=alpha,
                )

        # Etichette paese
        for paese in paesi:
            nome = paese.get("nome", "")
            etichetta = paese.get("etichetta", "")
            if not etichetta:
                continue
            mask = world["name"].str.lower() == nome.lower()
            if not mask.any():
                mask = world["name"].str.lower().str.contains(nome.lower(), na=False)
            if mask.any():
                centroid = world[mask].geometry.centroid.iloc[0]
                ax.text(
                    centroid.x, centroid.y, etichetta,
                    fontsize=max(6, int(8 * self.width / 1920)),
                    ha="center", va="center",
                    color="white", fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.3",
                              facecolor="black", alpha=0.55, edgecolor="none"),
                    zorder=6,
                )

        # Extent e pulizia assi
        ax.set_xlim(min_lon, max_lon)
        ax.set_ylim(min_lat, max_lat)
        ax.set_axis_off()
        plt.subplots_adjust(left=0, right=1, bottom=0, top=1)

        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight", pad_inches=0)
        plt.close(fig)
        buf.seek(0)

        img = Image.open(buf).convert("RGB")
        img = img.resize((self.width, self.height), Image.LANCZOS)
        return img

    # ------------------------------------------------------------------ #
    #  Animazioni PIL (veloce, per ogni frame)                            #
    # ------------------------------------------------------------------ #

    def apply_animations(self, keyframe: Image.Image, scene: dict,
                         progress: float) -> np.ndarray:
        """
        Applica animazioni (frecce, icone, fade paesi, overlay testo) al
        keyframe statico. `progress` è 0.0..1.0 all'interno della scena.
        Restituisce un numpy array RGB uint8.
        """
        mappa = scene.get("mappa", {})
        extent = _compute_extent(mappa)

        # Copia su RGBA per compositing
        frame = keyframe.copy().convert("RGBA")

        # --- Animazione fade_in per i paesi -----------------------------------
        self._animate_country_fadeins(frame, scene, progress, extent)

        # --- Frecce animate ---------------------------------------------------
        self._draw_animated_arrows(frame, scene, progress, extent)

        # --- Icone ------------------------------------------------------------
        self._draw_icons(frame, scene, progress, extent)

        # --- Transizione fade (inizio/fine scena) ----------------------------
        durata = float(scene.get("durata", 8))
        trans = scene.get("transizione", {})
        trans_tipo = trans.get("tipo", "fade")
        trans_dur = float(trans.get("durata", 0.5))

        if trans_tipo == "fade":
            t = progress * durata  # secondi all'interno della scena
            if t < trans_dur and trans_dur > 0:
                alpha_factor = t / trans_dur
                overlay = Image.new("RGBA", frame.size, (0, 0, 0, 0))
                black = Image.new("RGBA", frame.size,
                                  (0, 0, 0, int(255 * (1 - alpha_factor))))
                frame = Image.alpha_composite(frame, black)
            elif t > (durata - trans_dur) and trans_dur > 0:
                alpha_factor = (durata - t) / trans_dur
                black = Image.new("RGBA", frame.size,
                                  (0, 0, 0, int(255 * (1 - alpha_factor))))
                frame = Image.alpha_composite(frame, black)

        # Converti in RGB
        rgb = frame.convert("RGB")

        # --- Overlay testo + branding (su immagine RGB finale) ---------------
        rgb = self._add_text_overlays(rgb, scene, progress)

        return np.array(rgb)

    # ------------------------------------------------------------------ #
    #  Helper animazioni                                                   #
    # ------------------------------------------------------------------ #

    def _animate_country_fadeins(self, frame: Image.Image, scene: dict,
                                  progress: float,
                                  extent: Tuple[float, float, float, float]) -> None:
        """
        Renderizza un overlay semi-trasparente per i paesi con animazione
        'fade_in', aumentando gradualmente la visibilità.
        """
        # Per questa ottimizzazione usiamo solo matplotlib se strettamente
        # necessario. Invece, gestiamo il fade direttamente nel keyframe
        # variando l'alpha del layer del paese. Poiché il keyframe è già
        # renderizzato, qui applichiamo un layer di copertura inverso:
        # all'inizio il paese è coperto da uno strato opaco che svanisce.
        paesi_fade = [
            p for p in scene.get("paesi", [])
            if p.get("animazione") == "fade_in"
        ]
        if not paesi_fade:
            return

        # fade_in: completamente visibile dopo il 40% della scena
        fade_progress = min(1.0, progress / 0.4)
        if fade_progress >= 1.0:
            return

        # Applica un overlay scuro che si dissolve sui paesi fade_in.
        # Poiché non abbiamo la maschera pixel dei singoli paesi (senza
        # ridisegnare la mappa) usiamo un overlay globale leggero come
        # compromesso accettabile per la performance.
        alpha_cover = int(200 * (1.0 - fade_progress))
        cover = Image.new("RGBA", frame.size, (10, 10, 30, alpha_cover))
        frame.paste(cover, mask=cover)

    def _draw_animated_arrows(self, frame: Image.Image, scene: dict,
                               progress: float,
                               extent: Tuple[float, float, float, float]) -> None:
        draw = ImageDraw.Draw(frame)
        frecce = scene.get("frecce", [])

        for freccia in frecce:
            da = freccia.get("da", {})
            a = freccia.get("a", {})
            colore = freccia.get("colore", "#e74c3c")
            spessore = int(freccia.get("spessore", 3))
            stile = freccia.get("stile", "solido")
            etichetta = freccia.get("etichetta", "")

            x0, y0 = _latlon_to_pixel(
                da["lat"], da["lon"], extent, self.width, self.height
            )
            x1, y1 = _latlon_to_pixel(
                a["lat"], a["lon"], extent, self.width, self.height
            )

            # L'animazione "draw" disegna la freccia progressivamente
            anim_progress = min(1.0, progress * 1.8)
            xc = int(x0 + (x1 - x0) * anim_progress)
            yc = int(y0 + (y1 - y0) * anim_progress)

            rgb = _hex_to_rgb(colore)
            color_rgba = rgb + (230,)

            if stile == "tratteggiato":
                self._draw_dashed_line(draw, x0, y0, xc, yc, color_rgba, spessore)
            elif stile == "punteggiato":
                self._draw_dashed_line(draw, x0, y0, xc, yc, color_rgba,
                                       spessore, dash=(4, 8))
            else:
                draw.line([(x0, y0), (xc, yc)], fill=color_rgba, width=spessore)

            # Punta della freccia
            if anim_progress > 0.05:
                self._draw_arrowhead(draw, x0, y0, xc, yc, color_rgba,
                                     size=spessore * 5)

            # Etichetta freccia
            if etichetta and anim_progress > 0.5:
                mx = (x0 + xc) // 2
                my = (y0 + yc) // 2
                font = _load_font(_FONT_PATHS_BOLD, max(14, spessore * 5))
                draw.text((mx + 2, my + 2), etichetta, font=font,
                          fill=(0, 0, 0, 200))
                draw.text((mx, my), etichetta, font=font, fill=color_rgba)

    def _draw_icons(self, frame: Image.Image, scene: dict,
                    progress: float,
                    extent: Tuple[float, float, float, float]) -> None:
        draw = ImageDraw.Draw(frame)
        icone = scene.get("icone", [])
        icon_colors = {
            "base_militare": "#ff6b35",
            "zona_conflitto": "#e74c3c",
            "risorsa": "#f1c40f",
            "porto": "#3498db",
            "capitale": "#ecf0f1",
            "aeroporto": "#9b59b6",
            "confine": "#e74c3c",
        }
        scale = max(10, int(14 * self.width / 1920))
        font = _load_font(_FONT_PATHS_REGULAR, max(12, int(14 * self.width / 1920)))

        for icona in icone:
            tipo = icona.get("tipo", "capitale")
            lat = float(icona.get("lat", 0))
            lon = float(icona.get("lon", 0))
            etichetta = icona.get("etichetta", "")
            colore = icona.get("colore", icon_colors.get(tipo, "#ffffff"))

            px, py = _latlon_to_pixel(lat, lon, extent, self.width, self.height)
            _draw_icon(draw, tipo, px, py, colore, scala=scale)

            if etichetta:
                draw.text((px + scale + 3, py - scale // 2), etichetta,
                          font=font, fill=_hex_to_rgb(colore) + (220,))

    # ------------------------------------------------------------------ #
    #  Overlay testo e branding                                            #
    # ------------------------------------------------------------------ #

    def _add_text_overlays(self, img: Image.Image, scene: dict,
                           progress: float) -> Image.Image:
        draw = ImageDraw.Draw(img)
        w, h = img.size
        scale = w / 1920  # fattore di scala rispetto a 1920x1080

        titolo = scene.get("titolo", "")
        sottotitolo = scene.get("sottotitolo", "")
        canale = self.metadata.get("canale", "Scacchiera Mondiale")

        # Font
        fs_title = max(24, int(52 * scale))
        fs_sub = max(16, int(30 * scale))
        fs_brand = max(14, int(26 * scale))

        f_title = _load_font(_FONT_PATHS_BOLD, fs_title)
        f_sub = _load_font(_FONT_PATHS_REGULAR, fs_sub)
        f_brand = _load_font(_FONT_PATHS_BOLD, fs_brand)

        # -- Barra titolo in basso ------------------------------------------
        if titolo:
            bar_h = int(110 * scale)
            bar = Image.new("RGBA", (w, bar_h), (0, 0, 0, 185))
            img_rgba = img.convert("RGBA")
            img_rgba.paste(bar, (0, h - bar_h), bar)
            img = img_rgba.convert("RGB")
            draw = ImageDraw.Draw(img)

            pad = int(40 * scale)
            draw.text((pad, h - bar_h + int(8 * scale)), titolo,
                      font=f_title, fill=(255, 255, 255))
            if sottotitolo:
                draw.text((pad, h - bar_h + fs_title + int(10 * scale)),
                          sottotitolo, font=f_sub, fill=(190, 190, 210))

        # -- Branding Scacchiera Mondiale (in alto a sinistra) ---------------
        brand_text = f"\u265f {canale}"
        brand_w = int(340 * scale)
        brand_h = int(46 * scale)
        brand_bg = Image.new("RGBA", (brand_w, brand_h), (15, 52, 96, 220))
        img_rgba = img.convert("RGBA")
        img_rgba.paste(brand_bg, (0, 0), brand_bg)
        img = img_rgba.convert("RGB")
        draw = ImageDraw.Draw(img)
        draw.text((int(12 * scale), int(10 * scale)), brand_text,
                  font=f_brand, fill=(226, 185, 111))

        # -- Overlay testo aggiuntivo -----------------------------------------
        for testo_cfg in scene.get("testo_overlay", []):
            testo = testo_cfg.get("testo", "")
            posizione = testo_cfg.get("posizione", "centro")
            dimensione = int(testo_cfg.get("dimensione", 28) * scale)
            colore = _hex_to_rgb(testo_cfg.get("colore", "#ffffff"))
            sfondo = testo_cfg.get("sfondo", None)

            f_ov = _load_font(_FONT_PATHS_REGULAR, max(12, dimensione))
            draw = ImageDraw.Draw(img)

            # Misura testo
            bbox = draw.textbbox((0, 0), testo, font=f_ov)
            tw = bbox[2] - bbox[0]
            th = bbox[3] - bbox[1]

            if posizione in ("centro", "center"):
                tx = (w - tw) // 2
                ty = (h - th) // 2
            elif posizione == "alto":
                tx = (w - tw) // 2
                ty = int(80 * scale)
            elif posizione == "basso":
                tx = (w - tw) // 2
                ty = h - int(200 * scale)
            else:
                # Posizione personalizzata come "x,y" o stringa nota
                try:
                    px_str, py_str = posizione.split(",")
                    tx, ty = int(px_str), int(py_str)
                except Exception:
                    tx = (w - tw) // 2
                    ty = (h - th) // 2

            # Sfondo rettangolare opzionale
            if sfondo:
                padding = 8
                bg_col = _hex_to_rgb(sfondo) + (180,)
                bg_layer = img.copy().convert("RGBA")
                bg_d = ImageDraw.Draw(bg_layer)
                bg_d.rectangle(
                    [tx - padding, ty - padding,
                     tx + tw + padding, ty + th + padding],
                    fill=bg_col,
                )
                img = Image.alpha_composite(
                    img.convert("RGBA"), bg_layer
                ).convert("RGB")
                draw = ImageDraw.Draw(img)

            # Ombra testo
            draw.text((tx + 2, ty + 2), testo, font=f_ov, fill=(0, 0, 0))
            draw.text((tx, ty), testo, font=f_ov, fill=colore)

        return img

    # ------------------------------------------------------------------ #
    #  Helper geometrici                                                   #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _draw_arrowhead(draw: ImageDraw.Draw,
                        x0: int, y0: int, x1: int, y1: int,
                        color: tuple, size: int = 18) -> None:
        dx = x1 - x0
        dy = y1 - y0
        length = math.hypot(dx, dy)
        if length < 1:
            return
        ux, uy = dx / length, dy / length
        # Basi della punta
        perp_x, perp_y = -uy, ux
        half = size // 2
        tip = (x1, y1)
        base1 = (x1 - int(ux * size) + int(perp_x * half),
                 y1 - int(uy * size) + int(perp_y * half))
        base2 = (x1 - int(ux * size) - int(perp_x * half),
                 y1 - int(uy * size) - int(perp_y * half))
        draw.polygon([tip, base1, base2], fill=color)

    @staticmethod
    def _draw_dashed_line(draw: ImageDraw.Draw,
                          x0: int, y0: int, x1: int, y1: int,
                          color: tuple, width: int = 2,
                          dash: Tuple[int, int] = (12, 8)) -> None:
        length = math.hypot(x1 - x0, y1 - y0)
        if length < 1:
            return
        steps = int(length)
        ux = (x1 - x0) / length
        uy = (y1 - y0) / length
        dash_on, dash_off = dash
        period = dash_on + dash_off
        for s in range(0, steps, period):
            seg_end = min(s + dash_on, steps)
            ax = int(x0 + ux * s)
            ay = int(y0 + uy * s)
            bx = int(x0 + ux * seg_end)
            by = int(y0 + uy * seg_end)
            draw.line([(ax, ay), (bx, by)], fill=color, width=width)

    # ------------------------------------------------------------------ #
    #  Anteprima per la GUI                                                #
    # ------------------------------------------------------------------ #

    def render_preview(self, scene: dict) -> Image.Image:
        """
        Genera un'immagine di anteprima a metà progress (0.5) per la GUI.
        """
        keyframe = self.render_scene_keyframe(scene)
        arr = self.apply_animations(keyframe, scene, 0.5)
        return Image.fromarray(arr)
