"""Miles de escenarios al azar contra la secuencia de publicación.

Un Facebook falso responde al azar (errores, bloqueos, sesión cerrada, la persona que salta, detiene o
cierra) y se revisa que, pase lo que pase, se cumplan las reglas que protegen la cuenta:
nunca se repite un anuncio, nunca se repite un grupo en la misma tira, se respeta el tiempo entre
publicaciones por cuenta, y lo que se reporta coincide con lo que de verdad se publicó.
"""
import random
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from publicador.cuentas import ruta_grupos
from publicador.grupos import cargar_grupos
from publicador.historial import Historial
from publicador.sesion import (Controles, CuentaBloqueada, ErrorFacebook, GrupoSinPermiso, Ritmo,
                               SesionCerrada, ejecutar_tira)
from publicador.tira import Publicacion, Tira

CUENTAS = ["Perfil", "Pagina Centro", "Pagina Norte"]
MINUTOS = 60


class Reloj:
    def __init__(self):
        self.t = datetime(2026, 11, 9, 8, 0, 0)

    def __call__(self):
        self.t += timedelta(seconds=1)
        return self.t

    def dormir(self, segundos):
        self.t += timedelta(seconds=segundos)


class BucleInfinito(AssertionError):
    pass


class FBAzar:
    """Facebook falso: cada llamada responde al azar. Lleva la cuenta de lo que DE VERDAD se publicó."""

    def __init__(self, rng, reloj, automatico, cuenta, reales, p_falla):
        self.rng, self.reloj, self.auto, self.cuenta = rng, reloj, automatico, cuenta
        self.reales = reales  # lista compartida: (momento, cuenta, link, texto)
        self.p = p_falla
        self.actual = None
        self.pasos = 0
        self.preparadas_tras_detener = 0
        self.controles = None
        self.clic = False
        self.fallo_publico = False  # en «fallo» con revisión: ¿sí salió? (la persona lo revisa)

    def _paso(self):
        self.pasos += 1
        if self.pasos > 5000:
            raise BucleInfinito("la tira no termina")

    def _azar(self, *excepciones):
        for exc, peso in excepciones:
            if self.rng.random() < self.p * peso:
                raise exc

    def asegurar_cuenta(self, nombre):
        self._paso()
        assert nombre == self.cuenta
        self._azar((SesionCerrada(), 0.3), (ErrorFacebook("menú"), 0.15), (CuentaBloqueada("checkpoint"), 0.1))

    def preparar_publicacion(self, link, texto, archivos):
        self._paso()
        if self.controles is not None and self.controles.detener.is_set():
            self.preparadas_tras_detener += 1
        assert len(archivos) == 2
        self.actual = None
        self.clic = False
        self._azar((GrupoSinPermiso("x"), 1.0), (ErrorFacebook("y"), 1.0), (SesionCerrada(), 0.4),
                   (CuentaBloqueada("bloqueado temporalmente"), 0.2))
        self.actual = (link, texto)

    def publicar(self, controles=None):
        self._paso()
        assert self.auto and self.actual is not None
        if controles is not None and (controles.saltar.is_set() or controles.detener.is_set()):
            return False
        self._azar((ErrorFacebook("botón"), 0.5), (CuentaBloqueada("restringida"), 0.1))
        self.clic = True
        return True

    def _publicar_de_verdad(self):
        self.reales.append((self.reloj.t, self.cuenta, self.actual[0], self.actual[1]))

    def esperar_resultado(self, controles):
        self._paso()
        assert self.actual is not None
        r = self.rng.random()
        if self.auto:
            assert self.clic, "en automático solo se espera el resultado después del clic"
            if r < self.p * 0.3:
                raise CuentaBloqueada("limitamos", publicado=self.rng.random() < 0.5 and self._pub())
            if r < self.p * 0.8:
                return "fallo"
            if r < self.p * 1.2:
                return "sin_respuesta"
            self._publicar_de_verdad()
            return "publicado"
        # Con revisión: la persona hace algo al azar.
        if r < self.p * 0.3:
            raise CuentaBloqueada("limitamos", publicado=self.rng.random() < 0.5 and self._pub())
        if r < self.p * 0.8:
            self.fallo_publico = self.rng.random() < 0.3
            if self.fallo_publico:
                self._publicar_de_verdad()
            return "fallo"
        if r < self.p * 1.3:
            return "cerrado"
        if r < self.p * 1.8:
            controles.saltar.set()
            return "saltar"
        if r < self.p * 2.1:
            controles.detener.set()
            return "detener"
        self._publicar_de_verdad()
        return "publicado"

    def _pub(self):
        self._publicar_de_verdad()
        return True

    def cerrar_compositor(self):
        self.actual = None

    def captura(self, nombre):
        return Path("captura.png")


class UIAzar:
    def __init__(self, rng, controles, p_detener, fb=None):
        self.rng, self.controles, self.p_detener, self.fb = rng, controles, p_detener, fb
        self.avisos = []
        self.estados = []

    def estado(self, m):
        self.estados.append(m)
        if self.rng.random() < self.p_detener:  # la persona aprieta botones en cualquier momento
            (self.controles.detener if self.rng.random() < 0.5 else self.controles.saltar).set()

    def progreso(self, actual, total, titulo, grupo):
        assert 1 <= actual <= total

    def aviso(self, nivel, mensaje):
        assert nivel in ("amarillo", "rojo")
        self.avisos.append((nivel, mensaje))

    def preguntar(self, mensaje, opciones):
        assert opciones
        if "Sí se publicó" in opciones and self.fb is not None:
            # La persona revisa el grupo y contesta la verdad.
            if self.fb.fallo_publico:
                return "Sí se publicó"
            return self.rng.choice([o for o in opciones if o != "Sí se publicó"])
        return self.rng.choice(opciones)


def _preparar(tmp_path, rng):
    n_grupos = rng.randint(1, 30)
    tiras = {}
    for nombre in ("TIRA 1", "TIRA 2"):
        n_pubs = rng.randint(1, 12)
        pubs = [Publicacion(i, f"T{i}", f"{nombre} · Texto {i}", tmp_path / f"{i} I.png")
                for i in range(1, n_pubs + 1)]
        tiras[nombre] = Tira(tmp_path, pubs, [tmp_path / "0.A.jpg", tmp_path / "0.B.mp4",
                                              tmp_path / "000.C.jpeg"], [])
    for c in CUENTAS:
        r = ruta_grupos(tmp_path, c)
        r.parent.mkdir(exist_ok=True)
        r.write_text("".join(f"G{i} | https://www.facebook.com/groups/{i}/\n" for i in range(n_grupos)),
                     encoding="utf-8")
    return tiras


def _correr_escenario(tmp_path, semilla):
    rng = random.Random(semilla)
    tiras = _preparar(tmp_path, rng)
    historial = Historial(tmp_path / "h.csv", "Perfil")
    reloj = Reloj()
    reales: list = []
    p_falla = rng.choice([0.0, 0.05, 0.15, 0.35])
    resumen = []
    for vuelta in range(rng.randint(1, 6)):  # se reanuda varias veces, a veces con otra cuenta u otra tira
        nombre_tira = rng.choice(list(tiras))
        tira = tiras[nombre_tira]
        cuenta = rng.choice(CUENTAS)
        auto = rng.random() < 0.5
        ritmo = Ritmo("automatico" if auto else "revision", 2, rng.randint(2, 6))
        controles = Controles()
        fb = FBAzar(rng, reloj, auto, cuenta, reales, p_falla)
        fb.controles = controles
        ui = UIAzar(rng, controles, rng.choice([0.0, 0.0, 0.002, 0.02]), fb)
        antes = len(reales)
        r = ejecutar_tira(tira, "1.lunes", nombre_tira, fb, ui, controles, ruta_grupos(tmp_path, cuenta),
                          historial, MINUTOS, ahora=reloj, rng=rng, cuenta=cuenta, ritmo=ritmo,
                          dormir=reloj.dormir)
        nuevas = len(reales) - antes
        resumen.append((cuenta, auto, r, nuevas))

        # --- Reglas que deben cumplirse SIEMPRE ---
        assert r.motivo_fin in ("terminada", "detenida", "sin_grupos", "bloqueada")
        assert r.publicadas == nuevas, f"reportó {r.publicadas} pero de verdad se publicaron {nuevas}"
        assert fb.preparadas_tras_detener == 0, "siguió preparando después de Detener"
        if r.motivo_fin == "bloqueada":
            assert r.cuenta_bloqueada == cuenta and any(n == "rojo" for n, _ in ui.avisos)
            assert historial.bloqueada_hoy(cuenta, reloj.t.date())
        if r.motivo_fin == "terminada" and not auto:
            hechas = historial.publicadas("1.lunes", nombre_tira, reloj.t.date())
            assert set(hechas) == {p.numero for p in tira.publicaciones}, "terminó sin publicar todo"
        reloj.dormir(rng.choice([5, 600, 4000]))

    # Nunca se repite un anuncio en el día.
    textos = [t for _, _, _, t in reales]
    assert len(textos) == len(set(textos)), f"anuncio repetido: {sorted(textos)}"
    # Nunca se usa el mismo grupo dos veces para la misma tira (con ninguna cuenta).
    for nombre in tiras:
        links = [l for _, _, l, t in reales if t.startswith(nombre)]
        assert len(links) == len(set(links)), f"grupo repetido en {nombre}"
    # Misma cuenta, mismo grupo: deben pasar al menos MINUTOS entre publicaciones.
    ultimo: dict = {}
    for momento, c, l, _ in sorted(reales):
        if (c, l) in ultimo:
            assert momento - ultimo[(c, l)] >= timedelta(minutes=MINUTOS) - timedelta(seconds=5), \
                f"{c} repitió {l} a los {momento - ultimo[(c, l)]}"
        ultimo[(c, l)] = momento
    # Todo lo que de verdad se publicó quedó anotado como publicado, con su cuenta.
    filas = [f for f in historial._filas() if f["resultado"] == "publicado"]
    assert sorted((f["link_grupo"], f["cuenta"]) for f in filas) == sorted((l, c) for _, c, l, _ in reales)
    # El historial se puede volver a leer completo y cada fila tiene resultado válido.
    for f in historial._filas():
        assert f["resultado"] in ("publicado", "saltado", "error", "bloqueo")
    # Los archivos de grupos siguen completos (no se pierden grupos).
    for c in CUENTAS:
        assert len(cargar_grupos(ruta_grupos(tmp_path, c))) >= 1
    return resumen


@pytest.mark.parametrize("bloque", range(20))
def test_escenarios_al_azar(tmp_path_factory, bloque):
    for i in range(150):
        semilla = bloque * 1000 + i
        carpeta = tmp_path_factory.mktemp(f"e{semilla}")
        try:
            _correr_escenario(carpeta, semilla)
        except Exception as e:
            raise AssertionError(f"falló el escenario con semilla {semilla}: {type(e).__name__}: {e}") from e
