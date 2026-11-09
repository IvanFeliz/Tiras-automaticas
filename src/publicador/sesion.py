"""Secuencia de publicación de una tira (spec §7 y §8), sin depender de Tk ni de Playwright."""
from __future__ import annotations

import random
import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Protocol

from .grupos import Grupo, cargar_grupos, marcar_ignorado
from .historial import Historial, Registro
from .rotacion import elegir_grupo
from .tira import Publicacion, Tira


class ErrorFacebook(Exception):
    """Algo falló al preparar una publicación en Facebook."""


@dataclass
class Controles:
    saltar: threading.Event = field(default_factory=threading.Event)
    detener: threading.Event = field(default_factory=threading.Event)


class NavegadorProto(Protocol):
    def sesion_activa(self) -> bool: ...
    def preparar_publicacion(self, link: str, texto: str, archivos: list[Path]) -> None: ...
    def esperar_resultado(self, controles: Controles) -> str: ...
    def cerrar_compositor(self) -> None: ...
    def captura(self, nombre: str) -> Path: ...


class UIProto(Protocol):
    def estado(self, mensaje: str) -> None: ...
    def progreso(self, actual: int, total: int, titulo: str, grupo: str) -> None: ...
    def preguntar(self, mensaje: str, opciones: list[str]) -> str: ...


@dataclass
class Resultado:
    publicadas: int
    saltadas: int
    motivo_fin: str  # terminada | detenida | sin_grupos


REINTENTAR, SALTAR, DETENER = "Reintentar", "Saltar este grupo", "Detener"


def ejecutar_tira(tira: Tira, dia: str, nombre_tira: str, fb: NavegadorProto, ui: UIProto,
                  controles: Controles, ruta_grupos: Path, historial: Historial, minutos: int,
                  ahora: Callable[[], datetime] = datetime.now, rng: random.Random | None = None) -> Resultado:
    rng = rng or random.Random()
    hoy = ahora().date()
    hechas = historial.publicadas(dia, nombre_tira, hoy)
    excluir = set(historial.grupos_usados(dia, nombre_tira, hoy))
    total = len(tira.publicaciones)
    publicadas = saltadas = 0

    def registrar(pub: Publicacion, grupo: Grupo, ubicacion: Path, resultado: str) -> None:
        historial.agregar(Registro(ahora(), dia, nombre_tira, pub.numero, pub.titulo, grupo.nombre,
                                   grupo.link, ubicacion.name, resultado))

    def fin(motivo: str) -> Resultado:
        return Resultado(publicadas, saltadas, motivo)

    for indice, pub in enumerate(tira.publicaciones, start=1):
        if pub.numero in hechas:
            continue
        grupo: Grupo | None = None
        while True:
            if controles.detener.is_set():
                return fin("detenida")
            controles.saltar.clear()
            if grupo is None:
                grupo = elegir_grupo(cargar_grupos(ruta_grupos), historial, ahora(), minutos, excluir, rng)
                if grupo is None:
                    ui.estado("No hay grupos disponibles ahora. Intenta más tarde o actualiza los grupos.")
                    return fin("sin_grupos")
                excluir.add(grupo.link)
            ui.progreso(indice, total, pub.titulo, grupo.nombre)
            ui.estado(f"Preparando publicación {indice} de {total} en «{grupo.nombre}»…")

            while not fb.sesion_activa():
                ui.preguntar("Inicia sesión en el navegador y da clic en Continuar", ["Continuar"])

            ubicacion = rng.choice(tira.ubicaciones)
            try:
                fb.preparar_publicacion(grupo.link, pub.texto, [pub.imagen, ubicacion])
            except ErrorFacebook as e:
                ruta = fb.captura(f"error_{nombre_tira}_{pub.numero}")
                registrar(pub, grupo, ubicacion, "error")
                resp = ui.preguntar(f"No se pudo preparar la publicación en «{grupo.nombre}»: {e}\n"
                                    f"Captura guardada en {ruta}", [REINTENTAR, SALTAR, DETENER])
                if resp == REINTENTAR:
                    continue
                fb.cerrar_compositor()
                if resp == DETENER:
                    return fin("detenida")
                marcar_ignorado(ruta_grupos, grupo.link)
                saltadas += 1
                grupo = None
                continue

            ui.estado(f"Esperando a que des clic en Publicar… ({indice} de {total}, «{grupo.nombre}»)")
            res = fb.esperar_resultado(controles)
            if res == "publicado":
                registrar(pub, grupo, ubicacion, "publicado")
                publicadas += 1
                break
            if res == "detener":
                fb.cerrar_compositor()
                return fin("detenida")
            registrar(pub, grupo, ubicacion, "saltado")
            saltadas += 1
            if res == "saltar":
                fb.cerrar_compositor()
                marcar_ignorado(ruta_grupos, grupo.link)
            grupo = None

    ui.estado(f"{nombre_tira} terminada ✅ ({publicadas} publicadas)")
    return fin("terminada")
