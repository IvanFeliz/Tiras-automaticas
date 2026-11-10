"""Historial de publicaciones en historial.csv (UTF-8 con BOM para Excel)."""
from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

CAMPOS = ["fecha_hora", "dia", "tira", "numero", "titulo", "grupo", "link_grupo", "archivo_ubicacion", "resultado",
          "cuenta"]
FORMATO = "%Y-%m-%d %H:%M:%S"
# Formatos que deja Excel si alguien guarda el archivo desde ahí.
FORMATOS_LECTURA = (FORMATO, "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%y %H:%M")


def _fecha(texto: str) -> datetime | None:
    for f in FORMATOS_LECTURA:
        try:
            return datetime.strptime((texto or "").strip(), f)
        except ValueError:
            continue
    return None


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
    resultado: str  # publicado | saltado | error | bloqueo
    cuenta: str = ""


class Historial:
    def __init__(self, ruta: Path, cuenta_principal: str = ""):
        self.ruta = Path(ruta)
        # Las filas de antes (sin columna cuenta) se consideran de la cuenta principal.
        self.cuenta_principal = cuenta_principal

    def _leer_crudo(self) -> tuple[str, bool]:
        """Devuelve (texto, normal). normal=False si Excel lo guardó en ANSI o con ';'."""
        datos = self.ruta.read_bytes()
        try:
            texto = datos.decode("utf-8-sig")
            normal = True
        except UnicodeDecodeError:
            texto = datos.decode("cp1252", errors="replace")
            normal = False
        primera = texto.split("\n", 1)[0]
        if ";" in primera and "," not in primera:
            normal = False
        return texto, normal

    def _filas_crudas(self) -> list[dict]:
        """Todas las filas tal cual, aunque la fecha no se entienda."""
        if not self.ruta.exists():
            return []
        texto, _ = self._leer_crudo()
        primera = texto.split("\n", 1)[0]
        delimitador = ";" if (";" in primera and "," not in primera) else ","
        filas = []
        for fila in csv.DictReader(io.StringIO(texto, newline=""), delimiter=delimitador):
            filas.append({k: (fila.get(k) or "") for k in CAMPOS})
        return filas

    def _reescribir(self, cambiar=None) -> None:
        """Reescribe el archivo en el formato del programa (con respaldo .bak), sin perder filas."""
        filas = self._filas_crudas()
        tmp = self.ruta.with_suffix(".csv.tmp")
        with tmp.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=CAMPOS, extrasaction="ignore")
            w.writeheader()
            for fila in filas:
                fecha = _fecha(fila["fecha_hora"])
                if fecha is not None:
                    fila["fecha_hora"] = fecha.strftime(FORMATO)
                if cambiar is not None:
                    cambiar(fila)
                w.writerow(fila)
        self.ruta.with_suffix(".csv.bak").write_bytes(self.ruta.read_bytes())
        tmp.replace(self.ruta)

    def _normalizar(self) -> None:
        """Si Excel cambió el formato (o es de la versión sin cuentas), se reescribe."""
        if not self.ruta.exists() or self.ruta.stat().st_size == 0:
            return
        texto, normal = self._leer_crudo()
        encabezado = texto.split("\n", 1)[0]
        if normal and "cuenta" in encabezado:
            return
        self._reescribir()

    def fijar_cuenta_vacia(self, cuenta: str) -> None:
        """Las filas sin cuenta (de la versión anterior) quedan a nombre de esta cuenta, para siempre."""
        if not cuenta or not self.ruta.exists() or self.ruta.stat().st_size == 0:
            return
        if not any(not f["cuenta"] for f in self._filas_crudas()):
            return

        def poner(fila: dict) -> None:
            if not fila["cuenta"]:
                fila["cuenta"] = cuenta
        self._reescribir(poner)

    def agregar(self, r: Registro) -> None:
        self._normalizar()
        nuevo = not self.ruta.exists() or self.ruta.stat().st_size == 0
        if not nuevo:
            with self.ruta.open("rb") as f:
                f.seek(-1, 2)
                falta_salto = f.read(1) not in (b"\n", b"\r")
            if falta_salto:  # si alguien lo guardó sin salto final, la fila nueva no se pega a la última
                with self.ruta.open("ab") as f:
                    f.write(b"\r\n")
        with self.ruta.open("a", encoding="utf-8-sig" if nuevo else "utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=CAMPOS)
            if nuevo:
                w.writeheader()
            w.writerow({
                "fecha_hora": r.fecha_hora.strftime(FORMATO), "dia": r.dia, "tira": r.tira,
                "numero": r.numero, "titulo": r.titulo, "grupo": r.grupo, "link_grupo": r.link_grupo,
                "archivo_ubicacion": r.archivo_ubicacion, "resultado": r.resultado, "cuenta": r.cuenta,
            })

    def _filas(self) -> list[dict]:
        if not self.ruta.exists():
            return []
        texto, _ = self._leer_crudo()
        primera = texto.split("\n", 1)[0]
        delimitador = ";" if (";" in primera and "," not in primera) else ","
        filas = []
        for fila in csv.DictReader(io.StringIO(texto, newline=""), delimiter=delimitador):
            fecha = _fecha(fila.get("fecha_hora") or "")
            if fecha is None:
                continue
            fila["_fecha"] = fecha
            for k in CAMPOS:
                fila[k] = fila.get(k) or ""
            fila["_cuenta"] = fila["cuenta"] or self.cuenta_principal
            filas.append(fila)
        return filas

    def ultimas_publicaciones(self, cuenta: str | None = None) -> dict[str, datetime]:
        res: dict[str, datetime] = {}
        for f in self._filas():
            if f["resultado"] != "publicado" or (cuenta is not None and f["_cuenta"] != cuenta):
                continue
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

    def grupos_usados(self, dia: str, tira: str, fecha: date, cuenta: str | None = None) -> set[str]:
        return {f["link_grupo"] for f in self._de_tira(dia, tira, fecha)
                if f["link_grupo"] and (cuenta is None or f["_cuenta"] == cuenta)}

    def _de_cuenta_hoy(self, cuenta: str, fecha: date):
        return (f for f in self._filas() if f["_cuenta"] == cuenta and f["_fecha"].date() == fecha)

    def publicadas_hoy_cuenta(self, cuenta: str, fecha: date) -> int:
        return sum(1 for f in self._de_cuenta_hoy(cuenta, fecha) if f["resultado"] == "publicado")

    def bloqueada_hoy(self, cuenta: str, fecha: date) -> bool:
        return any(f["resultado"] == "bloqueo" for f in self._de_cuenta_hoy(cuenta, fecha))
