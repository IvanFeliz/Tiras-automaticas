"""La ventana con todo conectado (hilo de trabajo + secuencia) usando un Facebook falso."""
import shutil
import time
from pathlib import Path

import pytest

tk = pytest.importorskip("tkinter")

from publicador.config import Config, guardar_config  # noqa: E402
from publicador.cuentas import Cuenta, guardar_cuentas, ruta_grupos  # noqa: E402
from publicador.sesion import CuentaBloqueada  # noqa: E402

DATOS = Path(__file__).parent / "datos"


class Pagina:
    url = "https://www.facebook.com/"

    def goto(self, url):
        self.url = url


class FBFalso:
    """Lo mínimo que usa el hilo de trabajo."""

    def __init__(self, bloquear_en=None, lento=0.0):
        self.pagina = Pagina()
        self.cerrado = False
        self.publicadas = []
        self.cuenta = "Reparaciones Gigabyte"
        self.bloquear_en = bloquear_en
        self.lento = lento
        self._actual = None

    def sesion_activa(self):
        return True

    def cambiar_cuenta(self, nombre):
        self.cuenta = nombre

    asegurar_cuenta = cambiar_cuenta

    def preparar_publicacion(self, link, texto, archivos):
        time.sleep(self.lento)
        if self.bloquear_en is not None and len(self.publicadas) == self.bloquear_en and self.cuenta == "Centro":
            raise CuentaBloqueada("Estás bloqueado temporalmente")
        self._actual = (self.cuenta, link, texto)

    def publicar(self, controles=None):
        return not (controles and (controles.saltar.is_set() or controles.detener.is_set()))

    def esperar_resultado(self, controles):
        self.publicadas.append(self._actual)
        return "publicado"

    def cerrar_compositor(self):
        pass

    def captura(self, nombre):
        return Path("c.png")

    def cerrar(self):
        self.cerrado = True


@pytest.fixture
def ventana(tmp_path, monkeypatch):
    c = tmp_path / "Tiras" / "1.lunes" / "TIRA 1"
    c.mkdir(parents=True)
    shutil.copy(DATOS / "0 TEXTOS TIRA.txt", c / "0 TEXTOS TIRA.txt")
    for i in range(1, 13):
        (c / f"{i} IMG.png").write_bytes(b"x")
    (c / "0.CROQUIS.jpg").write_bytes(b"x")
    datos = tmp_path / "datos"
    datos.mkdir()
    guardar_config(datos / "config.json", Config(carpeta_tiras=str(tmp_path / "Tiras"), ultimo_dia="1.lunes",
                                                 ultima_tira="TIRA 1", modo="automatico", espera_min=2, espera_max=2))
    guardar_cuentas(datos / "cuentas.json", [Cuenta("Reparaciones Gigabyte", "perfil"), Cuenta("Centro", "pagina"),
                                             Cuenta("Norte", "pagina")], "Centro")
    for cuenta in ("Reparaciones Gigabyte", "Centro", "Norte"):
        r = ruta_grupos(datos, cuenta)
        r.parent.mkdir(exist_ok=True)
        r.write_text("".join(f"G{i} | https://www.facebook.com/groups/{i}/\n" for i in range(30)), encoding="utf-8")
    import functools
    import publicador.app as modulo_app
    from publicador.sesion import ejecutar_tira
    # Sin esperas reales de minutos entre publicaciones.
    monkeypatch.setattr(modulo_app, "ejecutar_tira", functools.partial(ejecutar_tira, dormir=lambda s: None))
    monkeypatch.setattr("publicador.app.messagebox.askyesno", lambda *a, **k: True)
    monkeypatch.setattr("publicador.app.messagebox.showwarning", lambda *a, **k: None)
    monkeypatch.setattr("publicador.app.messagebox.showinfo", lambda *a, **k: None)
    from publicador.app import crear_ventana
    try:
        root = crear_ventana(datos)
    except tk.TclError as e:
        pytest.skip(f"sin pantalla: {e}")
    yield root, datos
    try:
        root.app.trabajador.comandos.put(("salir",))
        root.destroy()
    except tk.TclError:
        pass


def _bombear(root, hasta, limite=20.0):
    fin = time.monotonic() + limite
    while time.monotonic() < fin:
        root.update()
        if hasta():
            return True
        time.sleep(0.02)
    return False


def test_empezar_publica_la_tira_completa(ventana):
    root, datos = ventana
    app = root.app
    fb = FBFalso()
    app.trabajador._navegador = lambda: fb
    assert str(app.btn_empezar["state"]) == "normal"
    app._empezar()
    assert str(app.btn_detener["state"]) == "normal" and str(app.combo_cuenta["state"]) == "disabled"
    assert _bombear(root, lambda: not app.corriendo), app.var_estado.get()
    assert "terminada" in app.var_estado.get()
    assert len(fb.publicadas) == 12 and {c for c, _, _ in fb.publicadas} == {"Centro"}
    assert len({l for _, l, _ in fb.publicadas}) == 12
    assert float(app.barra["value"]) == 0 and str(app.btn_empezar["state"]) == "normal"
    assert "hoy ya van 12" in app.var_chip.get()
    # Volver a empezar la misma tira el mismo día: avisa y no publica de nuevo.
    app._empezar()
    root.update()
    assert not app.corriendo and len(fb.publicadas) == 12


def test_bloqueo_y_seguir_con_otra_cuenta(ventana, monkeypatch):
    root, datos = ventana
    app = root.app
    fb = FBFalso(bloquear_en=5)
    app.trabajador._navegador = lambda: fb
    respuestas = iter(["Seguir con otra cuenta", "Norte"])
    monkeypatch.setattr(app, "_elegir_opcion", lambda m, o: next(respuestas))
    app._empezar()
    assert _bombear(root, lambda: not app.corriendo, 30), app.var_estado.get()
    textos = [t for _, _, t in fb.publicadas]
    assert len(textos) == 12 and len(set(textos)) == 12, "se repitió o faltó un anuncio"
    assert [c for c, _, _ in fb.publicadas] == ["Centro"] * 5 + ["Norte"] * 7
    assert app.combo_cuenta.get() == "Norte"
    assert app.historial.bloqueada_hoy("Centro", __import__("datetime").date.today())


def test_detener_a_media_tira(ventana):
    root, _ = ventana
    app = root.app
    fb = FBFalso(lento=0.05)
    app.trabajador._navegador = lambda: fb
    app._empezar()
    assert _bombear(root, lambda: len(fb.publicadas) >= 2)
    app._detener()
    assert _bombear(root, lambda: not app.corriendo)
    n = len(fb.publicadas)
    assert 2 <= n < 12 and "Detenido" in app.var_estado.get()
    time.sleep(0.3)
    root.update()
    assert len(fb.publicadas) == n, "siguió publicando después de Detener"


def test_cerrar_el_programa_mientras_publica(ventana):
    root, _ = ventana
    app = root.app
    fb = FBFalso(lento=0.05)
    app.trabajador._navegador = lambda: fb
    app.trabajador.fb = fb
    app._empezar()
    assert _bombear(root, lambda: len(fb.publicadas) >= 1)
    t0 = time.monotonic()
    app._al_cerrar()  # askyesno ya contesta que sí
    assert time.monotonic() - t0 < 5, "cerrar tardó demasiado"
    assert fb.cerrado and not app.trabajador.is_alive()
