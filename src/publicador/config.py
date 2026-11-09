"""Configuración (config.json) y carpeta de datos."""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, fields
from pathlib import Path


def carpeta_datos() -> Path:
    appdata = os.environ.get("APPDATA")
    base = Path(appdata) / "PublicadorTiras" if appdata else Path.home() / ".publicador_tiras"
    base.mkdir(parents=True, exist_ok=True)
    return base


@dataclass
class Config:
    carpeta_tiras: str = ""
    minutos_entre_publicaciones: int = 60
    ultimo_dia: str = ""
    ultima_tira: str = ""


def cargar_config(ruta: Path) -> Config:
    try:
        datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
        if not isinstance(datos, dict):
            return Config()
    except (OSError, ValueError):
        return Config()
    validos = {f.name for f in fields(Config)}
    try:
        return Config(**{k: v for k, v in datos.items() if k in validos})
    except TypeError:
        return Config()


def guardar_config(ruta: Path, cfg: Config) -> None:
    Path(ruta).write_text(json.dumps(asdict(cfg), ensure_ascii=False, indent=2), encoding="utf-8")


def bloquear_instancia(datos: Path):
    """Evita abrir el programa dos veces (compartirían el mismo navegador).

    Devuelve el archivo abierto que mantiene el candado, o None si ya hay otra instancia.
    """
    ruta = Path(datos) / ".abierto.lock"
    f = open(ruta, "a+")
    try:
        if os.name == "nt":
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return None
    return f
