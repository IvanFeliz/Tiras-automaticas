"""Lista de grupos en grupos.txt: una línea 'nombre | link'; '#' al inicio = ignorado."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

MARCA_AUTO = "(ya no aparece)"
MARCAS = (MARCA_AUTO, "(sin permiso)")
RUTAS_ESPECIALES = {"feed", "discover", "joins", "create", "notifications", "search", "you", "categories"}


def normalizar_link_grupo(href: str) -> str | None:
    """Convierte cualquier link de grupo a https://www.facebook.com/groups/<id>/ (o None)."""
    href = (href or "").strip()
    if not href:
        return None
    if not href.startswith(("http://", "https://", "/")):
        href = "https://" + href
    u = urlparse(href)
    if u.netloc and not u.netloc.endswith("facebook.com"):
        return None
    partes = [p for p in u.path.split("/") if p]
    if len(partes) < 2 or partes[0] != "groups":
        return None
    ident = partes[1]
    if ident.lower() in RUTAS_ESPECIALES:
        return None
    return f"https://www.facebook.com/groups/{ident}/"


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
        for marca in MARCAS:
            if texto.startswith(marca):
                auto = marca == MARCA_AUTO
                texto = texto[len(marca):].strip()
                break
    if "|" not in texto:
        return _Linea(linea)
    nombre, link = (p.strip() for p in texto.split("|", 1))
    normal = normalizar_link_grupo(link)
    if normal is None:
        if not link.startswith("http"):
            return _Linea(linea)
        normal = link  # link raro pero válido: se usa tal cual
    return _Linea(linea, Grupo(nombre, normal, activo), auto)


def _formatear(g: Grupo, auto: bool = False) -> str:
    base = f"{g.nombre} | {g.link}"
    if g.activo:
        return base
    return f"# {MARCA_AUTO} {base}" if auto else f"# {base}"


def _leer(ruta: Path) -> list[_Linea]:
    ruta = Path(ruta)
    if not ruta.exists():
        return []
    datos = ruta.read_bytes()
    try:
        texto = datos.decode("utf-8-sig")
    except UnicodeDecodeError:
        texto = datos.decode("cp1252", errors="replace")
    return [_parsear(l.lstrip("\ufeff")) for l in texto.splitlines()]


def _escribir(ruta: Path, lineas: list[str]) -> None:
    """Escribe en un archivo temporal y lo reemplaza: un apagón no deja grupos.txt vacío."""
    ruta = Path(ruta)
    tmp = ruta.with_name(ruta.name + ".tmp")
    tmp.write_text("".join(l + "\n" for l in lineas), encoding="utf-8")
    if ruta.exists():
        ruta.with_name(ruta.name + ".bak").write_bytes(ruta.read_bytes())
    os.replace(tmp, ruta)


def cargar_grupos(ruta: Path) -> list[Grupo]:
    return [l.grupo for l in _leer(ruta) if l.grupo is not None]


def actualizar_grupos(ruta: Path, encontrados: list[tuple[str, str]]) -> int:
    lineas = _leer(ruta)
    encontrados = [(n, normalizar_link_grupo(l) or l) for n, l in encontrados]
    hallados = {link: nombre for nombre, link in encontrados}
    activos = sum(1 for l in lineas if l.grupo is not None and l.grupo.activo)
    # Si el escaneo encontró muy pocos (internet lento, página a medio cargar), no se desactiva nada.
    desactivar_faltantes = len(hallados) >= activos * 0.5
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
        elif g.activo and not desactivar_faltantes:
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


def marcar_ignorado(ruta: Path, link: str, motivo: str = "") -> None:
    salida = []
    for l in _leer(ruta):
        if l.grupo is not None and l.grupo.link == (normalizar_link_grupo(link) or link) and l.grupo.activo:
            salida.append(f"# ({motivo}) {l.original.strip()}" if motivo else f"# {l.original.strip()}")
        else:
            salida.append(l.original)
    _escribir(ruta, salida)
