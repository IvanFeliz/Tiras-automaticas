"""Miles de archivos raros: textos de tira, grupos.txt e historial.csv. Nada debe tronar ni perder datos."""
import random
from datetime import date, datetime, timedelta

import pytest

from publicador.grupos import actualizar_grupos, cargar_grupos, marcar_ignorado, normalizar_link_grupo
from publicador.historial import Historial, Registro
from publicador.tira import leer_tira, listar_subcarpetas

ENC = ["utf-8", "utf-8-sig", "cp1252", "utf-16"]
EMOJIS = "📱💥✅📍📲🚀💙🔋⚡️🛠️💻⌨️❌🎙️"
LETRAS = "abcdefghijklmnñopqrstuvwxyzáéíóúü ABCDEFGHIJKLMNÑOPQRSTUVWXYZÁÉÍÓÚ 0123456789 ¿?¡!.,:;#()-_/"


def _texto(rng, n, emojis=True):
    fuente = LETRAS + (EMOJIS if emojis else "")
    return "".join(rng.choice(fuente) for _ in range(n))


# --- Tiras -------------------------------------------------------------------------
def _tira_al_azar(carpeta, rng):
    n = rng.randint(0, 14)
    numeros = list(range(1, n + 1))
    if rng.random() < 0.2 and numeros:
        numeros.append(rng.choice(numeros))  # repetido
    rng.shuffle(numeros) if rng.random() < 0.2 else None
    bloques = []
    for num in numeros:
        cuerpo = "\n".join(_texto(rng, rng.randint(0, 60)) for _ in range(rng.randint(0, 6)))
        cab = rng.choice([f"{num}. ", f"{num}.", f"  {num}. ", f"{num}.  "]) + _texto(rng, rng.randint(0, 30), False)
        bloques.append(cab + "\n" * rng.randint(0, 3) + cuerpo)
    sep = lambda: "\n" * rng.randint(0, 2) + "-" * rng.randint(3, 70) + " " * rng.randint(0, 2) + "\n" * rng.randint(0, 2)
    texto = rng.choice(["", "TIRA #\n\n", "TIRA 3\n"]) + "".join(b + sep() for b in bloques)
    if rng.random() < 0.3:
        texto = texto.replace("\n", "\r\n")
    enc = rng.choice(ENC)
    if enc == "cp1252":
        texto = texto.encode("cp1252", "replace").decode("cp1252")
    if rng.random() < 0.9:
        (carpeta / rng.choice(["0 TEXTOS TIRA.txt", "textos.TXT"])).write_bytes(texto.encode(enc, "replace"))
    if rng.random() < 0.05:
        (carpeta / "otro.txt").write_text("x", encoding="utf-8")
    for num in set(numeros):
        if rng.random() < 0.92:
            ext = rng.choice([".png", ".jpg", ".jpeg", ".webp", ".PNG"])
            (carpeta / f"{num} {_texto(rng, rng.randint(0, 12), False).strip('/')}{ext}".replace("/", "")).write_bytes(b"x")
    if rng.random() < 0.1:
        (carpeta / f"{n + 1} EXTRA.png").write_bytes(b"x")
    for nombre in rng.sample(["000.LOCAL.jpeg", "0.CROQUIS.jpg", "0.VIDEO.mp4", "0.X.mov"], rng.randint(0, 4)):
        (carpeta / nombre).write_bytes(b"x")
    (carpeta / "Thumbs.db").write_bytes(b"x") if rng.random() < 0.1 else None


@pytest.mark.parametrize("bloque", range(10))
def test_tiras_raras_nunca_truenan(tmp_path, bloque):
    for i in range(150):
        rng = random.Random(bloque * 1000 + i)
        c = tmp_path / f"TIRA {i}"
        c.mkdir()
        _tira_al_azar(c, rng)
        t = leer_tira(c)
        # Reglas: si está OK, todo cuadra; si no, hay al menos un error explicado.
        assert t.ok == (not t.errores)
        if t.ok:
            assert t.publicaciones and t.ubicaciones
            nums = [p.numero for p in t.publicaciones]
            assert nums == sorted(set(nums))
            for p in t.publicaciones:
                assert p.imagen.exists() and p.imagen.name.startswith(f"{p.numero}")
                assert not p.imagen.name[len(str(p.numero))].isdigit()
                assert "\r" not in p.texto and p.texto == p.texto.strip()
        for e in t.errores:
            assert isinstance(e, str) and e
    assert len(listar_subcarpetas(tmp_path)) == 150


def test_carpeta_que_no_existe(tmp_path):
    t = leer_tira(tmp_path / "no-existe")
    assert not t.ok
    assert listar_subcarpetas(tmp_path / "no-existe") == []


# --- grupos.txt ----------------------------------------------------------------------
def _link(rng, i):
    base = rng.choice(["https://www.facebook.com/groups/", "https://facebook.com/groups/", "facebook.com/groups/",
                       "https://web.facebook.com/groups/", "https://m.facebook.com/groups/"])
    return base + f"{i}" + rng.choice(["", "/", "/?ref=share", "/posts/99"])


@pytest.mark.parametrize("bloque", range(10))
def test_grupos_txt_nunca_pierde_grupos(tmp_path, bloque):
    for k in range(60):
        rng = random.Random(bloque * 1000 + k)
        r = tmp_path / f"g{k}.txt"
        lineas, esperados = [], set()
        for i in range(rng.randint(0, 40)):
            tipo = rng.random()
            if tipo < 0.1:
                lineas.append(rng.choice(["", "   ", "solo texto", "# comentario", "|", "a | b"]))
                continue
            nombre = _texto(rng, rng.randint(0, 25), True).replace("|", "")
            pref = rng.choice(["", "", "# ", "#", "# (ya no aparece) ", "# (sin permiso) ", "  "])
            lineas.append(f"{pref}{nombre} {'|' if rng.random() < 0.97 else '¦'} {_link(rng, i)}  ")
            if "¦" not in lineas[-1]:
                esperados.add(normalizar_link_grupo(_link(random.Random(0), i)) or "")
        enc = rng.choice(["utf-8", "utf-8-sig", "cp1252"])
        texto = "\n".join(lineas)
        if enc == "cp1252":
            texto = texto.encode("cp1252", "replace").decode("cp1252")
        r.write_bytes(texto.encode(enc, "replace"))
        antes = {g.link for g in cargar_grupos(r)}
        inactivos_manual = {g.link for g in cargar_grupos(r) if not g.activo}
        # Operaciones al azar
        for _ in range(rng.randint(1, 6)):
            op = rng.random()
            if op < 0.4 and antes:
                marcar_ignorado(r, rng.choice(sorted(antes)), rng.choice(["", "sin permiso"]))
            else:
                encontrados = [(_texto(rng, 10, False), _link(rng, rng.randint(0, 60))) for _ in range(rng.randint(0, 30))]
                actualizar_grupos(r, encontrados)
            despues = {g.link for g in cargar_grupos(r)}
            assert antes <= despues, f"se perdieron grupos: {antes - despues}"
            antes = despues
        assert not list(tmp_path.glob("*.tmp"))
        # Ningún grupo repetido
        links = [g.link for g in cargar_grupos(r)]
        assert len(links) == len(set(links))
        del inactivos_manual, esperados


# --- historial.csv -------------------------------------------------------------------
def _fila_excel(rng, t):
    fecha = rng.choice([t.strftime("%Y-%m-%d %H:%M:%S"), t.strftime("%d/%m/%Y %H:%M"), t.strftime("%Y-%m-%d %H:%M"),
                        t.strftime("%d/%m/%y %H:%M"), "08/11/2026 10:00 a. m.", "", "basura"])
    campos = [fecha, "1.lunes", rng.choice(["TIRA 1", "TIRA 2"]), str(rng.randint(1, 12)),
              _texto(rng, 15).replace(",", " ").replace(";", " ").replace('"', ""), "Grupo",
              f"https://www.facebook.com/groups/{rng.randint(1, 9)}/", "0.X.jpg",
              rng.choice(["publicado", "saltado", "error", "bloqueo"])]
    if rng.random() < 0.5:
        campos.append(rng.choice(["", "Perfil", "Página Ñ"]))
    return campos


@pytest.mark.parametrize("bloque", range(10))
def test_historial_raro_nunca_pierde_filas(tmp_path, bloque):
    for k in range(40):
        rng = random.Random(bloque * 1000 + k)
        ruta = tmp_path / f"h{k}.csv"
        t0 = datetime(2026, 11, 9, 9)
        con_cuenta = rng.random() < 0.5
        sep = rng.choice([",", ";"])
        enc = rng.choice(["utf-8-sig", "utf-8", "cp1252"])
        cab = ["fecha_hora", "dia", "tira", "numero", "titulo", "grupo", "link_grupo", "archivo_ubicacion", "resultado"]
        filas = [_fila_excel(rng, t0 + timedelta(minutes=i)) for i in range(rng.randint(0, 25))]
        if con_cuenta:
            cab.append("cuenta")
        filas = [f[:len(cab)] + [""] * (len(cab) - len(f)) for f in filas]
        texto = "\n".join(sep.join(x) for x in [cab] + filas) + ("\n" if rng.random() < 0.7 else "")
        if enc == "cp1252":
            texto = texto.encode("cp1252", "replace").decode("cp1252")
        ruta.write_bytes(texto.encode(enc, "replace"))
        h = Historial(ruta, cuenta_principal=rng.choice(["", "Perfil"]))
        # Consultas: nunca truenan
        h.publicadas("1.lunes", "TIRA 1", date(2026, 11, 9))
        h.ultimas_publicaciones()
        h.ultimas_publicaciones("Perfil")
        h.bloqueada_hoy("Perfil", date(2026, 11, 9))
        n_antes = len(h._filas_crudas())
        # Agregar y fijar cuenta: no se pierde ninguna fila, aunque la fecha sea rara
        for i in range(rng.randint(1, 4)):
            h.agregar(Registro(t0 + timedelta(hours=i + 1), "1.lunes", "TIRA 1", i + 1, "Título, con \"comillas\"; y ñ",
                               "G", f"L{i}", "0.X.jpg", "publicado", rng.choice(["", "Perfil", "Página Ñ"])))
            n_antes += 1
            assert len(Historial(ruta)._filas_crudas()) == n_antes
        h.fijar_cuenta_vacia("Perfil")
        assert len(Historial(ruta)._filas_crudas()) == n_antes
        assert ruta.read_bytes().startswith(b"\xef\xbb\xbf")
        assert all(f["cuenta"] for f in Historial(ruta)._filas_crudas())


def test_rutas_con_acentos_y_espacios(tmp_path):
    from publicador.cuentas import ruta_grupos
    c = tmp_path / "Mis Documentos Ñoños" / "3 MIÉRCOLES" / "TIRA 1 (copia)"
    c.mkdir(parents=True)
    (c / "0 TEXTOS TIRA.txt").write_text("1. Batería\n\nTexto ñ 📱", encoding="utf-8")
    (c / "1 BATERÍA Ñ.png").write_bytes(b"x")
    (c / "0.UBICACIÓN.mp4").write_bytes(b"x")
    t = leer_tira(c)
    assert t.ok, t.errores
    assert t.publicaciones[0].imagen.name == "1 BATERÍA Ñ.png"
    r = ruta_grupos(tmp_path / "Datos Ñ", "Página Señora Ñ")
    r.parent.mkdir(parents=True)
    actualizar_grupos(r, [("Grupo Ñ", "https://www.facebook.com/groups/1/")])
    assert cargar_grupos(r)[0].nombre == "Grupo Ñ"
