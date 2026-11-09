from datetime import date, datetime

from publicador.historial import Historial, Registro


def _r(t, numero, link, resultado, tira="TIRA 1"):
    return Registro(t, "1.lunes", tira, numero, f"T{numero}", f"G-{link}", link, "000.ALTAMIRANO.jpeg", resultado)


def test_agregar_y_consultar(tmp_path):
    h = Historial(tmp_path / "h.csv")
    t = datetime(2026, 11, 9, 10, 0)
    h.agregar(_r(t, 1, "L1", "publicado"))
    h.agregar(_r(t.replace(hour=11), 2, "L2", "saltado"))
    h.agregar(_r(t.replace(hour=12), 3, "L3", "publicado", tira="TIRA 2"))
    assert h.ultima_publicacion("L1") == t
    assert h.ultima_publicacion("L2") is None
    assert h.publicadas("1.lunes", "TIRA 1", t.date()) == {1: "L1"}
    assert h.grupos_usados("1.lunes", "TIRA 1", t.date()) == {"L1", "L2"}
    assert h.publicadas("1.lunes", "TIRA 1", date(2026, 11, 10)) == {}
    assert (tmp_path / "h.csv").read_bytes().startswith(b"\xef\xbb\xbf")


def test_ultima_es_la_mas_reciente(tmp_path):
    h = Historial(tmp_path / "h.csv")
    h.agregar(_r(datetime(2026, 11, 9, 12), 1, "L1", "publicado"))
    h.agregar(_r(datetime(2026, 11, 9, 9), 2, "L1", "publicado"))
    assert h.ultima_publicacion("L1") == datetime(2026, 11, 9, 12)


def test_archivo_inexistente(tmp_path):
    h = Historial(tmp_path / "h.csv")
    assert h.ultima_publicacion("L1") is None
    assert h.publicadas("d", "t", date.today()) == {}
    assert h.grupos_usados("d", "t", date.today()) == set()


def test_acentos_y_comas(tmp_path):
    h = Historial(tmp_path / "h.csv")
    t = datetime(2026, 11, 9, 10)
    h.agregar(Registro(t, "3 MIÉRCOLES", "TIRA 1", 1, "Centro de Carga (¿Ya no carga?), x", "Compra, Venta", "L1", "a", "publicado"))
    assert h.publicadas("3 MIÉRCOLES", "TIRA 1", t.date()) == {1: "L1"}


def test_ultimas_publicaciones(tmp_path):
    h = Historial(tmp_path / "h.csv")
    h.agregar(_r(datetime(2026, 11, 9, 12), 1, "L1", "publicado"))
    h.agregar(_r(datetime(2026, 11, 9, 9), 2, "L1", "publicado"))
    h.agregar(_r(datetime(2026, 11, 9, 13), 3, "L2", "saltado"))
    assert h.ultimas_publicaciones() == {"L1": datetime(2026, 11, 9, 12)}


def test_historial_guardado_desde_excel(tmp_path):
    """Excel guarda en ANSI, con ';' y fechas dd/mm/aaaa."""
    ruta = tmp_path / "h.csv"
    contenido = ("fecha_hora;dia;tira;numero;titulo;grupo;link_grupo;archivo_ubicacion;resultado\r\n"
                 "09/11/2026 10:00;1.lunes;TIRA 1;1;Batería;Grupo;L1;0.UBICACIÓN.mp4;publicado\r\n")
    ruta.write_bytes(contenido.encode("cp1252"))
    h = Historial(ruta)
    assert h.publicadas("1.lunes", "TIRA 1", date(2026, 11, 9)) == {1: "L1"}
    assert h.ultima_publicacion("L1") == datetime(2026, 11, 9, 10, 0)
    h.agregar(_r(datetime(2026, 11, 9, 11), 2, "L2", "publicado"))
    h2 = Historial(ruta)
    assert h2.publicadas("1.lunes", "TIRA 1", date(2026, 11, 9)) == {1: "L1", 2: "L2"}
    assert ruta.read_bytes().startswith(b"\xef\xbb\xbf")


# --- Por cuenta ---------------------------------------------------------------------
def _rc(t, numero, link, resultado, cuenta, tira="TIRA 1"):
    return Registro(t, "1.lunes", tira, numero, f"T{numero}", "G", link, "u", resultado, cuenta)


def test_filas_viejas_son_de_la_principal(tmp_path):
    ruta = tmp_path / "h.csv"
    ruta.write_text("fecha_hora,dia,tira,numero,titulo,grupo,link_grupo,archivo_ubicacion,resultado\n"
                    "2026-11-09 10:00:00,1.lunes,TIRA 1,1,T,G,L1,u,publicado\n", encoding="utf-8-sig")
    h = Historial(ruta, cuenta_principal="Yo")
    assert h.ultimas_publicaciones("Yo") == {"L1": datetime(2026, 11, 9, 10)}
    assert h.ultimas_publicaciones("Sucursal") == {}
    h.agregar(_rc(datetime(2026, 11, 9, 11), 2, "L2", "publicado", "Sucursal"))
    texto = ruta.read_text(encoding="utf-8-sig")
    assert texto.splitlines()[0].endswith(",cuenta")
    h2 = Historial(ruta, cuenta_principal="Yo")
    assert h2.ultimas_publicaciones("Yo") == {"L1": datetime(2026, 11, 9, 10)}
    assert h2.ultimas_publicaciones("Sucursal") == {"L2": datetime(2026, 11, 9, 11)}


def test_filtros_por_cuenta(tmp_path):
    h = Historial(tmp_path / "h.csv", cuenta_principal="Yo")
    t = datetime(2026, 11, 9, 10)
    h.agregar(_rc(t, 1, "L1", "publicado", "Yo"))
    h.agregar(_rc(t, 2, "L2", "publicado", "Suc"))
    h.agregar(_rc(t, 3, "L3", "saltado", "Suc"))
    h.agregar(_rc(t, 0, "", "bloqueo", "Suc"))
    assert h.publicadas("1.lunes", "TIRA 1", t.date()) == {1: "L1", 2: "L2"}  # sin importar cuenta
    assert h.grupos_usados("1.lunes", "TIRA 1", t.date(), cuenta="Suc") == {"L2", "L3"}
    assert h.publicadas_hoy_cuenta("Suc", t.date()) == 1
    assert h.bloqueada_hoy("Suc", t.date()) is True
    assert h.bloqueada_hoy("Yo", t.date()) is False
    assert h.ultimas_publicaciones() == {"L1": t, "L2": t}
