import shutil
from pathlib import Path

import pytest

tk = pytest.importorskip("tkinter")

from publicador.config import Config, guardar_config  # noqa: E402

DATOS = Path(__file__).parent / "datos"
IMAGENES = [f"{i} IMG{i}.png" for i in range(1, 13)]
UBIC = ["000.ALTAMIRANO.jpeg", "0.CROQUIS ALTAMIRANO.jpg", "0.UBICACION ALTAMIRANO.mp4"]


@pytest.fixture
def ventana(tmp_path):
    tiras = tmp_path / "Tiras"
    for dia in ["2 MARTES", "1.lunes"]:
        for n in ["TIRA 2", "TIRA 1", "TIRA 10"]:
            c = tiras / dia / n
            c.mkdir(parents=True)
            shutil.copy(DATOS / "0 TEXTOS TIRA.txt", c / "0 TEXTOS TIRA.txt")
            for f in IMAGENES + UBIC:
                (c / f).write_bytes(b"x")
    datos = tmp_path / "datos"
    datos.mkdir()
    guardar_config(datos / "config.json", Config(carpeta_tiras=str(tiras), ultimo_dia="1.lunes", ultima_tira="TIRA 1"))
    from publicador.app import crear_ventana
    try:
        root = crear_ventana(datos)
    except tk.TclError as e:
        pytest.skip(f"sin pantalla: {e}")
    root.update()
    yield root, tiras
    root.app.trabajador.comandos.put(("salir",))
    try:
        root.destroy()
    except tk.TclError:
        pass  # la prueba ya cerró la ventana


def test_restaura_y_muestra_resumen(ventana):
    root, _ = ventana
    app = root.app
    assert list(app.combo_dia["values"]) == ["1.lunes", "2 MARTES"]
    assert list(app.combo_tira["values"]) == ["TIRA 1", "TIRA 2", "TIRA 10"]
    texto = app.resumen.get("1.0", "end")
    assert "TIRA 1 — 1.lunes" in texto
    assert " 1. Cambio de Pantalla  →  1 IMG1.png" in texto
    assert "12. Teclado  →  12 IMG12.png" in texto
    assert "Ubicación: 3 archivos" in texto
    assert str(app.btn_empezar["state"]) == "normal"


def test_tira_con_error_desactiva_empezar(ventana):
    root, tiras = ventana
    (tiras / "2 MARTES" / "TIRA 2" / "5 IMG5.png").unlink()
    root.app.cargar_tira(tiras / "2 MARTES" / "TIRA 2")
    assert "Falta la imagen del texto 5" in root.app.resumen.get("1.0", "end")
    assert str(root.app.btn_empezar["state"]) == "disabled"


def test_empezar_sin_grupos_avisa(ventana, monkeypatch):
    root, _ = ventana
    avisos = []
    monkeypatch.setattr("publicador.app.messagebox.showinfo", lambda t, m: avisos.append(m))
    root.app._empezar()
    assert avisos and "Actualizar grupos" in avisos[0]
    assert root.app.trabajador.comandos.empty()


def test_botones_de_carpeta_bloqueados_mientras_corre(ventana):
    root, _ = ventana
    app = root.app
    app._marcar_corriendo(True, tira=True)
    assert str(app.btn_cambiar["state"]) == "disabled"
    assert str(app.btn_escoger["state"]) == "disabled"
    app._marcar_corriendo(False)
    assert str(app.btn_cambiar["state"]) == "normal"


def test_cerrar_con_pregunta_abierta_responde_detener(ventana):
    import queue
    root, _ = ventana
    app = root.app
    respuesta = queue.Queue()
    app.cola_ui.put(("preguntar", "¿Algo?", ["Reintentar", "Saltar este grupo", "Detener"], respuesta))
    root.after(200, app._al_cerrar)
    app._procesar_cola()
    assert respuesta.get(timeout=2) == "Detener"
