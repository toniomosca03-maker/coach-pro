"""
video_generator.py — Generatore video MP4 da progetti Scacchiera Mondiale.

Algoritmo per ogni scena:
  1. Rendering del keyframe statico con matplotlib (1 chiamata pesante).
  2. Generazione dei frame con PIL (leggera, per ogni frame).
  3. Scrittura dei frame nel file MP4 con imageio + ffmpeg.

Callback opzionali:
  progress_callback(float 0-100) — aggiorna la barra di avanzamento nella GUI
  status_callback(str)           — aggiorna il testo di stato nella GUI
"""
from __future__ import annotations

import os
import tempfile
from typing import Callable, Optional

import numpy as np

from src.map_renderer import MapRenderer


class VideoGenerator:
    """
    Genera un video MP4 da un dizionario progetto (già validato da SceneParser).
    """

    def __init__(
        self,
        project: dict,
        output_path: str,
        progress_callback: Optional[Callable[[float], None]] = None,
        status_callback: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.project = project
        self.output_path = output_path
        self._progress = progress_callback or (lambda _: None)
        self._status = status_callback or (lambda _: None)

        self.metadata = project.get("metadata", {})
        self.scenes = project.get("scene", [])
        self.fps = int(self.metadata.get("fps", 30))
        self.renderer = MapRenderer(self.metadata)

    # ------------------------------------------------------------------ #
    #  Punto di ingresso                                                   #
    # ------------------------------------------------------------------ #

    def generate(self) -> None:
        """Esegue il rendering completo e salva il file MP4."""
        try:
            import imageio
        except ImportError as exc:
            raise RuntimeError(
                "imageio non trovato. Installa le dipendenze con:\n"
                "  pip install imageio imageio-ffmpeg"
            ) from exc

        output_dir = os.path.dirname(self.output_path)
        if output_dir and not os.path.isdir(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        n_scenes = len(self.scenes)
        self._status("Avvio rendering…")

        writer = imageio.get_writer(
            self.output_path,
            fps=self.fps,
            codec="libx264",
            quality=8,
            pixelformat="yuv420p",
            macro_block_size=None,
        )

        try:
            for scene_idx, scene in enumerate(self.scenes):
                scene_title = scene.get("titolo", f"Scena {scene_idx + 1}")
                self._status(
                    f"Rendering scena {scene_idx + 1}/{n_scenes}: "
                    f"\"{scene_title}\"…"
                )

                # Barra: le prime 90 unità coprono il rendering
                base_pct = (scene_idx / n_scenes) * 90.0
                frames = self._generate_scene_frames(
                    scene,
                    progress_base=base_pct,
                    progress_span=90.0 / n_scenes,
                )

                for frame in frames:
                    writer.append_data(frame)

        finally:
            writer.close()

        self._progress(100)
        self._status(f"Video salvato: {self.output_path}")

    # ------------------------------------------------------------------ #
    #  Generazione frame per una scena                                    #
    # ------------------------------------------------------------------ #

    def _generate_scene_frames(
        self,
        scene: dict,
        progress_base: float = 0.0,
        progress_span: float = 90.0,
    ) -> list[np.ndarray]:
        durata = float(scene.get("durata", 8))
        n_frames = max(1, int(durata * self.fps))

        # --- Keyframe statico (matplotlib, lento) --------------------------
        self._status(
            f"  Rendering mappa base per \"{scene.get('titolo', '')}\"…"
        )
        keyframe = self.renderer.render_scene_keyframe(scene)
        self._progress(progress_base + progress_span * 0.2)

        # --- Frame animati (PIL, veloce) ------------------------------------
        frames: list[np.ndarray] = []
        for f_idx in range(n_frames):
            progress = f_idx / max(1, n_frames - 1)
            frame = self.renderer.apply_animations(keyframe, scene, progress)
            frames.append(frame)

            # Aggiornamento avanzamento ogni 10 frame
            if f_idx % 10 == 0:
                pct = progress_base + progress_span * (0.2 + 0.8 * (f_idx / n_frames))
                self._progress(pct)

        return frames
