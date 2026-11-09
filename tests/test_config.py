from publicador.config import Config, cargar_config, guardar_config


def test_config_defecto_y_roundtrip(tmp_path):
    assert cargar_config(tmp_path / "no.json").minutos_entre_publicaciones == 60
    guardar_config(tmp_path / "c.json", Config(carpeta_tiras="C:/T", minutos_entre_publicaciones=30))
    c = cargar_config(tmp_path / "c.json")
    assert c.minutos_entre_publicaciones == 30
    assert c.carpeta_tiras == "C:/T"


def test_config_corrupto(tmp_path):
    (tmp_path / "c.json").write_text("{no json", encoding="utf-8")
    assert cargar_config(tmp_path / "c.json") == Config()


def test_config_claves_desconocidas(tmp_path):
    (tmp_path / "c.json").write_text('{"otra": 1, "ultimo_dia": "1.lunes"}', encoding="utf-8")
    assert cargar_config(tmp_path / "c.json").ultimo_dia == "1.lunes"


def test_una_sola_instancia(tmp_path):
    from publicador.config import bloquear_instancia
    primero = bloquear_instancia(tmp_path)
    assert primero is not None
    assert bloquear_instancia(tmp_path) is None
    primero.close()
    otra = bloquear_instancia(tmp_path)
    assert otra is not None
    otra.close()


def test_ajustar_espera():
    from publicador.config import ajustar_espera
    c = Config(espera_min=1, espera_max=0)
    ajustar_espera(c)
    assert (c.espera_min, c.espera_max) == (2, 2)
    c = Config(espera_min=7, espera_max=4)
    ajustar_espera(c)
    assert (c.espera_min, c.espera_max) == (7, 7)
    assert Config().modo == "revision"
