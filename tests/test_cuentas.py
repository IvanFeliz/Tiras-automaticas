from publicador.cuentas import (Cuenta, cargar_cuentas, guardar_cuentas, migrar_grupos, principal,
                                ruta_grupos)


def test_roundtrip(tmp_path):
    cs = [Cuenta("Reparaciones Gigabyte", "perfil"), Cuenta("Sucursal Centro", "pagina")]
    guardar_cuentas(tmp_path / "c.json", cs, "Sucursal Centro")
    assert cargar_cuentas(tmp_path / "c.json") == (cs, "Sucursal Centro")


def test_corrupto(tmp_path):
    (tmp_path / "c.json").write_text("{x", encoding="utf-8")
    assert cargar_cuentas(tmp_path / "c.json") == ([], "")
    assert cargar_cuentas(tmp_path / "no.json") == ([], "")


def test_principal():
    assert principal([Cuenta("P1", "pagina"), Cuenta("Yo", "perfil")]).nombre == "Yo"
    assert principal([Cuenta("P1", "pagina")]).nombre == "P1"
    assert principal([]) is None


def test_ruta_grupos(tmp_path):
    r = ruta_grupos(tmp_path, "Sucursal Altamirano #13 — Niño")
    assert r.parent == tmp_path / "grupos"
    assert r.name.startswith("sucursal-altamirano-13-nino-") and r.suffix == ".txt"
    assert ruta_grupos(tmp_path, "Reparaciones Cel") != ruta_grupos(tmp_path, "Reparaciones-Cel")
    assert ruta_grupos(tmp_path, "🔧📱") != ruta_grupos(tmp_path, "📱🔧")
    assert ruta_grupos(tmp_path, "Yo") == ruta_grupos(tmp_path, "Yo")


def test_migrar_grupos(tmp_path):
    (tmp_path / "grupos.txt").write_text("A | x\n", encoding="utf-8")
    migrar_grupos(tmp_path, "Yo")
    assert ruta_grupos(tmp_path, "Yo").read_text(encoding="utf-8") == "A | x\n"
    assert not (tmp_path / "grupos.txt").exists()


def test_migrar_no_pisa(tmp_path):
    destino = ruta_grupos(tmp_path, "Yo")
    destino.parent.mkdir()
    destino.write_text("B | y\n", encoding="utf-8")
    (tmp_path / "grupos.txt").write_text("A | x\n", encoding="utf-8")
    migrar_grupos(tmp_path, "Yo")
    assert destino.read_text(encoding="utf-8") == "B | y\n"
    assert (tmp_path / "grupos.txt").exists()



def test_guardar_sin_temporales(tmp_path):
    guardar_cuentas(tmp_path / "c.json", [Cuenta("A", "perfil")], "A")
    assert not list(tmp_path.glob("*.tmp"))
    assert cargar_cuentas(tmp_path / "c.json")[1] == "A"
