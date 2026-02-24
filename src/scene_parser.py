"""
scene_parser.py — Parser e validatore del formato JSON per Scacchiera Mondiale.
Legge il file di progetto e verifica che tutte le scene siano corrette.
"""
import json
import os


TIPI_ICONE_VALIDI = {
    "base_militare", "zona_conflitto", "risorsa",
    "porto", "capitale", "aeroporto", "confine"
}

TIPI_TRANSIZIONE_VALIDI = {"fade", "nessuna", "slide"}
TIPI_STILE_FRECCIA_VALIDI = {"solido", "tratteggiato", "punteggiato"}
ANIMAZIONI_PAESE_VALIDE = {"fade_in", "nessuna", "pulse"}


class SceneParserError(Exception):
    pass


class SceneParser:
    """Carica, valida e restituisce un progetto JSON."""

    @staticmethod
    def load(file_path: str) -> dict:
        if not os.path.isfile(file_path):
            raise SceneParserError(f"File non trovato: {file_path}")
        try:
            with open(file_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except json.JSONDecodeError as exc:
            raise SceneParserError(f"JSON non valido: {exc}") from exc
        SceneParser.validate(data)
        return data

    @staticmethod
    def validate(data: dict) -> None:
        if not isinstance(data, dict):
            raise SceneParserError("Il file JSON deve essere un oggetto.")
        if "scene" not in data:
            raise SceneParserError("Manca la chiave 'scene' nel progetto.")
        if not isinstance(data["scene"], list) or len(data["scene"]) == 0:
            raise SceneParserError("'scene' deve essere una lista non vuota.")
        for idx, scene in enumerate(data["scene"], start=1):
            SceneParser._validate_scene(scene, idx)

    @staticmethod
    def _validate_scene(scene: dict, idx: int) -> None:
        tag = f"Scena {idx}"
        if not isinstance(scene, dict):
            raise SceneParserError(f"{tag}: ogni scena deve essere un oggetto.")
        if "durata" in scene:
            if not isinstance(scene["durata"], (int, float)) or scene["durata"] <= 0:
                raise SceneParserError(f"{tag}: 'durata' deve essere un numero positivo.")
        for paese in scene.get("paesi", []):
            nome = paese.get("nome", "")
            if not nome:
                raise SceneParserError(f"{tag}: ogni paese deve avere un campo 'nome'.")
        for i, freccia in enumerate(scene.get("frecce", []), start=1):
            for campo in ("da", "a"):
                if campo not in freccia:
                    raise SceneParserError(
                        f"{tag}, freccia {i}: manca il campo '{campo}'."
                    )
                punto = freccia[campo]
                if "lat" not in punto or "lon" not in punto:
                    raise SceneParserError(
                        f"{tag}, freccia {i}: '{campo}' deve avere 'lat' e 'lon'."
                    )

    # ------------------------------------------------------------------ #
    #  Template e helper                                                   #
    # ------------------------------------------------------------------ #

    @staticmethod
    def get_template() -> dict:
        """Restituisce un progetto di esempio vuoto."""
        return {
            "metadata": {
                "titolo": "Il Mio Video Geopolitico",
                "canale": "Scacchiera Mondiale",
                "risoluzione": "1920x1080",
                "fps": 30,
                "tema": "scuro"
            },
            "scene": [
                {
                    "id": 1,
                    "durata": 8,
                    "titolo": "La Situazione in Europa",
                    "sottotitolo": "2024",
                    "mappa": {
                        "centro": {"lat": 50, "lon": 15},
                        "zoom": 3,
                        "sfondo": "#1a1a2e",
                        "oceani": "#0f3460"
                    },
                    "paesi": [
                        {
                            "nome": "Ukraine",
                            "colore": "#e74c3c",
                            "opacita": 0.8,
                            "etichetta": "Zona di conflitto",
                            "animazione": "fade_in"
                        },
                        {
                            "nome": "Russia",
                            "colore": "#e67e22",
                            "opacita": 0.7,
                            "etichetta": "",
                            "animazione": "nessuna"
                        }
                    ],
                    "frecce": [
                        {
                            "da": {"lat": 55.7, "lon": 37.6},
                            "a": {"lat": 50.4, "lon": 30.5},
                            "colore": "#e74c3c",
                            "spessore": 3,
                            "etichetta": "Avanzata",
                            "stile": "solido"
                        }
                    ],
                    "icone": [],
                    "testo_overlay": [],
                    "transizione": {
                        "tipo": "fade",
                        "durata": 0.5
                    }
                }
            ]
        }

    @staticmethod
    def summary(data: dict) -> str:
        """Restituisce un sommario testuale del progetto."""
        meta = data.get("metadata", {})
        scenes = data.get("scene", [])
        durata_tot = sum(s.get("durata", 5) for s in scenes)
        lines = [
            f"Titolo  : {meta.get('titolo', 'N/A')}",
            f"Canale  : {meta.get('canale', 'Scacchiera Mondiale')}",
            f"Scene   : {len(scenes)}",
            f"Durata  : {durata_tot} secondi totali",
            f"Res.    : {meta.get('risoluzione', '1920x1080')} @ {meta.get('fps', 30)} fps",
            "",
        ]
        for i, scene in enumerate(scenes, start=1):
            paesi = ", ".join(p.get("nome", "") for p in scene.get("paesi", []))
            lines.append(
                f"  [{i}] \"{scene.get('titolo', '')}\" — "
                f"{scene.get('durata', 5)}s"
                + (f"  |  Paesi: {paesi}" if paesi else "")
            )
        return "\n".join(lines)
