"""Secuencia de publicación de una tira, sin depender de Tk ni de Playwright.

Spec original §7–§8 y spec de cuentas y modo automático §3–§6.
"""
from __future__ import annotations

import random
import threading
import time
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


class GrupoSinPermiso(ErrorFacebook):
    """En este grupo la cuenta no puede publicar (por ejemplo, la banearon)."""


class SesionCerrada(Exception):
    """Facebook pide iniciar sesión."""


class NavegadorCerrado(Exception):
    """El navegador se cerró (por ejemplo, a mano)."""


class CuentaBloqueada(Exception):
    """Facebook bloqueó la cuenta o pidió verificación.

    publicado=True: el bloqueo apareció justo después de una publicación que sí salió.
    """

    def __init__(self, mensaje: str = "", publicado: bool = False):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.publicado = publicado


@dataclass
class Controles:
    saltar: threading.Event = field(default_factory=threading.Event)
    detener: threading.Event = field(default_factory=threading.Event)
    limite_s: float | None = None  # tiempo máximo esperando el resultado (None = sin límite)


class NavegadorProto(Protocol):
    def asegurar_cuenta(self, nombre: str) -> None: ...
    def preparar_publicacion(self, link: str, texto: str, archivos: list[Path]) -> None: ...
    def publicar(self, controles: Controles | None = None) -> bool: ...
    def esperar_resultado(self, controles: Controles) -> str: ...
    def cerrar_compositor(self) -> None: ...
    def captura(self, nombre: str) -> Path: ...


class UIProto(Protocol):
    def estado(self, mensaje: str) -> None: ...
    def progreso(self, actual: int, total: int, titulo: str, grupo: str) -> None: ...
    def preguntar(self, mensaje: str, opciones: list[str]) -> str: ...
    def aviso(self, nivel: str, mensaje: str) -> None: ...


@dataclass
class Ritmo:
    modo: str = "revision"  # revision | automatico
    espera_min: int = 5  # minutos entre publicaciones (automático)
    espera_max: int = 10

    @property
    def automatico(self) -> bool:
        return self.modo == "automatico"


@dataclass
class Resultado:
    publicadas: int
    saltadas: int
    motivo_fin: str  # terminada | detenida | sin_grupos | bloqueada
    cuenta_bloqueada: str = ""
    mensaje_bloqueo: str = ""


REINTENTAR, SALTAR, DETENER = "Reintentar", "Saltar este grupo", "Detener"
SI_SE_PUBLICO = "Sí se publicó"
IGNORAR_EN_CUENTA, SOLO_SALTAR = "Ignorarlo en esta cuenta", "Solo saltarlo esta vez"
SEGUIR = "Seguir"
PAUSA_REVISION_S = (5, 15)
LIMITE_TRAS_CLIC_S = 180
AVISOS_PUBLICADAS = (24, 48)
ERRORES_SEGUIDOS_AVISO = 3
ERRORES_SEGUIDOS_PAUSA = 5


def _mmss(segundos: float) -> str:
    s = max(0, int(round(segundos)))
    return f"{s // 60}:{s % 60:02d}"


def ejecutar_tira(tira: Tira, dia: str, nombre_tira: str, fb: NavegadorProto, ui: UIProto,
                  controles: Controles, ruta_grupos: Path, historial: Historial, minutos: int,
                  ahora: Callable[[], datetime] = datetime.now, rng: random.Random | None = None,
                  cuenta: str = "", ritmo: Ritmo | None = None,
                  dormir: Callable[[float], None] = time.sleep) -> Resultado:
    rng = rng or random.Random()
    ritmo = ritmo or Ritmo()
    hoy = ahora().date()
    filtro_cuenta = cuenta or None
    cuenta_real = cuenta or historial.cuenta_principal
    nombre_cuenta = cuenta_real or "esta cuenta"
    # Lo ya publicado de esta tira hoy cuenta con cualquier cuenta: así no se repite un anuncio.
    hechas = historial.publicadas(dia, nombre_tira, hoy)
    # Tampoco se usa un grupo donde otra cuenta ya intentó esta tira hoy (sería el mismo anuncio dos veces).
    excluir = set(historial.grupos_usados(dia, nombre_tira, hoy))
    pendientes = [p for p in tira.publicaciones if p.numero not in hechas]
    total = len(tira.publicaciones)
    publicadas = saltadas = 0
    errores_seguidos = 0

    def registrar(pub: Publicacion, grupo: Grupo | None, ubicacion: Path | None, resultado: str) -> None:
        registro = Registro(ahora(), dia, nombre_tira, pub.numero, pub.titulo,
                            grupo.nombre if grupo else "", grupo.link if grupo else "",
                            ubicacion.name if ubicacion else "", resultado, cuenta)
        while True:
            try:
                historial.agregar(registro)
                return
            except OSError:
                resp = ui.preguntar("No se pudo guardar el historial. Si historial.csv está abierto en Excel, "
                                    "ciérralo y da clic en Reintentar.", [REINTENTAR, "Continuar sin guardar"])
                if resp != REINTENTAR:
                    return

    def ignorar(grupo: Grupo, motivo: str = "") -> None:
        try:
            marcar_ignorado(ruta_grupos, grupo.link, motivo)
        except OSError:
            ui.estado(f"No se pudo marcar «{grupo.nombre}» en {ruta_grupos.name} (¿está abierto en otro "
                      "programa?). Se sigue con otro grupo.")

    def fin(motivo: str, mensaje_bloqueo: str = "") -> Resultado:
        return Resultado(publicadas, saltadas, motivo,
                         cuenta_real if motivo == "bloqueada" else "", mensaje_bloqueo)

    def contar_error() -> bool:
        """Cuenta un error seguido. Devuelve False si la persona decide detener."""
        nonlocal errores_seguidos
        errores_seguidos += 1
        if errores_seguidos == ERRORES_SEGUIDOS_AVISO:
            ui.aviso("amarillo", f"Facebook podría estar limitando «{nombre_cuenta}»: van "
                                 f"{errores_seguidos} errores seguidos en distintos grupos.")
        if errores_seguidos % ERRORES_SEGUIDOS_PAUSA == 0:
            resp = ui.preguntar(f"Van {errores_seguidos} errores seguidos con «{nombre_cuenta}». Facebook podría "
                                "estar limitando la cuenta. Revisa el navegador. ¿Sigo?", [SEGUIR, DETENER])
            return resp != DETENER
        return True

    def bloqueo(pub: Publicacion, grupo: Grupo | None, ubicacion: Path | None, e: CuentaBloqueada) -> Resultado:
        nonlocal publicadas
        if e.publicado:
            registrar(pub, grupo, ubicacion, "publicado")
            publicadas += 1
        ruta = fb.captura(f"bloqueo_{nombre_tira}_{pub.numero}")
        registrar(pub, grupo, ubicacion, "bloqueo")
        ui.aviso("rojo", f"⛔ Facebook bloqueó o pidió verificación a «{nombre_cuenta}»: «{e.mensaje}». "
                         f"Se detuvo la tira. Captura: {ruta}")
        return fin("bloqueada", e.mensaje)

    def esperar(segundos: float, contar: bool) -> bool:
        """Espera en pasos de 1 s. Devuelve False si se pidió Detener."""
        restante = float(segundos)
        while restante > 0:
            if controles.detener.is_set():
                return False
            if contar:
                ui.estado(f"Siguiente publicación en {_mmss(restante)} (cuenta «{nombre_cuenta}»)")
            paso = min(1.0, restante)
            dormir(paso)
            restante -= paso
        return not controles.detener.is_set()

    def publicada_ok() -> None:
        nonlocal publicadas, errores_seguidos
        publicadas += 1
        errores_seguidos = 0
        n = historial.publicadas_hoy_cuenta(cuenta_real, hoy)
        if n in AVISOS_PUBLICADAS:
            ui.aviso("amarillo", f"«{nombre_cuenta}» lleva {n} publicaciones hoy: el riesgo de bloqueo sube.")

    for orden, pub in enumerate(pendientes):
        indice = tira.publicaciones.index(pub) + 1
        if orden > 0 and ritmo.automatico:
            espera = rng.uniform(ritmo.espera_min, ritmo.espera_max) * 60
            if not esperar(espera, contar=True):
                return fin("detenida")
        controles.saltar.clear()
        grupo: Grupo | None = None
        cuenta_confirmada = False
        while True:
            if controles.detener.is_set():
                return fin("detenida")
            if cuenta and not cuenta_confirmada:
                # Antes de cada publicación se confirma la cuenta activa (alguien pudo cambiarla, o al volver
                # a iniciar sesión Facebook regresa al perfil personal).
                try:
                    fb.asegurar_cuenta(cuenta)
                except CuentaBloqueada as e:
                    return bloqueo(pub, None, None, e)
                except SesionCerrada:
                    resp = ui.preguntar("Facebook pide iniciar sesión. Inicia sesión en el navegador y da clic en "
                                        "Continuar.", ["Continuar", DETENER])
                    if resp == DETENER:
                        return fin("detenida")
                    continue
                except ErrorFacebook as e:
                    ui.aviso("rojo", f"No se pudo confirmar que esté activa la cuenta «{cuenta}»: {e} "
                                     "Se detuvo para no publicar con otra cuenta.")
                    return fin("detenida")
                cuenta_confirmada = True
            controles.saltar.clear()
            if grupo is None:
                grupo = elegir_grupo(cargar_grupos(ruta_grupos), historial, ahora(), minutos, excluir, rng,
                                     cuenta=filtro_cuenta)
                if grupo is None:
                    ui.estado("No hay grupos disponibles ahora. Intenta más tarde o actualiza los grupos.")
                    return fin("sin_grupos")
                excluir.add(grupo.link)
            ui.progreso(indice, total, pub.titulo, grupo.nombre)
            ui.estado(f"Preparando publicación {indice} de {total} en «{grupo.nombre}»…")

            ubicacion = rng.choice(tira.ubicaciones)
            try:
                fb.preparar_publicacion(grupo.link, pub.texto, [pub.imagen, ubicacion])
            except CuentaBloqueada as e:
                return bloqueo(pub, grupo, ubicacion, e)
            except SesionCerrada:
                resp = ui.preguntar("Facebook pide iniciar sesión. Inicia sesión en el navegador y da clic en "
                                    "Continuar.", ["Continuar", DETENER])
                if resp == DETENER:
                    return fin("detenida")
                cuenta_confirmada = False
                continue  # mismo grupo
            except GrupoSinPermiso as e:
                registrar(pub, grupo, ubicacion, "error")
                fb.cerrar_compositor()
                if ritmo.automatico:
                    ignorar(grupo, "sin permiso")
                    ui.estado(f"«{grupo.nombre}» no deja publicar a «{nombre_cuenta}» ({e}); "
                              "se ignora en esta cuenta y se usa otro grupo.")
                    if not contar_error():
                        return fin("detenida")
                else:
                    resp = ui.preguntar(f"Parece que «{nombre_cuenta}» no puede publicar en «{grupo.nombre}» ({e}). "
                                        "¿Lo ignoro en esta cuenta?", [IGNORAR_EN_CUENTA, SOLO_SALTAR, DETENER])
                    if resp == DETENER:
                        return fin("detenida")
                    if resp == IGNORAR_EN_CUENTA:
                        ignorar(grupo, "sin permiso")
                saltadas += 1
                grupo = None
                continue
            except ErrorFacebook as e:
                ruta = fb.captura(f"error_{nombre_tira}_{pub.numero}")
                registrar(pub, grupo, ubicacion, "error")
                if ritmo.automatico:
                    fb.cerrar_compositor()
                    ui.estado(f"No se pudo preparar en «{grupo.nombre}» ({e}). Se prueba otro grupo.")
                    saltadas += 1
                    grupo = None
                    if not contar_error():
                        return fin("detenida")
                    continue
                resp = ui.preguntar(f"No se pudo preparar la publicación en «{grupo.nombre}»: {e}\n"
                                    f"Captura guardada en {ruta}", [REINTENTAR, SALTAR, DETENER])
                if resp == REINTENTAR:
                    continue
                fb.cerrar_compositor()
                if resp == DETENER:
                    return fin("detenida")
                ignorar(grupo)
                saltadas += 1
                grupo = None
                continue

            espera_resultado = controles
            if ritmo.automatico:
                ui.estado(f"Revisando antes de publicar en «{grupo.nombre}»…")
                if not esperar(rng.uniform(*PAUSA_REVISION_S), contar=False):
                    fb.cerrar_compositor()
                    return fin("detenida")
                try:
                    clic = fb.publicar(controles)
                except CuentaBloqueada as e:
                    return bloqueo(pub, grupo, ubicacion, e)
                except ErrorFacebook as e:
                    fb.captura(f"error_publicar_{nombre_tira}_{pub.numero}")
                    registrar(pub, grupo, ubicacion, "error")
                    fb.cerrar_compositor()
                    ui.estado(f"No se pudo dar clic en Publicar en «{grupo.nombre}» ({e}). Se prueba otro grupo.")
                    saltadas += 1
                    grupo = None
                    if not contar_error():
                        return fin("detenida")
                    continue
                if not clic:  # se apretó Detener o Saltar antes del clic
                    fb.cerrar_compositor()
                    if controles.detener.is_set():
                        return fin("detenida")
                    registrar(pub, grupo, ubicacion, "saltado")
                    ignorar(grupo)
                    saltadas += 1
                    grupo = None
                    continue
                # Ya se dio clic: Saltar y Detener se ignoran hasta saber el resultado (si no, se repetiría el
                # anuncio en otro grupo). Detener se atiende en cuanto termine.
                controles.saltar.clear()
                espera_resultado = Controles(limite_s=LIMITE_TRAS_CLIC_S)
                ui.estado(f"Publicando en «{grupo.nombre}»… ({indice} de {total})")
            else:
                ui.estado(f"Esperando a que des clic en Publicar… ({indice} de {total}, «{grupo.nombre}»)")

            try:
                res = fb.esperar_resultado(espera_resultado)
            except CuentaBloqueada as e:
                return bloqueo(pub, grupo, ubicacion, e)

            if res == "publicado":
                registrar(pub, grupo, ubicacion, "publicado")
                publicada_ok()
                break
            if res == "detener":
                fb.cerrar_compositor()
                return fin("detenida")
            if res == "sin_respuesta":
                fb.captura(f"sin_respuesta_{nombre_tira}_{pub.numero}")
                fb.cerrar_compositor()
                registrar(pub, grupo, ubicacion, "error")
                ui.estado(f"La publicación en «{grupo.nombre}» no terminó a tiempo. Se sigue con la siguiente.")
                if not contar_error():
                    return fin("detenida")
                break
            if res == "fallo":
                registrar(pub, grupo, ubicacion, "error")
                if ritmo.automatico:
                    # Si en realidad sí salió, así no se repite el anuncio en otro grupo.
                    ui.estado(f"Facebook mostró un error al publicar en «{grupo.nombre}». "
                              "Se sigue con la siguiente publicación.")
                    if not contar_error():
                        return fin("detenida")
                    break
                resp = ui.preguntar(f"Facebook mostró un error al publicar en «{grupo.nombre}». "
                                    "Revisa el grupo en el navegador.",
                                    [REINTENTAR, SI_SE_PUBLICO, SALTAR, DETENER])
                if resp == REINTENTAR:
                    continue
                if resp == SI_SE_PUBLICO:
                    registrar(pub, grupo, ubicacion, "publicado")
                    publicada_ok()
                    break
                if resp == DETENER:
                    return fin("detenida")
                saltadas += 1
                grupo = None
                continue
            registrar(pub, grupo, ubicacion, "saltado")
            saltadas += 1
            if res == "saltar":
                fb.cerrar_compositor()
                ignorar(grupo)
            grupo = None

    ui.estado(f"{nombre_tira} terminada ✅ ({publicadas} publicadas) con «{nombre_cuenta}»")
    return fin("terminada")
