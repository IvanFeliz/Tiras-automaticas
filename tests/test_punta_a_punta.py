"""Corrida completa con navegador real: secuencia + control de Facebook contra páginas falsas por HTTP."""
import functools
import http.server
import random
import threading
from datetime import datetime
from pathlib import Path

import pytest

from publicador.facebook import Facebook
from publicador.historial import Historial
from publicador.sesion import Controles, Ritmo, ejecutar_tira
from publicador.tira import leer_tira

DATOS = Path(__file__).parent / "datos"


class _Silencioso(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


@pytest.fixture(scope="module")
def servidor():
    h = functools.partial(_Silencioso, directory=str(DATOS))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), h)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


class UI:
    def __init__(self):
        self.estados, self.avisos, self.preguntas = [], [], []

    def estado(self, m):
        self.estados.append(m)

    def progreso(self, *a):
        pass

    def aviso(self, n, m):
        self.avisos.append((n, m))

    def preguntar(self, m, o):
        self.preguntas.append(m)
        for preferida in ("Ignorarlo en esta cuenta", "Saltar este grupo"):
            if preferida in o:
                return preferida
        return o[0]


@pytest.fixture
def tira(tmp_path):
    c = tmp_path / "1.lunes" / "TIRA 1"
    c.mkdir(parents=True)
    (c / "0 TEXTOS TIRA.txt").write_bytes((DATOS / "0 TEXTOS TIRA.txt").read_bytes())
    for i in range(1, 13):
        (c / f"{i} IMG.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    for n in ("000.LOCAL.jpeg", "0.CROQUIS.jpg", "0.VIDEO.mp4"):
        (c / n).write_bytes(b"x")
    t = leer_tira(c)
    assert t.ok
    t.publicaciones = t.publicaciones[:3]  # 3 anuncios bastan
    return t


@pytest.mark.parametrize("modo", ["automatico", "revision"])
def test_tira_completa_con_navegador(tmp_path, servidor, tira, modo):
    fb = Facebook(tmp_path / "perfil", tmp_path / "capturas", canales=(None,), headless=True)
    try:
        fb.abrir()
    except Exception as e:
        pytest.skip(f"sin navegador: {e}")
    fb.url_inicio = f"{servidor}/menu_cuentas_falso.html"
    fb.pausa_cambio_s = 0.2
    grupos = tmp_path / "grupos.txt"
    especiales = {2: "?sin_permiso=1", 4: "?falla=1"}
    grupos.write_text("".join(f"G{i} | {servidor}/grupo_falso.html{especiales.get(i, '?g=' + str(i))}\n"
                              for i in range(1, 8)), encoding="utf-8")
    h = Historial(tmp_path / "h.csv", "Reparaciones Gigabyte")
    controles = Controles()
    ui = UI()
    if modo == "revision":
        # La persona da clic en Publicar en cuanto aparece el compositor.
        orig = fb.esperar_resultado

        def esperar(c):
            try:
                fb.pagina.locator("#publicar").click(timeout=5000)
            except Exception:
                pass
            return orig(c)
        fb.esperar_resultado = esperar
    try:
        r = ejecutar_tira(tira, "1.lunes", "TIRA 1", fb, ui, controles, grupos, h, 60,
                          rng=random.Random(3), cuenta="Gigabyte Sucursal Norte",
                          ritmo=Ritmo(modo, 2, 2), dormir=lambda s: None)
        assert fb.cuenta_actual() == "Gigabyte Sucursal Norte"
    finally:
        fb.cerrar()
    filas = h._filas()
    publicados = [f for f in filas if f["resultado"] == "publicado"]
    assert r.motivo_fin == "terminada", (r, ui.estados[-3:], ui.preguntas)
    assert r.publicadas == len(publicados)
    assert len({f["link_grupo"] for f in publicados}) == len(publicados)
    assert all(f["cuenta"] == "Gigabyte Sucursal Norte" for f in filas)
    # El grupo sin permiso no recibió nada.
    assert not any("sin_permiso" in f["link_grupo"] for f in publicados)
