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
