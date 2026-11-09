import random
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from publicador.grupos import cargar_grupos
from publicador.historial import Historial, Registro
from publicador.sesion import Controles, ErrorFacebook, ejecutar_tira
from publicador.tira import Publicacion, Tira

HOY = datetime(2026, 11, 9, 10, 0)


class Reloj:
    def __init__(self):
        self.t = HOY

    def __call__(self):
        self.t += timedelta(seconds=30)
        return self.t


class FakeFB:
    def __init__(self, resultados=(), errores=0, sesion=(True,)):
        self.resultados = list(resultados)
        self.errores = errores
        self.sesion = list(sesion)
        self.preparadas: list[tuple[str, str, list[Path]]] = []
        self.cerrados = 0
        self.capturas = 0
        self.publicaciones_auto = 0

    def sesion_activa(self):
        return self.sesion.pop(0) if len(self.sesion) > 1 else self.sesion[0]

    def preparar_publicacion(self, link, texto, archivos):
        self.preparadas.append((link, texto, archivos))
        if self.errores:
            self.errores -= 1
            raise ErrorFacebook("no abrió")

    def esperar_resultado(self, controles):
        return self.resultados.pop(0) if self.resultados else "publicado"

    def cerrar_compositor(self):
        self.cerrados += 1

    def publicar(self):
        self.publicaciones_auto += 1

    def captura(self, nombre):
        self.capturas += 1
        return Path("c.png")


class FakeUI:
    def __init__(self, respuestas=()):
        self.respuestas = list(respuestas)
        self.estados: list[str] = []
        self.preguntas: list[str] = []
        self.avisos: list[tuple[str, str]] = []

    def aviso(self, nivel, mensaje):
        self.avisos.append((nivel, mensaje))

    def estado(self, m):
        self.estados.append(m)

    def progreso(self, actual, total, titulo, grupo):
        pass

    def preguntar(self, mensaje, opciones):
        self.preguntas.append(mensaje)
        return self.respuestas.pop(0) if self.respuestas else opciones[0]


@pytest.fixture
def entorno(tmp_path):
    def armar(n_pubs=3, n_grupos=5):
        pubs = [Publicacion(i, f"T{i}", f"Texto {i}", tmp_path / f"{i} I.png") for i in range(1, n_pubs + 1)]
        tira = Tira(tmp_path, pubs, [tmp_path / "0.A.jpg", tmp_path / "0.B.mp4"], [])
        rg = tmp_path / "grupos.txt"
        rg.write_text("".join(f"G{i} | https://fb/groups/{i}/\n" for i in range(1, n_grupos + 1)), encoding="utf-8")
        return tira, rg, Historial(tmp_path / "h.csv")
    return armar


def _correr(tira, rg, h, fb, ui, controles=None):
    return ejecutar_tira(tira, "1.lunes", "TIRA 1", fb, ui, controles or Controles(), rg, h, 60,
                         ahora=Reloj(), rng=random.Random(0))


def _resultados(h):
    return [(f["numero"], f["link_grupo"], f["resultado"]) for f in h._filas()]


def test_todo_publicado(entorno):
    tira, rg, h = entorno()
    fb, ui = FakeFB(), FakeUI()
    r = _correr(tira, rg, h, fb, ui)
    assert (r.publicadas, r.saltadas, r.motivo_fin) == (3, 0, "terminada")
    links = [p[0] for p in fb.preparadas]
    assert len(set(links)) == 3
    assert [x[2] for x in _resultados(h)] == ["publicado"] * 3
    texto, archivos = fb.preparadas[0][1], fb.preparadas[0][2]
    assert texto == "Texto 1"
    assert archivos[0].name == "1 I.png" and archivos[1] in tira.ubicaciones
    assert any("TIRA 1 terminada ✅ (3 publicadas)" in e for e in ui.estados)


def test_saltar_marca_y_reintenta(entorno):
    tira, rg, h = entorno(n_pubs=1)
    fb = FakeFB(["saltar", "publicado"])
    r = _correr(tira, rg, h, fb, FakeUI())
    primero, segundo = fb.preparadas[0][0], fb.preparadas[1][0]
    assert primero != segundo
    assert fb.cerrados == 1
    assert {g.link: g.activo for g in cargar_grupos(rg)}[primero] is False
    assert (r.publicadas, r.saltadas) == (1, 1)
    assert _resultados(h)[0] == ("1", primero, "saltado")


def test_cerrado_no_marca(entorno):
    tira, rg, h = entorno(n_pubs=1)
    fb = FakeFB(["cerrado", "publicado"])
    _correr(tira, rg, h, fb, FakeUI())
    primero = fb.preparadas[0][0]
    assert {g.link: g.activo for g in cargar_grupos(rg)}[primero] is True
    assert _resultados(h)[0][2] == "saltado"
    assert fb.preparadas[1][0] != primero


def test_error_reintentar(entorno):
    tira, rg, h = entorno(n_pubs=1)
    fb, ui = FakeFB(errores=1), FakeUI(["Reintentar"])
    r = _correr(tira, rg, h, fb, ui)
    assert fb.preparadas[0][0] == fb.preparadas[1][0]
    assert fb.capturas == 1
    assert [x[2] for x in _resultados(h)] == ["error", "publicado"]
    assert r.publicadas == 1


def test_error_saltar_grupo(entorno):
    tira, rg, h = entorno(n_pubs=1)
    fb, ui = FakeFB(errores=1), FakeUI(["Saltar este grupo"])
    _correr(tira, rg, h, fb, ui)
    primero = fb.preparadas[0][0]
    assert fb.preparadas[1][0] != primero
    assert {g.link: g.activo for g in cargar_grupos(rg)}[primero] is False


def test_error_detener(entorno):
    tira, rg, h = entorno(n_pubs=2)
    fb, ui = FakeFB(errores=1), FakeUI(["Detener"])
    r = _correr(tira, rg, h, fb, ui)
    assert (r.publicadas, r.motivo_fin) == (0, "detenida")
    assert len(fb.preparadas) == 1


def test_detener(entorno):
    tira, rg, h = entorno()
    fb = FakeFB(["publicado", "detener"])
    r = _correr(tira, rg, h, fb, FakeUI())
    assert (r.publicadas, r.saltadas, r.motivo_fin) == (1, 0, "detenida")
    assert fb.cerrados == 1


def test_detener_antes_de_empezar(entorno):
    tira, rg, h = entorno()
    c = Controles()
    c.detener.set()
    fb = FakeFB()
    r = _correr(tira, rg, h, fb, FakeUI(), c)
    assert r.motivo_fin == "detenida" and fb.preparadas == []


def test_reanudar(entorno):
    tira, rg, h = entorno()
    h.agregar(Registro(HOY - timedelta(hours=2), "1.lunes", "TIRA 1", 1, "T1", "G1", "https://fb/groups/1/", "a", "publicado"))
    fb = FakeFB()
    r = _correr(tira, rg, h, fb, FakeUI())
    assert [p[1] for p in fb.preparadas] == ["Texto 2", "Texto 3"]
    assert "https://fb/groups/1/" not in [p[0] for p in fb.preparadas]
    assert r.publicadas == 2


def test_sin_grupos(entorno):
    tira, rg, h = entorno(n_pubs=2, n_grupos=1)
    ui = FakeUI()
    r = _correr(tira, rg, h, FakeFB(), ui)
    assert (r.publicadas, r.saltadas, r.motivo_fin) == (1, 0, "sin_grupos")
    assert any("No hay grupos disponibles" in e for e in ui.estados)


# --- Correcciones de la revisión final ------------------------------------------------
from publicador.sesion import NavegadorCerrado, SesionCerrada  # noqa: E402


class FBExcepciones(FakeFB):
    def __init__(self, excepciones, **kw):
        super().__init__(**kw)
        self.excepciones = list(excepciones)

    def preparar_publicacion(self, link, texto, archivos):
        self.preparadas.append((link, texto, archivos))
        if self.excepciones:
            raise self.excepciones.pop(0)


def test_sesion_cerrada_pide_login_y_reintenta_mismo_grupo(entorno):
    tira, rg, h = entorno(n_pubs=1)
    fb, ui = FBExcepciones([SesionCerrada()]), FakeUI(["Continuar"])
    r = _correr(tira, rg, h, fb, ui)
    assert any("Inicia sesión" in p for p in ui.preguntas)
    assert fb.preparadas[0][0] == fb.preparadas[1][0]
    assert [x[2] for x in _resultados(h)] == ["publicado"]
    assert all(g.activo for g in cargar_grupos(rg))
    assert r.publicadas == 1


def test_sesion_cerrada_y_detener(entorno):
    tira, rg, h = entorno(n_pubs=1)
    fb, ui = FBExcepciones([SesionCerrada()]), FakeUI(["Detener"])
    r = _correr(tira, rg, h, fb, ui)
    assert r.motivo_fin == "detenida" and _resultados(h) == []


def test_navegador_cerrado_no_marca_ni_registra(entorno):
    tira, rg, h = entorno(n_pubs=1)
    fb = FBExcepciones([NavegadorCerrado()])
    with pytest.raises(NavegadorCerrado):
        _correr(tira, rg, h, fb, FakeUI())
    assert _resultados(h) == []
    assert all(g.activo for g in cargar_grupos(rg))


class HistorialBloqueado(Historial):
    def __init__(self, ruta, fallos):
        super().__init__(ruta)
        self.fallos = fallos

    def agregar(self, r):
        if self.fallos:
            self.fallos -= 1
            raise PermissionError("historial.csv abierto en Excel")
        super().agregar(r)


def test_historial_bloqueado_por_excel(entorno, tmp_path):
    tira, rg, _ = entorno(n_pubs=1)
    h = HistorialBloqueado(tmp_path / "h.csv", fallos=1)
    ui = FakeUI(["Reintentar"])
    r = _correr(tira, rg, h, FakeFB(), ui)
    assert any("Excel" in p for p in ui.preguntas)
    assert [x[2] for x in _resultados(h)] == ["publicado"]
    assert r.publicadas == 1


def test_fallo_de_facebook_al_publicar(entorno):
    tira, rg, h = entorno(n_pubs=1)
    fb, ui = FakeFB(["fallo", "publicado"]), FakeUI(["Reintentar"])
    r = _correr(tira, rg, h, fb, ui)
    assert any("Facebook mostró un error" in p for p in ui.preguntas)
    assert [x[2] for x in _resultados(h)] == ["error", "publicado"]
    assert fb.preparadas[0][0] == fb.preparadas[1][0]
    assert r.publicadas == 1


def test_fallo_pero_si_se_publico(entorno):
    tira, rg, h = entorno(n_pubs=2)
    fb, ui = FakeFB(["fallo", "publicado"]), FakeUI(["Sí se publicó"])
    r = _correr(tira, rg, h, fb, ui)
    assert [p[1] for p in fb.preparadas] == ["Texto 1", "Texto 2"]
    assert [x[2] for x in _resultados(h)] == ["error", "publicado", "publicado"]
    assert r.publicadas == 2


def test_no_poder_marcar_grupo_no_detiene(entorno, monkeypatch):
    tira, rg, h = entorno(n_pubs=1)

    def falla(*a, **k):
        raise PermissionError("grupos.txt bloqueado")
    monkeypatch.setattr("publicador.sesion.marcar_ignorado", falla)
    ui = FakeUI()
    r = _correr(tira, rg, h, FakeFB(["saltar", "publicado"]), ui)
    assert r.publicadas == 1
    assert any("grupos.txt" in e for e in ui.estados)



# --- Cuentas y modo automático --------------------------------------------------------
from publicador.sesion import CuentaBloqueada, GrupoSinPermiso, Ritmo  # noqa: E402

AUTO = Ritmo(modo="automatico", espera_min=2, espera_max=3)


def _auto(tira, rg, h, fb, ui, controles=None, cuenta="Suc", dormir=None, ritmo=AUTO):
    esperas = []
    return ejecutar_tira(tira, "1.lunes", "TIRA 1", fb, ui, controles or Controles(), rg, h, 60,
                         ahora=Reloj(), rng=random.Random(0), cuenta=cuenta, ritmo=ritmo,
                         dormir=dormir or esperas.append), esperas


def test_auto_publica_solo_y_espera(entorno):
    tira, rg, h = entorno(n_pubs=3)
    fb, ui = FakeFB(), FakeUI()
    esperas = []
    r = ejecutar_tira(tira, "1.lunes", "TIRA 1", fb, ui, Controles(), rg, h, 60, ahora=Reloj(),
                      rng=random.Random(0), cuenta="Suc", ritmo=AUTO, dormir=esperas.append)
    assert r.publicadas == 3 and fb.publicaciones_auto == 3
    total = sum(esperas)
    assert 3 * 5 + 2 * 120 <= total <= 3 * 15 + 2 * 180
    assert any("Siguiente publicación en" in e for e in ui.estados)
    assert ui.preguntas == []
    assert {f["cuenta"] for f in h._filas()} == {"Suc"}


def test_auto_detener_durante_espera(entorno):
    tira, rg, h = entorno(n_pubs=3)
    c = Controles()
    fb = FakeFB()
    llamadas = []

    def dormir(seg):
        llamadas.append(seg)
        if fb.publicaciones_auto == 1 and len(llamadas) > 30:
            c.detener.set()
    r, _ = _auto(tira, rg, h, fb, FakeUI(), controles=c, dormir=dormir)
    assert (r.publicadas, r.motivo_fin) == (1, "detenida")
    assert len(llamadas) < 200


def test_grupo_sin_permiso_se_ignora_sin_preguntar(entorno):
    tira, rg, h = entorno(n_pubs=1)
    fb, ui = FBExcepciones([GrupoSinPermiso("no deja publicar")]), FakeUI()
    r, _ = _auto(tira, rg, h, fb, ui)
    primero = fb.preparadas[0][0]
    assert {g.link: g.activo for g in cargar_grupos(rg)}[primero] is False
    assert ui.preguntas == [] and r.publicadas == 1


def test_grupo_sin_permiso_tambien_en_revision(entorno):
    tira, rg, h = entorno(n_pubs=1)
    fb, ui = FBExcepciones([GrupoSinPermiso("no deja publicar")]), FakeUI()
    _correr(tira, rg, h, fb, ui)
    assert {g.link: g.activo for g in cargar_grupos(rg)}[fb.preparadas[0][0]] is False
    assert ui.preguntas == []


def test_error_en_auto_prueba_otro_grupo_sin_preguntar(entorno):
    tira, rg, h = entorno(n_pubs=1)
    fb, ui = FBExcepciones([ErrorFacebook("raro")]), FakeUI()
    r, _ = _auto(tira, rg, h, fb, ui)
    assert ui.preguntas == []
    assert fb.preparadas[0][0] != fb.preparadas[1][0]
    assert all(g.activo for g in cargar_grupos(rg))
    assert r.publicadas == 1


def test_fallo_en_auto_pasa_a_la_siguiente(entorno):
    tira, rg, h = entorno(n_pubs=2)
    fb, ui = FakeFB(["fallo", "publicado"]), FakeUI()
    r, _ = _auto(tira, rg, h, fb, ui)
    assert [p[1] for p in fb.preparadas] == ["Texto 1", "Texto 2"]
    assert [x[2] for x in _resultados(h)] == ["error", "publicado"]
    assert ui.preguntas == [] and r.publicadas == 1


def test_bloqueo_detiene_y_avisa(entorno):
    tira, rg, h = entorno(n_pubs=2)
    fb, ui = FBExcepciones([CuentaBloqueada("Estás bloqueado temporalmente")]), FakeUI()
    r, _ = _auto(tira, rg, h, fb, ui)
    assert r.motivo_fin == "bloqueada" and r.cuenta_bloqueada == "Suc"
    assert "bloqueado" in r.mensaje_bloqueo
    assert any(n == "rojo" for n, _ in ui.avisos)
    assert h.bloqueada_hoy("Suc", HOY.date())
    assert len(fb.preparadas) == 1


def test_bloqueo_despues_de_publicar(entorno):
    tira, rg, h = entorno(n_pubs=2)

    class FBBloqueoTras(FakeFB):
        def esperar_resultado(self, controles):
            raise CuentaBloqueada("Confirma tu identidad")
    r, _ = _auto(tira, rg, h, FBBloqueoTras(), FakeUI())
    assert r.motivo_fin == "bloqueada" and r.publicadas == 0


def test_aviso_24_publicaciones(entorno):
    tira, rg, h = entorno(n_pubs=1)
    for i in range(23):
        h.agregar(Registro(HOY, "1.lunes", "TIRA 9", i, "x", "G", f"Lx{i}", "u", "publicado", "Suc"))
    ui = FakeUI()
    _auto(tira, rg, h, FakeFB(), ui)
    assert any(n == "amarillo" and "24" in m for n, m in ui.avisos)


def test_aviso_tres_errores_seguidos(entorno):
    tira, rg, h = entorno(n_pubs=1, n_grupos=6)
    fb, ui = FBExcepciones([ErrorFacebook("a"), ErrorFacebook("b"), ErrorFacebook("c")]), FakeUI()
    r, _ = _auto(tira, rg, h, fb, ui)
    assert any(n == "amarillo" and "limitando" in m for n, m in ui.avisos)
    assert r.publicadas == 1


def test_reanudar_con_otra_cuenta_no_repite(entorno):
    tira, rg, h = entorno(n_pubs=3)
    h.agregar(Registro(HOY - timedelta(hours=1), "1.lunes", "TIRA 1", 1, "T1", "G1", "https://fb/groups/1/",
                       "a", "publicado", "Yo"))
    fb = FakeFB()
    _auto(tira, rg, h, fb, FakeUI(), cuenta="Suc")
    assert [p[1] for p in fb.preparadas] == ["Texto 2", "Texto 3"]
