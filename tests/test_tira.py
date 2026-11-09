import shutil
from pathlib import Path

import pytest

from publicador.tira import leer_tira, listar_subcarpetas

DATOS = Path(__file__).parent / "datos"
IMAGENES = [
    "1 PANTALLA.png", "2 TAPA.png", "3 CENTRO DE CARGA 2.png", "4 MANTENIMIENTO.png",
    "5 BATERIA.png", "6 MICROFONO.png", "7 FORMATEO.png", "8 OFFICE.png",
    "9 MANTENIMIENTO LAPTOP.png", "10 DISPLAY.png", "11 DISCO.png", "12 TECLADO.png",
]
UBICACIONES = ["000.ALTAMIRANO.jpeg", "0.CROQUIS ALTAMIRANO.jpg", "0.UBICACION ALTAMIRANO.mp4"]


def _tocar(carpeta: Path, nombres):
    for n in nombres:
        (carpeta / n).write_bytes(b"x")


@pytest.fixture
def tira_real(tmp_path):
    c = tmp_path / "TIRA 1"
    c.mkdir()
    shutil.copy(DATOS / "0 TEXTOS TIRA.txt", c / "0 TEXTOS TIRA.txt")
    _tocar(c, IMAGENES + UBICACIONES)
    return c


def _tira_simple(tmp_path, texto, imagenes, ubic=("0.CROQUIS.jpg",), encoding="utf-8"):
    c = tmp_path / "T"
    c.mkdir()
    (c / "0 TEXTOS TIRA.txt").write_text(texto, encoding=encoding)
    _tocar(c, list(imagenes) + list(ubic))
    return c


def test_tira_real(tira_real):
    t = leer_tira(tira_real)
    assert t.ok, t.errores
    assert [p.numero for p in t.publicaciones] == list(range(1, 13))
    p1 = t.publicaciones[0]
    assert p1.titulo == "Cambio de Pantalla"
    assert p1.imagen.name == "1 PANTALLA.png"
    assert p1.texto.startswith("📱💥 ¿Se te rompió la pantalla")
    assert p1.texto.endswith("https://wa.me/message/UONLT5LZIBPQK1 🚀💙")
    assert "\r" not in p1.texto and "\n\n✅" in p1.texto
    assert t.publicaciones[3].texto.splitlines()[-1].startswith("o da click")
    assert t.publicaciones[2].imagen.name == "3 CENTRO DE CARGA 2.png"
    assert {u.name for u in t.ubicaciones} == set(UBICACIONES)


def _bloques(n):
    return "TIRA #\n\n" + "\n---\n".join(f"{i}. T{i}\n\nTexto {i}" for i in range(1, n + 1))


def test_uno_no_toma_diez(tmp_path):
    imgs = [f"{i} I{i}.png" for i in range(1, 11)]
    t = leer_tira(_tira_simple(tmp_path, _bloques(10), imgs))
    assert t.ok, t.errores
    assert t.publicaciones[0].imagen.name == "1 I1.png"
    assert t.publicaciones[9].imagen.name == "10 I10.png"


def test_txt_cp1252(tmp_path):
    texto = "1. Diseño\n\nEstá súper niño\n---\n2. B\n\nOtro"
    t = leer_tira(_tira_simple(tmp_path, texto, ["1 A.png", "2 B.png"], encoding="cp1252"))
    assert t.ok, t.errores
    assert t.publicaciones[0].texto == "Está súper niño"
    assert t.publicaciones[0].titulo == "Diseño"


def test_separador_variable(tmp_path):
    texto = "1. A\nUno\n---\n2. B\n\nDos\n\n" + "-" * 60 + "\n3. C\nTres\n"
    t = leer_tira(_tira_simple(tmp_path, texto, ["1 A.png", "2 B.png", "3 C.png"]))
    assert t.ok, t.errores
    assert [p.texto for p in t.publicaciones] == ["Uno", "Dos", "Tres"]


def test_falta_imagen(tira_real):
    (tira_real / "5 BATERIA.png").unlink()
    t = leer_tira(tira_real)
    assert not t.ok
    assert any("5" in e for e in t.errores)


def test_imagen_sin_texto(tira_real):
    (tira_real / "13 EXTRA.png").write_bytes(b"x")
    t = leer_tira(tira_real)
    assert not t.ok
    assert any("13" in e for e in t.errores)


def test_numero_repetido(tmp_path):
    texto = "1. A\nUno\n---\n2. B\nDos\n---\n2. C\nTres"
    t = leer_tira(_tira_simple(tmp_path, texto, ["1 A.png", "2 B.png"]))
    assert not t.ok
    assert any("repetid" in e for e in t.errores)


def test_sin_ubicacion(tmp_path):
    t = leer_tira(_tira_simple(tmp_path, "1. A\nUno", ["1 A.png"], ubic=()))
    assert not t.ok
    assert any("ubicación" in e for e in t.errores)


def test_sin_txt(tmp_path):
    c = tmp_path / "T"
    c.mkdir()
    _tocar(c, ["1 A.png", "0.X.jpg"])
    t = leer_tira(c)
    assert not t.ok
    assert t.errores


def test_listar_subcarpetas(tmp_path):
    for n in ["TIRA 10", "TIRA 2", "TIRA 1", "otra"]:
        (tmp_path / "a" / n).mkdir(parents=True)
    assert [p.name for p in listar_subcarpetas(tmp_path / "a")] == ["TIRA 1", "TIRA 2", "TIRA 10", "otra"]
    for n in ["2 MARTES", "1.lunes", "7. DOMINGO"]:
        (tmp_path / "b" / n).mkdir(parents=True)
    (tmp_path / "b" / "archivo.txt").write_text("x")
    assert [p.name for p in listar_subcarpetas(tmp_path / "b")] == ["1.lunes", "2 MARTES", "7. DOMINGO"]
