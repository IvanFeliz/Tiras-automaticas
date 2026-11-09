from publicador.grupos import actualizar_grupos, cargar_grupos, marcar_ignorado

L1 = "https://www.facebook.com/groups/1/"
L2 = "https://www.facebook.com/groups/2/"
L3 = "https://www.facebook.com/groups/3/"
L4 = "https://www.facebook.com/groups/4/"


def test_actualizar_respeta_marcas(tmp_path):
    r = tmp_path / "grupos.txt"
    r.write_text(f"A | {L1}\n# B | {L2}\nC | {L3}\n", encoding="utf-8")
    nuevos = actualizar_grupos(r, [("A", L1), ("B", L2), ("D", L4)])
    assert nuevos == 1
    gs = {g.link: g for g in cargar_grupos(r)}
    assert gs[L2].activo is False
    assert gs[L4].activo is True and gs[L4].nombre == "D"
    assert gs[L3].activo is False
    assert f"# (ya no aparece) C | {L3}" in r.read_text(encoding="utf-8")


def test_actualizar_archivo_nuevo(tmp_path):
    r = tmp_path / "grupos.txt"
    assert actualizar_grupos(r, [("A", L1), ("B", L2)]) == 2
    assert [g.nombre for g in cargar_grupos(r)] == ["A", "B"]


def test_reaparece_no_se_reactiva_si_tenia_marca_manual(tmp_path):
    r = tmp_path / "grupos.txt"
    r.write_text(f"# (ya no aparece) C | {L3}\n", encoding="utf-8")
    actualizar_grupos(r, [("C", L3)])
    # Volvió a aparecer: se reactiva porque la marca era automática.
    assert cargar_grupos(r)[0].activo is True


def test_marcar_ignorado(tmp_path):
    r = tmp_path / "grupos.txt"
    r.write_text(f"A | {L1}\nB | {L2}\n", encoding="utf-8")
    marcar_ignorado(r, L1)
    assert r.read_text(encoding="utf-8") == f"# A | {L1}\nB | {L2}\n"
    gs = {g.link: g for g in cargar_grupos(r)}
    assert gs[L1].activo is False and gs[L2].activo is True


def test_lineas_raras(tmp_path):
    r = tmp_path / "grupos.txt"
    r.write_text(f"\nsolo texto\n  X  |  {L1}  \n", encoding="utf-8")
    gs = cargar_grupos(r)
    assert [(g.nombre, g.link) for g in gs] == [("X", L1)]
    actualizar_grupos(r, [("X", L1)])
    assert "solo texto" in r.read_text(encoding="utf-8")


def test_sin_archivo(tmp_path):
    assert cargar_grupos(tmp_path / "no.txt") == []
