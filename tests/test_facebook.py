from pathlib import Path

import pytest

from publicador.facebook import Facebook, normalizar_link_grupo
from publicador.sesion import Controles, ErrorFacebook

DATOS = Path(__file__).parent / "datos"


@pytest.mark.parametrize("href,esperado", [
    ("https://www.facebook.com/groups/123456/", "https://www.facebook.com/groups/123456/"),
    ("/groups/compraventaiguala/?ref=bookmarks", "https://www.facebook.com/groups/compraventaiguala/"),
    ("https://web.facebook.com/groups/987/posts/55", "https://www.facebook.com/groups/987/"),
    ("https://m.facebook.com/groups/987", "https://www.facebook.com/groups/987/"),
    ("https://www.facebook.com/groups/feed/", None),
    ("https://www.facebook.com/groups/joins/", None),
    ("https://www.facebook.com/groups/discover/", None),
    ("https://www.facebook.com/profile.php?id=1", None),
    ("", None),
])
def test_normalizar_link_grupo(href, esperado):
    assert normalizar_link_grupo(href) == esperado


# --- Pruebas con navegador real contra páginas falsas -------------------------------

@pytest.fixture
def fb(tmp_path):
    f = Facebook(tmp_path / "perfil", tmp_path / "capturas", canales=(None,), headless=True)
    try:
        f.abrir()
    except Exception as e:  # sin navegador disponible
        pytest.skip(f"no se pudo abrir el navegador: {e}")
    yield f
    f.cerrar()


def _archivos(tmp_path):
    img = tmp_path / "1 PANTALLA.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")
    ub = tmp_path / "0.CROQUIS.jpg"
    ub.write_bytes(b"\xff\xd8\xff")
    return [img, ub]


TEXTO = "📱💥 ¿Se te rompió la pantalla?\n\n✅ ¡Tráelo hoy!\n📍 Altamirano #13"


def test_preparar_y_publicar(fb, tmp_path):
    fb.preparar_publicacion((DATOS / "grupo_falso.html").as_uri(), TEXTO, _archivos(tmp_path))
    pagina = fb.pagina
    assert pagina.evaluate("document.querySelector('#ed').innerText") == TEXTO
    assert sorted(pagina.evaluate("window.__subidos")) == ["0.CROQUIS.jpg", "1 PANTALLA.png"]
    # La persona da clic en Publicar (aquí lo simulamos con un clic real).
    c = Controles()
    pagina.locator("#publicar").click()
    assert fb.esperar_resultado(c) == "publicado"


def test_cerrar_sin_publicar(fb, tmp_path):
    fb.preparar_publicacion((DATOS / "grupo_falso.html").as_uri(), TEXTO, _archivos(tmp_path))
    fb.pagina.keyboard.press("Escape")
    assert fb.esperar_resultado(Controles()) == "cerrado"


def test_saltar_y_detener(fb, tmp_path):
    for evento, esperado in (("saltar", "saltar"), ("detener", "detener")):
        fb.preparar_publicacion((DATOS / "grupo_falso.html").as_uri(), TEXTO, _archivos(tmp_path))
        c = Controles()
        getattr(c, evento).set()
        assert fb.esperar_resultado(c) == esperado
        fb.cerrar_compositor()
        assert fb.pagina.locator('[role="dialog"]').count() == 0


def test_sin_compositor_lanza_error(fb, tmp_path):
    vacia = tmp_path / "vacia.html"
    vacia.write_text("<html><body>nada</body></html>", encoding="utf-8")
    fb.timeout_compositor_ms = 1500
    with pytest.raises(ErrorFacebook):
        fb.preparar_publicacion(vacia.as_uri(), TEXTO, _archivos(tmp_path))
    assert fb.captura("x").exists()


def test_extraer_grupos(fb):
    fb.url_tus_grupos = (DATOS / "tus_grupos_falso.html").as_uri()
    fb.pausa_scroll_s = 0.3
    estados = []
    grupos = fb.extraer_grupos(estados.append)
    assert len(grupos) == 25
    assert grupos[0] == ("Grupo 0", "https://www.facebook.com/groups/1000/")
    assert estados


def test_sesion_activa(fb, tmp_path):
    login = tmp_path / "login.html"
    login.write_text('<html><body><input name="email"></body></html>', encoding="utf-8")
    fb.pagina.goto(login.as_uri())
    assert fb.sesion_activa() is False
    fb.pagina.goto((DATOS / "grupo_falso.html").as_uri())
    assert fb.sesion_activa() is True


# --- Correcciones de la revisión final ------------------------------------------------
from publicador.sesion import NavegadorCerrado, SesionCerrada  # noqa: E402


def test_pegado_lento_no_duplica(fb, tmp_path):
    url = (DATOS / "grupo_falso.html").as_uri() + "?lento=1"
    fb.preparar_publicacion(url, TEXTO, _archivos(tmp_path))
    fb.pagina.wait_for_timeout(500)
    assert fb.pagina.evaluate("document.querySelector('#ed').innerText") == TEXTO


def test_clic_en_publicar_desactivado_no_cuenta(fb, tmp_path):
    fb.preparar_publicacion((DATOS / "grupo_falso.html").as_uri(), TEXTO, _archivos(tmp_path))
    fb.pagina.locator("#publicar-desactivado").click(force=True)
    fb.pagina.keyboard.press("Escape")
    assert fb.esperar_resultado(Controles()) == "cerrado"


def test_publicado_gana_a_saltar(fb, tmp_path):
    fb.preparar_publicacion((DATOS / "grupo_falso.html").as_uri(), TEXTO, _archivos(tmp_path))
    fb.pagina.locator("#publicar").click()
    c = Controles()
    c.saltar.set()
    assert fb.esperar_resultado(c) == "publicado"


def test_sesion_cerrada_despues_de_abrir_grupo(fb, tmp_path):
    login = tmp_path / "login.html"
    login.write_text('<html><body><input name="email"></body></html>', encoding="utf-8")
    with pytest.raises(SesionCerrada):
        fb.preparar_publicacion(login.as_uri(), TEXTO, _archivos(tmp_path))


def test_navegador_cerrado_a_mano(fb, tmp_path):
    fb.preparar_publicacion((DATOS / "grupo_falso.html").as_uri(), TEXTO, _archivos(tmp_path))
    fb.pagina.close()
    with pytest.raises(NavegadorCerrado):
        fb.esperar_resultado(Controles())
    with pytest.raises(NavegadorCerrado):
        fb.preparar_publicacion((DATOS / "grupo_falso.html").as_uri(), TEXTO, _archivos(tmp_path))
