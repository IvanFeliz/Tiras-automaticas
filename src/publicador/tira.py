"""Lectura y validación de una carpeta de tira (spec §3)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

EXT_IMAGEN = {".png", ".jpg", ".jpeg", ".webp"}
EXT_VIDEO = {".mp4", ".mov"}
_SEPARADOR = re.compile(r"^\s*-{3,}\s*$")
_ENCABEZADO = re.compile(r"^\s*(\d+)\.\s*(.*?)\s*$")
_NUMERO_ARCHIVO = re.compile(r"^(\d+)\D")


@dataclass(frozen=True)
class Publicacion:
    numero: int
    titulo: str
    texto: str
    imagen: Path


@dataclass
class Tira:
    carpeta: Path
    publicaciones: list[Publicacion] = field(default_factory=list)
    ubicaciones: list[Path] = field(default_factory=list)
    errores: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errores


def _leer_texto(ruta: Path) -> str:
    datos = ruta.read_bytes()
    for codificacion in ("utf-8-sig", "cp1252"):
        try:
            texto = datos.decode(codificacion)
            break
        except UnicodeDecodeError:
            continue
    else:
        texto = datos.decode("utf-8", errors="replace")
    return texto.replace("\r\n", "\n").replace("\r", "\n")


def _partir_bloques(texto: str) -> list[list[str]]:
    bloques: list[list[str]] = [[]]
    for linea in texto.split("\n"):
        if _SEPARADOR.match(linea):
            bloques.append([])
        else:
            bloques[-1].append(linea)
    return bloques


def _parsear_bloque(lineas: list[str]) -> tuple[int, str, str] | None:
    """Devuelve (numero, titulo, texto) o None si el bloque no empieza con 'N. Título'."""
    # Puede haber texto previo (p. ej. el encabezado 'TIRA #') antes del primer 'N.'.
    for i, linea in enumerate(lineas):
        m = _ENCABEZADO.match(linea)
        if m:
            cuerpo = [l.strip() for l in lineas[i + 1:]]
            while cuerpo and not cuerpo[0]:
                cuerpo.pop(0)
            while cuerpo and not cuerpo[-1]:
                cuerpo.pop()
            return int(m.group(1)), m.group(2), "\n".join(cuerpo)
    return None


def _numero(nombre: str) -> int | None:
    m = _NUMERO_ARCHIVO.match(nombre)
    return int(m.group(1)) if m else None


def leer_tira(carpeta: Path) -> Tira:
    carpeta = Path(carpeta)
    tira = Tira(carpeta=carpeta)
    archivos = sorted(p for p in carpeta.iterdir() if p.is_file()) if carpeta.is_dir() else []

    txts = [p for p in archivos if p.suffix.lower() == ".txt"]
    if not txts:
        tira.errores.append("No se encontró el archivo .txt con los textos.")
    elif len(txts) > 1:
        tira.errores.append("Hay más de un archivo .txt en la carpeta: " + ", ".join(p.name for p in txts))

    imagenes: dict[int, list[Path]] = {}
    for p in archivos:
        ext = p.suffix.lower()
        n = _numero(p.name)
        if n is None:
            continue
        if n == 0 and ext in EXT_IMAGEN | EXT_VIDEO:
            tira.ubicaciones.append(p)
        elif n > 0 and ext in EXT_IMAGEN:
            imagenes.setdefault(n, []).append(p)

    if not tira.ubicaciones:
        tira.errores.append("No hay archivos de ubicación (los que empiezan con 0).")

    if len(txts) != 1:
        return tira

    vistos: set[int] = set()
    for bloque in _partir_bloques(_leer_texto(txts[0])):
        datos = _parsear_bloque(bloque)
        if datos is None:
            continue
        numero, titulo, texto = datos
        if numero in vistos:
            tira.errores.append(f"El texto número {numero} está repetido.")
            continue
        vistos.add(numero)
        if not texto:
            tira.errores.append(f"El texto número {numero} está vacío.")
        imgs = imagenes.get(numero, [])
        if not imgs:
            tira.errores.append(f"Falta la imagen del texto {numero}.")
            continue
        if len(imgs) > 1:
            tira.errores.append(f"Hay más de una imagen para el texto {numero}: " + ", ".join(p.name for p in imgs))
            continue
        tira.publicaciones.append(Publicacion(numero, titulo, texto, imgs[0]))

    for n in sorted(set(imagenes) - vistos):
        tira.errores.append(f"La imagen {imagenes[n][0].name} (número {n}) no tiene texto.")
    if not vistos:
        tira.errores.append("No se encontraron textos numerados (1., 2., …) en el .txt.")

    tira.publicaciones.sort(key=lambda p: p.numero)
    return tira


def _clave_orden(p: Path):
    m = re.match(r"^\s*(\d+)", p.name)
    if m:
        return (0, int(m.group(1)), p.name.lower())
    m = re.search(r"(\d+)\s*$", p.name)
    if m:
        return (0, int(m.group(1)), p.name.lower())
    return (1, 0, p.name.lower())


def listar_subcarpetas(carpeta: Path) -> list[Path]:
    carpeta = Path(carpeta)
    if not carpeta.is_dir():
        return []
    return sorted((p for p in carpeta.iterdir() if p.is_dir()), key=_clave_orden)
