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


def test_error_en_la_ventana_no_la_congela(ventana, monkeypatch):
    root, _ = ventana
    app = root.app
    monkeypatch.setattr(app, "_mostrar_tira", lambda *a: (_ for _ in ()).throw(PermissionError("USB")))
    monkeypatch.setattr("publicador.app.messagebox.showerror", lambda *a, **k: None)
    for ident in root.tk.call("after", "info"):
        root.after_cancel(ident)
    app.cola_ui.put(("fin", "listo"))
    app._procesar_cola()  # no debe lanzar
    assert root.tk.call("after", "info")  # se volvió a programar
    assert "PermissionError" in (app.datos / "errores.log").read_text(encoding="utf-8")


# --- Cuentas y modo automático --------------------------------------------------------
import json  # noqa: E402
import queue  # noqa: E402


@pytest.fixture
def ventana_cuentas(tmp_path):
    from publicador.app import crear_ventana
    datos = tmp_path / "datos"
    datos.mkdir()
    (datos / "cuentas.json").write_text(json.dumps({"cuentas": [
        {"nombre": "Reparaciones Gigabyte", "tipo": "perfil"},
        {"nombre": "Gigabyte Centro", "tipo": "pagina"},
        {"nombre": "Gigabyte Norte", "tipo": "pagina"}], "ultima": "Gigabyte Centro"}), encoding="utf-8")
    (datos / "grupos.txt").write_text("A | https://www.facebook.com/groups/1/\n", encoding="utf-8")
    try:
        root = crear_ventana(datos)
    except tk.TclError as e:
        pytest.skip(f"sin pantalla: {e}")
    root.update()
    root.app.trabajador.comandos = queue.Queue()  # que el hilo no abra un navegador en la prueba
    yield root, datos
    try:
        root.destroy()
    except tk.TclError:
        pass


def test_cuentas_en_la_ventana_y_migracion(ventana_cuentas):
    root, datos = ventana_cuentas
    app = root.app
    assert list(app.combo_cuenta["values"]) == ["Reparaciones Gigabyte", "Gigabyte Centro", "Gigabyte Norte"]
    assert app.combo_cuenta.get() == "Gigabyte Centro"
    from publicador.cuentas import ruta_grupos
    assert ruta_grupos(datos, "Reparaciones Gigabyte").exists()
    assert not (datos / "grupos.txt").exists()
    assert "sin grupos" in app.var_grupos.get()  # la Página todavía no tiene grupos


def test_aviso_de_riesgo_en_vivo(ventana_cuentas):
    root, _ = ventana_cuentas
    app = root.app
    app.var_modo.set("automatico")
    app.var_espera_min.set(2)
    app._revisar_riesgo()
    assert "alto" in app.var_aviso.get()
    app.var_espera_min.set(4)
    app._revisar_riesgo()
    assert "rápido" in app.var_aviso.get()
    app.var_espera_min.set(8)
    app._revisar_riesgo()
    assert app.var_aviso.get() == ""


def test_bloqueo_ofrece_seguir_con_otra_cuenta(ventana_cuentas, monkeypatch):
    root, _ = ventana_cuentas
    app = root.app
    from publicador.cuentas import ruta_grupos
    destino = ruta_grupos(app.datos, "Gigabyte Norte")
    destino.parent.mkdir(exist_ok=True)
    destino.write_text("N | https://www.facebook.com/groups/9/\n", encoding="utf-8")
    respuestas = iter(["Seguir con otra cuenta", "Gigabyte Norte"])
    monkeypatch.setattr(app, "_elegir_opcion", lambda mensaje, opciones: next(respuestas))
    app.corriendo = True
    tira_args = ("TIRA", "1.lunes", "TIRA 1")
    app.cola_ui.put(("bloqueada", "Gigabyte Centro", "Estás bloqueado", tira_args))
    app._procesar_cola()
    cmd = app.trabajador.comandos.get_nowait()
    assert cmd[0] == "tira" and cmd[1:4] == tira_args
    assert cmd[6] == "Gigabyte Norte"
    assert app.combo_cuenta.get() == "Gigabyte Norte"


def test_primera_vez_pregunta_cual_es_el_principal(ventana, monkeypatch):
    root, _ = ventana
    app = root.app
    preguntas = []

    def elegir(mensaje, opciones):
        preguntas.append((mensaje, opciones))
        return "Gigabyte Centro"
    monkeypatch.setattr(app, "_elegir_opcion", elegir)
    app._cuentas_encontradas([("Reparaciones Gigabyte", "perfil"), ("Gigabyte Centro", "pagina")])
    assert preguntas and "principal" in preguntas[0][0]
    assert {c.nombre: c.tipo for c in app.cuentas} == {"Reparaciones Gigabyte": "pagina", "Gigabyte Centro": "perfil"}
    assert app.historial.cuenta_principal == "Gigabyte Centro"


def test_cuentas_conocidas_no_cambian_de_principal(ventana_cuentas, monkeypatch):
    root, _ = ventana_cuentas
    app = root.app
    monkeypatch.setattr(app, "_elegir_opcion", lambda *a: (_ for _ in ()).throw(AssertionError("no debe preguntar")))
    # Facebook ahora lista primero una Página
    app._cuentas_encontradas([("Gigabyte Norte", "perfil"), ("Reparaciones Gigabyte", "pagina"),
                              ("Gigabyte Centro", "pagina")])
    assert app.historial.cuenta_principal == "Reparaciones Gigabyte"


def test_controles_de_ritmo_bloqueados_mientras_corre(ventana_cuentas):
    root, _ = ventana_cuentas
    app = root.app
    app._marcar_corriendo(True, tira=True)
    assert all(str(w["state"]) == "disabled" for w in app.controles_ritmo)
    app._marcar_corriendo(False)
    assert all(str(w["state"]) != "disabled" for w in app.controles_ritmo)


def test_seguir_no_ofrece_cuentas_bloqueadas_hoy(ventana_cuentas, monkeypatch):
    from datetime import datetime as _dt
    from publicador.historial import Registro
    root, _ = ventana_cuentas
    app = root.app
    app.historial.agregar(Registro(_dt.now(), "d", "t", 0, "", "", "", "", "bloqueo", "Gigabyte Norte"))
    vistas = []

    def elegir(mensaje, opciones):
        vistas.append(opciones)
        return "Seguir con otra cuenta" if len(vistas) == 1 else "Cancelar"
    monkeypatch.setattr(app, "_elegir_opcion", elegir)
    app.corriendo = True
    app._cuenta_bloqueada("Gigabyte Centro", "x", ("T", "d", "t"))
    assert "Gigabyte Norte" not in vistas[1] and "Reparaciones Gigabyte" in vistas[1]


# --- Diseño nuevo -------------------------------------------------------------------
def test_tres_pestanas(ventana):
    root, _ = ventana
    nb = root.app.pestanas
    assert [nb.tab(i, "text").split(" ", 1)[1] for i in range(nb.index("end"))] == [
        "Publicar", "Cuentas y grupos", "Ajustes"]


def test_etiqueta_de_estado_de_la_tira(ventana):
    root, tiras = ventana
    app = root.app
    assert "Lista para publicar: 12 anuncios" in app.var_chip.get()
    (tiras / "2 MARTES" / "TIRA 2" / "5 IMG5.png").unlink()
    app.cargar_tira(tiras / "2 MARTES" / "TIRA 2")
    assert app.var_chip.get().startswith("❌")


def test_barra_de_progreso(ventana):
    root, _ = ventana
    app = root.app
    app.cola_ui.put(("progreso", 4, 12, "Mantenimiento", "Grupo X"))
    app._procesar_mensajes()
    assert float(app.barra["value"]) == 4 and float(app.barra["maximum"]) == 12
    assert "4 de 12" in app.var_progreso.get()
    app.cola_ui.put(("fin", "listo"))
    app._procesar_mensajes()
    assert float(app.barra["value"]) == 0
