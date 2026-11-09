"""Lista de grupos en grupos.txt: una línea 'nombre | link'; '#' al inicio = ignorado."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

MARCA_AUTO = "(ya no aparece)"


@dataclass
class Grupo:
    nombre: str
    link: str
    activo: bool = True


@dataclass
class _Linea:
    original: str
    grupo: Grupo | None = None
    auto: bool = False  # marcado automáticamente como "ya no aparece"


def _parsear(linea: str) -> _Linea:
    texto = linea.strip()
    activo = True
    auto = False
    if texto.startswith("#"):
        activo = False
        texto = texto.lstrip("#").strip()
        if texto.startswith(MARCA_AUTO):
            auto = True
            texto = texto[len(MARCA_AUTO):].strip()
    if "|" not in texto:
        return _Linea(linea)
    nombre, link = (p.strip() for p in texto.split("|", 1))
    if not link.startswith("http"):
        return _Linea(linea)
    return _Linea(linea, Grupo(nombre, link, activo), auto)


def _formatear(g: Grupo, auto: bool = False) -> str:
    base = f"{g.nombre} | {g.link}"
    if g.activo:
        return base
    return f"# {MARCA_AUTO} {base}" if auto else f"# {base}"


def _leer(ruta: Path) -> list[_Linea]:
    ruta = Path(ruta)
    if not ruta.exists():
        return []
    return [_parsear(l) for l in ruta.read_text(encoding="utf-8").splitlines()]


def _escribir(ruta: Path, lineas: list[str]) -> None:
    Path(ruta).write_text("".join(l + "\n" for l in lineas), encoding="utf-8")


def cargar_grupos(ruta: Path) -> list[Grupo]:
    return [l.grupo for l in _leer(ruta) if l.grupo is not None]


def actualizar_grupos(ruta: Path, encontrados: list[tuple[str, str]]) -> int:
    lineas = _leer(ruta)
    hallados = {link: nombre for nombre, link in encontrados}
    conocidos: set[str] = set()
    salida: list[str] = []
    for l in lineas:
        g = l.grupo
        if g is None:
            if l.original.strip():
                salida.append(l.original)
            continue
        if g.link in conocidos:
            continue
        conocidos.add(g.link)
        if g.link in hallados:
            if l.auto:  # volvió a aparecer: se reactiva
                g.activo = True
                salida.append(_formatear(g))
            else:
                salida.append(l.original.strip())
        elif g.activo or l.auto:
            g.activo = False
            salida.append(_formatear(g, auto=True))
        else:
            salida.append(l.original.strip())
    nuevos = 0
    for nombre, link in encontrados:
        if link not in conocidos:
            conocidos.add(link)
            salida.append(_formatear(Grupo(nombre, link)))
            nuevos += 1
    _escribir(ruta, salida)
    return nuevos


def marcar_ignorado(ruta: Path, link: str) -> None:
    salida = []
    for l in _leer(ruta):
        if l.grupo is not None and l.grupo.link == link and l.grupo.activo:
            salida.append(f"# {l.original.strip()}")
        else:
            salida.append(l.original)
    _escribir(ruta, salida)
