"""Historial de publicaciones en historial.csv (UTF-8 con BOM para Excel)."""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

CAMPOS = ["fecha_hora", "dia", "tira", "numero", "titulo", "grupo", "link_grupo", "archivo_ubicacion", "resultado"]
FORMATO = "%Y-%m-%d %H:%M:%S"


@dataclass
class Registro:
    fecha_hora: datetime
    dia: str
    tira: str
    numero: int
    titulo: str
    grupo: str
    link_grupo: str
    archivo_ubicacion: str
    resultado: str  # publicado | saltado | error


class Historial:
    def __init__(self, ruta: Path):
        self.ruta = Path(ruta)

    def agregar(self, r: Registro) -> None:
        nuevo = not self.ruta.exists() or self.ruta.stat().st_size == 0
        with self.ruta.open("a", encoding="utf-8-sig" if nuevo else "utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=CAMPOS)
            if nuevo:
                w.writeheader()
            w.writerow({
                "fecha_hora": r.fecha_hora.strftime(FORMATO), "dia": r.dia, "tira": r.tira,
                "numero": r.numero, "titulo": r.titulo, "grupo": r.grupo, "link_grupo": r.link_grupo,
                "archivo_ubicacion": r.archivo_ubicacion, "resultado": r.resultado,
            })

    def _filas(self) -> list[dict]:
        if not self.ruta.exists():
            return []
        with self.ruta.open(encoding="utf-8-sig", newline="") as f:
            filas = []
            for fila in csv.DictReader(f):
                try:
                    fila["_fecha"] = datetime.strptime(fila["fecha_hora"], FORMATO)
                except (KeyError, TypeError, ValueError):
                    continue
                filas.append(fila)
            return filas

    def ultimas_publicaciones(self) -> dict[str, datetime]:
        res: dict[str, datetime] = {}
        for f in self._filas():
            if f["resultado"] == "publicado":
                link = f["link_grupo"]
                if link not in res or f["_fecha"] > res[link]:
                    res[link] = f["_fecha"]
        return res

    def ultima_publicacion(self, link: str) -> datetime | None:
        return self.ultimas_publicaciones().get(link)

    def _de_tira(self, dia: str, tira: str, fecha: date):
        return (f for f in self._filas() if f["dia"] == dia and f["tira"] == tira and f["_fecha"].date() == fecha)

    def publicadas(self, dia: str, tira: str, fecha: date) -> dict[int, str]:
        res = {}
        for f in self._de_tira(dia, tira, fecha):
            if f["resultado"] == "publicado":
                try:
                    res[int(f["numero"])] = f["link_grupo"]
                except ValueError:
                    pass
        return res

    def grupos_usados(self, dia: str, tira: str, fecha: date) -> set[str]:
        return {f["link_grupo"] for f in self._de_tira(dia, tira, fecha)}
