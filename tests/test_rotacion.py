import random
from datetime import datetime, timedelta

from publicador.grupos import Grupo
from publicador.historial import Historial, Registro
from publicador.rotacion import elegir_grupo

AHORA = datetime(2026, 11, 9, 15, 0)


def _hist(tmp_path, usos):
    h = Historial(tmp_path / "h.csv")
    for link, hace in usos.items():
        h.agregar(Registro(AHORA - hace, "d", "t", 1, "x", link, link, "u", "publicado"))
    return h


def _g(*links, inactivos=()):
    return [Grupo(l, l, l not in inactivos) for l in links]


def test_prefiere_nunca_usado(tmp_path):
    h = _hist(tmp_path, {"G1": timedelta(hours=5)})
    assert elegir_grupo(_g("G1", "G2"), h, AHORA, 60, set(), random.Random(0)).link == "G2"


def test_mas_antiguo(tmp_path):
    h = _hist(tmp_path, {"G1": timedelta(hours=2), "G2": timedelta(hours=5)})
    assert elegir_grupo(_g("G1", "G2"), h, AHORA, 60, set(), random.Random(0)).link == "G2"


def test_regla_minutos(tmp_path):
    h = _hist(tmp_path, {"G1": timedelta(minutes=59)})
    assert elegir_grupo(_g("G1"), h, AHORA, 60, set(), random.Random(0)) is None
    h2 = Historial(tmp_path / "h2.csv")
    h2.agregar(Registro(AHORA - timedelta(minutes=61), "d", "t", 1, "x", "G1", "G1", "u", "publicado"))
    assert elegir_grupo(_g("G1"), h2, AHORA, 60, set(), random.Random(0)).link == "G1"


def test_excluir_e_inactivos(tmp_path):
    h = _hist(tmp_path, {})
    g = elegir_grupo(_g("G1", "G2", "G3", inactivos={"G2"}), h, AHORA, 60, {"G1"}, random.Random(0))
    assert g.link == "G3"


def test_empate_al_azar(tmp_path):
    h = _hist(tmp_path, {})
    vistos = {elegir_grupo(_g("A", "B", "C"), h, AHORA, 60, set(), random.Random(s)).link for s in range(20)}
    assert vistos <= {"A", "B", "C"} and len(vistos) >= 2


def test_sin_grupos(tmp_path):
    assert elegir_grupo([], _hist(tmp_path, {}), AHORA, 60, set(), random.Random(0)) is None
