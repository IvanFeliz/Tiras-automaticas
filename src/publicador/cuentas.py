"""Cuentas de Facebook (perfil y Páginas) y su archivo de grupos."""
from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Cuenta:
    nombre: str
    tipo: str  # perfil | pagina


def cargar_cuentas(ruta: Path) -> tuple[list[Cuenta], str]:
    try:
        datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
        cuentas = [Cuenta(str(c["nombre"]), str(c.get("tipo", "pagina"))) for c in datos.get("cuentas", [])]
        return cuentas, str(datos.get("ultima", ""))
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return [], ""


def guardar_cuentas(ruta: Path, cuentas: list[Cuenta], ultima: str) -> None:
    datos = {"cuentas": [asdict(c) for c in cuentas], "ultima": ultima}
    ruta = Path(ruta)
    tmp = ruta.with_name(ruta.name + ".tmp")
    tmp.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, ruta)


def principal(cuentas: list[Cuenta]) -> Cuenta | None:
    for c in cuentas:
        if c.tipo == "perfil":
            return c
    return cuentas[0] if cuentas else None


def _slug(nombre: str) -> str:
    sin_acentos = unicodedata.normalize("NFKD", nombre).encode("ascii", "ignore").decode()
    legible = re.sub(r"[^a-z0-9]+", "-", sin_acentos.lower()).strip("-")[:40] or "cuenta"
    # Un pedacito del nombre exacto para que dos cuentas parecidas nunca compartan archivo.
    return f"{legible}-{hashlib.sha1(nombre.encode('utf-8')).hexdigest()[:6]}"


def ruta_grupos(datos: Path, cuenta: str) -> Path:
    return Path(datos) / "grupos" / f"{_slug(cuenta)}.txt"


def migrar_grupos(datos: Path, cuenta_principal: str) -> None:
    """El grupos.txt de antes (una sola cuenta) pasa a ser el de la cuenta principal."""
    viejo = Path(datos) / "grupos.txt"
    nuevo = ruta_grupos(datos, cuenta_principal)
    if viejo.exists() and not nuevo.exists():
        nuevo.parent.mkdir(parents=True, exist_ok=True)
        viejo.replace(nuevo)
