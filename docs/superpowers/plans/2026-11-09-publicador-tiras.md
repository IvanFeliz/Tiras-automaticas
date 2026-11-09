# Publicador de Tiras — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** App de escritorio para Windows que lee una carpeta de tira, abre cada grupo de Facebook, pega el texto y adjunta los archivos, y espera a que una persona dé clic en "Publicar".

**Architecture:** Módulos puros y probados (`tira`, `config`, `grupos`, `historial`, `rotacion`, `sesion`) más dos módulos de borde: `facebook.py` (Playwright) y `app.py` (Tkinter). Playwright corre en un solo hilo de trabajo; la ventana se comunica con él por colas y `threading.Event`.

**Tech Stack:** Python ≥3.11 (CI en 3.12), Playwright (sync API), Tkinter, pytest, PyInstaller, GitHub Actions `windows-latest`.

**Spec:** `docs/superpowers/specs/2026-11-09-publicador-tiras-design.md`

## Global Constraints

- Paquete en `src/publicador/`; pruebas en `tests/`; `pyproject.toml` con `pytest` configurado (`pythonpath = ["src"]`).
- Textos visibles al usuario en español.
- Archivos de datos en `%APPDATA%\PublicadorTiras\` (fuera de Windows: `~/.publicador_tiras/`).
- `minutos_entre_publicaciones` por defecto `60`.
- `historial.csv` en UTF-8 con BOM (`utf-8-sig`), columnas: `fecha_hora,dia,tira,numero,titulo,grupo,link_grupo,archivo_ubicacion,resultado`; `resultado` ∈ `publicado|saltado|error`.
- `grupos.txt`: una línea `nombre | link`; líneas que empiezan con `#` = ignoradas.
- El programa **nunca** da clic en "Publicar".
- Timeouts: compositor 30 s, subida de archivos 60 s.
- **Navegador:** se usa el Chrome o Edge instalado en Windows (`channel="chrome"`, y si falla `channel="msedge"`, que viene con Windows 10/11) con `launch_persistent_context`. Así el `.exe` no tiene que incluir Chromium (desviación menor del spec §10, que decía "Chromium incluido").

## Review Focus

1. `.txt` con fin de línea CRLF (el archivo real lo tiene) o guardado en cp1252 desde el Bloc de notas → debe leerse igual. Prueba en Task 1.
2. Separadores con distinta cantidad de guiones o sin línea en blanco antes/después (el archivo real mezcla ambos) → mismo resultado. Prueba en Task 1.
3. Nombres de imagen como `3 CENTRO DE CARGA 2.png` (dígito al final) o `10 DISPLAY.png` frente a `1 PANTALLA.png` → el `1` no debe tomar la `10`. Prueba en Task 1.
4. Reabrir la misma tira el mismo día después de un cierre → no se vuelven a publicar las que ya están `publicado`, ni se reusan sus grupos. Prueba en Task 5.
5. `grupos.txt` editado a mano con líneas vacías, espacios extra o sin `|` → no debe tronar; las líneas inválidas se conservan tal cual. Prueba en Task 2.

---

## Estructura de archivos

```
pyproject.toml
src/publicador/__init__.py
src/publicador/tira.py        lector y validación de carpetas de tira
src/publicador/config.py      config.json y carpeta de datos
src/publicador/grupos.py      grupos.txt
src/publicador/historial.py   historial.csv
src/publicador/rotacion.py    elegir grupo
src/publicador/sesion.py      secuencia de una tira (sin Tk ni Playwright directos)
src/publicador/facebook.py    todo lo de Playwright/Facebook
src/publicador/app.py         ventana Tkinter + hilo de trabajo
src/publicador/__main__.py    python -m publicador
tests/datos/0 TEXTOS TIRA.txt copia del archivo real
tests/test_tira.py, test_config.py, test_grupos.py, test_historial.py, test_rotacion.py, test_sesion.py, test_facebook.py
.github/workflows/build.yml
LEEME.md
.gitignore
```

---

### Task 1: Proyecto base y lector de tiras

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `src/publicador/__init__.py`, `src/publicador/tira.py`
- Test: `tests/test_tira.py` (usa `tests/datos/0 TEXTOS TIRA.txt`)

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) Publicacion(numero: int, titulo: str, texto: str, imagen: Path)`
  - `@dataclass Tira(carpeta: Path, publicaciones: list[Publicacion], ubicaciones: list[Path], errores: list[str])`, con la propiedad `ok -> bool` (`not errores`)
  - `leer_tira(carpeta: Path) -> Tira`
  - `listar_subcarpetas(carpeta: Path) -> list[Path]`: subcarpetas ordenadas por número inicial (las que no tienen número van al final, en orden alfabético)

Las pruebas arman carpetas en `tmp_path` copiando el `.txt` real y creando imágenes vacías con los nombres de la captura: `1 PANTALLA.png`, `2 TAPA.png`, `3 CENTRO DE CARGA 2.png`, `4 MANTENIMIENTO.png`, `5 BATERIA.png`, `6 MICROFONO.png` … `12 TECLADO.png`, más `000.ALTAMIRANO.jpeg`, `0.CROQUIS ALTAMIRANO.jpg` y `0.UBICACION ALTAMIRANO.mp4`.

- [ ] **Step 1: Escribir pruebas que fallen**

```python
def test_tira_real(tira_real):           # fixture: carpeta completa
    t = leer_tira(tira_real)
    assert t.ok, t.errores
    assert [p.numero for p in t.publicaciones] == list(range(1, 13))
    p1 = t.publicaciones[0]
    assert p1.titulo == "Cambio de Pantalla"
    assert p1.imagen.name == "1 PANTALLA.png"
    assert p1.texto.startswith("📱💥 ¿Se te rompió la pantalla")
    assert p1.texto.endswith("https://wa.me/message/UONLT5LZIBPQK1 🚀💙")
    assert "\r" not in p1.texto and "\n\n✅" in p1.texto
    assert t.publicaciones[3].texto.splitlines()[-1].startswith("o da click")  # espacio inicial quitado
    assert t.publicaciones[2].imagen.name == "3 CENTRO DE CARGA 2.png"
    assert {u.name for u in t.ubicaciones} == {"000.ALTAMIRANO.jpeg", "0.CROQUIS ALTAMIRANO.jpg", "0.UBICACION ALTAMIRANO.mp4"}

def test_uno_no_toma_diez(tmp_path): ...   # "1 A.png" y "10 B.png" → pub 1 → "1 A.png", pub 10 → "10 B.png"
def test_txt_cp1252(tmp_path): ...         # mismo contenido sin emojis guardado en cp1252 → texto con "ñ"/"é" correctos
def test_separador_variable(tmp_path): ... # "---" y 60 guiones, con y sin líneas en blanco → 2 publicaciones
def test_falta_imagen(tmp_path): ...       # sin "5 BATERIA.png" → not ok, error contiene "5"
def test_imagen_sin_texto(tmp_path): ...   # "13 EXTRA.png" sobrante → error contiene "13"
def test_numero_repetido(tmp_path): ...    # dos bloques "2." → error contiene "repetid"
def test_sin_ubicacion(tmp_path): ...      # sin archivos 0* → error contiene "ubicación"
def test_sin_txt(tmp_path): ...            # sin .txt → error
def test_listar_subcarpetas(tmp_path): ... # ["TIRA 10","TIRA 2","TIRA 1"] → ["TIRA 1","TIRA 2","TIRA 10"]; ["2 MARTES","1.lunes","7. DOMINGO"] → orden 1,2,7
```

- [ ] **Step 2: Correr y ver que fallan** — `pytest tests/test_tira.py -v` → FAIL (ImportError)
- [ ] **Step 3: Implementar `tira.py`** según spec §3. Lectura: probar `utf-8-sig` y luego `cp1252`; normalizar `\r\n`. Separador: regex `^\s*-{3,}\s*$` por línea. Encabezado de bloque: `^\s*(\d+)\.\s*(.*)$` en la primera línea no vacía del bloque; los bloques sin encabezado se ignoran (así se descarta `TIRA #`). Número de imagen: regex `^(\d+)\D` sobre el nombre; el número 0 cuenta como ubicación (incluye `000.`).
- [ ] **Step 4: Correr y ver que pasan** — `pytest tests/test_tira.py -v` → PASS
- [ ] **Step 5: Commit** — `git commit -m "feat: lector y validación de carpetas de tira"`

---

### Task 2: Configuración y lista de grupos

**Files:**
- Create: `src/publicador/config.py`, `src/publicador/grupos.py`
- Test: `tests/test_config.py`, `tests/test_grupos.py`

**Interfaces:**
- Produces:
  - `carpeta_datos() -> Path`: crea la carpeta si no existe (Global Constraints)
  - `@dataclass Config(carpeta_tiras: str = "", minutos_entre_publicaciones: int = 60, ultimo_dia: str = "", ultima_tira: str = "")`
  - `cargar_config(ruta: Path) -> Config` (si falta o está corrupto, devuelve los valores por defecto) · `guardar_config(ruta: Path, cfg: Config) -> None`
  - `@dataclass Grupo(nombre: str, link: str, activo: bool = True)`
  - `cargar_grupos(ruta: Path) -> list[Grupo]`: solo los grupos válidos, activos e inactivos (`#` = inactivo)
  - `actualizar_grupos(ruta: Path, encontrados: list[tuple[str, str]]) -> int`: combina y reescribe el archivo; devuelve cuántos grupos nuevos hubo
  - `marcar_ignorado(ruta: Path, link: str) -> None`

- [ ] **Step 1: Escribir pruebas que fallen**

```python
def test_config_defecto_y_roundtrip(tmp_path):
    assert cargar_config(tmp_path / "no.json").minutos_entre_publicaciones == 60
    guardar_config(tmp_path / "c.json", Config(carpeta_tiras="C:/T", minutos_entre_publicaciones=30))
    assert cargar_config(tmp_path / "c.json").minutos_entre_publicaciones == 30

def test_config_corrupto(tmp_path): ...  # "{no json" → Config()

def test_actualizar_respeta_marcas(tmp_path):
    r = tmp_path / "grupos.txt"
    r.write_text("A | https://www.facebook.com/groups/1/\n# B | https://www.facebook.com/groups/2/\nC | https://www.facebook.com/groups/3/\n", encoding="utf-8")
    nuevos = actualizar_grupos(r, [("A", ".../groups/1/"), ("B", ".../groups/2/"), ("D", ".../groups/4/")])  # links completos en la prueba
    assert nuevos == 1
    gs = {g.link: g for g in cargar_grupos(r)}
    assert gs[".../groups/2/"].activo is False         # se respeta el #
    assert gs[".../groups/4/"].activo is True
    assert "# (ya no aparece) C | https://www.facebook.com/groups/3/" in r.read_text(encoding="utf-8")

def test_marcar_ignorado(tmp_path): ...    # después de marcar, el grupo queda activo=False; las demás líneas no cambian
def test_lineas_raras(tmp_path): ...       # línea vacía, "solo texto", "  X  |  https://...  " → 1 grupo "X"; al actualizar, la línea "solo texto" se conserva
```

- [ ] **Step 2: Correr y ver que fallan** — `pytest tests/test_config.py tests/test_grupos.py -v` → FAIL
- [ ] **Step 3: Implementar** `config.py` (json, `dataclasses.asdict`, se ignoran claves desconocidas) y `grupos.py` (se parte con `split("|", 1)` y `strip`; la línea es válida si el link empieza con `http`; el `#` se identifica quitando `#` y espacios del inicio y, si existe, el prefijo `(ya no aparece)`; el archivo se lee y escribe en `utf-8`).
- [ ] **Step 4: Correr y ver que pasan** → PASS
- [ ] **Step 5: Commit** — `git commit -m "feat: configuración y lista de grupos"`

---

### Task 3: Historial

**Files:**
- Create: `src/publicador/historial.py`
- Test: `tests/test_historial.py`

**Interfaces:**
- Produces:
  - `@dataclass Registro(fecha_hora: datetime, dia: str, tira: str, numero: int, titulo: str, grupo: str, link_grupo: str, archivo_ubicacion: str, resultado: str)`
  - `class Historial(ruta: Path)` con:
    - `agregar(r: Registro) -> None`: crea el archivo con encabezado si no existe
    - `ultima_publicacion(link: str) -> datetime | None`: solo cuenta `publicado`
    - `publicadas(dia: str, tira: str, fecha: date) -> dict[int, str]`: número → link del grupo, para los `publicado` de esa tira en esa fecha
    - `grupos_usados(dia: str, tira: str, fecha: date) -> set[str]`: links con cualquier resultado en esa tira y fecha

- [ ] **Step 1: Escribir pruebas que fallen**

```python
def test_agregar_y_consultar(tmp_path):
    h = Historial(tmp_path / "h.csv")
    t = datetime(2026, 11, 9, 10, 0)
    h.agregar(Registro(t, "1.lunes", "TIRA 1", 1, "Pantalla", "G1", "L1", "000.ALTAMIRANO.jpeg", "publicado"))
    h.agregar(Registro(t.replace(hour=11), "1.lunes", "TIRA 1", 2, "Tapa", "G2", "L2", "x", "saltado"))
    assert h.ultima_publicacion("L1") == t
    assert h.ultima_publicacion("L2") is None
    assert h.publicadas("1.lunes", "TIRA 1", t.date()) == {1: "L1"}
    assert h.grupos_usados("1.lunes", "TIRA 1", t.date()) == {"L1", "L2"}
    assert (tmp_path / "h.csv").read_bytes().startswith(b"\xef\xbb\xbf")

def test_archivo_inexistente(tmp_path): ...  # consultas devuelven None / {} / set()
```

- [ ] **Step 2: Correr y ver que fallan** → FAIL
- [ ] **Step 3: Implementar** con `csv.DictWriter`/`DictReader`, `encoding="utf-8-sig"`, `newline=""`, fecha ISO `%Y-%m-%d %H:%M:%S`. Se relee el archivo en cada consulta (es chico y así es la única fuente de verdad).
- [ ] **Step 4: Correr y ver que pasan** → PASS
- [ ] **Step 5: Commit** — `git commit -m "feat: historial de publicaciones"`

---

### Task 4: Rotación

**Files:**
- Create: `src/publicador/rotacion.py`
- Test: `tests/test_rotacion.py`

**Interfaces:**
- Consumes: `Grupo` (Task 2), `Historial.ultima_publicacion` (Task 3)
- Produces: `elegir_grupo(grupos: list[Grupo], historial: Historial, ahora: datetime, minutos: int, excluir: set[str], rng: random.Random) -> Grupo | None`

- [ ] **Step 1: Escribir pruebas que fallen**

```python
def test_prefiere_nunca_usado(...)        # G1 usado hace 5 h, G2 nunca → G2
def test_mas_antiguo(...)                 # G1 hace 2 h, G2 hace 5 h → G2
def test_regla_minutos(...)               # G1 hace 59 min (minutos=60), único → None; con 61 min → G1
def test_excluir_e_inactivos(...)         # G1 en excluir, G2 activo=False, G3 libre → G3
def test_empate_al_azar(...)              # 3 nunca usados, rng=Random(1) y Random(2) → el resultado siempre es uno de los 3; con varias semillas salen al menos 2 distintos
def test_sin_grupos(...)                  # [] → None
```

- [ ] **Step 2: Correr y ver que fallan** → FAIL
- [ ] **Step 3: Implementar** según spec §6: se filtra, se ordena por `ultima_publicacion` (los `None` primero) y se elige con `rng.choice` entre los empatados en el primer lugar.
- [ ] **Step 4: Correr y ver que pasan** → PASS
- [ ] **Step 5: Commit** — `git commit -m "feat: rotación de grupos"`

---

### Task 5: Secuencia de una tira (`sesion.py`)

Toda la lógica de la sección 7 y de la tabla de errores del spec, sin Tk ni Playwright directos, para poder probarla con dobles.

**Files:**
- Create: `src/publicador/sesion.py`
- Test: `tests/test_sesion.py`

**Interfaces:**
- Consumes: Tasks 1–4, y el protocolo de Facebook que define este task (Task 6 lo implementa).
- Produces:

```python
class ErrorFacebook(Exception): ...           # vive aquí; facebook.py lo importa

class NavegadorProto(Protocol):
    def sesion_activa(self) -> bool: ...
    def preparar_publicacion(self, link: str, texto: str, archivos: list[Path]) -> None: ...  # lanza ErrorFacebook
    def esperar_resultado(self, controles: "Controles") -> str: ...  # "publicado" | "cerrado" | "saltar" | "detener"
    def cerrar_compositor(self) -> None: ...
    def captura(self, nombre: str) -> Path: ...

class UIProto(Protocol):
    def estado(self, mensaje: str) -> None: ...
    def progreso(self, actual: int, total: int, titulo: str, grupo: str) -> None: ...
    def preguntar(self, mensaje: str, opciones: list[str]) -> str: ...   # bloquea hasta que se responde

@dataclass
class Controles:
    saltar: threading.Event = field(default_factory=threading.Event)
    detener: threading.Event = field(default_factory=threading.Event)

@dataclass
class Resultado:
    publicadas: int
    saltadas: int
    motivo_fin: str     # "terminada" | "detenida" | "sin_grupos"

def ejecutar_tira(tira: Tira, dia: str, nombre_tira: str, fb: NavegadorProto, ui: UIProto,
                  controles: Controles, ruta_grupos: Path, historial: Historial, minutos: int,
                  ahora: Callable[[], datetime] = datetime.now, rng: random.Random | None = None) -> Resultado
```

Comportamiento (spec §7 y §8):
- Se omiten las publicaciones que ya están en `historial.publicadas(dia, nombre_tira, hoy)`. `excluir` empieza con `historial.grupos_usados(...)` y se le agrega cada grupo que se intenta.
- Antes de cada intento: si `controles.detener` está activo, se termina con `"detenida"`. Se limpia `saltar`. Se recargan los grupos desde `ruta_grupos` (por si se editó el archivo).
- Si `not fb.sesion_activa()`: `ui.preguntar("Inicia sesión en el navegador y da clic en Continuar", ["Continuar"])`.
- Archivos = `[pub.imagen, rng.choice(tira.ubicaciones)]`.
- `ErrorFacebook`: se toma `captura`, se registra `error` y se pregunta con opciones `["Reintentar", "Saltar este grupo", "Detener"]`. Reintentar usa el mismo grupo; Saltar se comporta como "saltar".
- `"publicado"` → se registra y sigue con la siguiente. `"cerrado"` → se registra `saltado` y se prueba otro grupo, sin marcarlo. `"saltar"` → `cerrar_compositor`, se registra `saltado`, `marcar_ignorado` y otro grupo. `"detener"` → `cerrar_compositor` y se termina con `"detenida"`.
- Sin grupos: `ui.estado("No hay grupos disponibles ahora")` y se termina con `"sin_grupos"`.
- Al terminar: `ui.estado(f"{nombre_tira} terminada ✅ ({n} publicadas)")`.

- [ ] **Step 1: Escribir pruebas que fallen** (con `FakeFB` que devuelve una lista de resultados programada, `FakeUI` que registra llamadas y responde de una cola, y un `Tira` armado a mano con `tmp_path`)

```python
def test_todo_publicado(...)          # 3 pubs, 5 grupos, FakeFB siempre "publicado" → Resultado(3, 0, "terminada"); 3 grupos distintos; historial con 3 "publicado"
def test_saltar_marca_y_reintenta(...) # resultados ["saltar","publicado"] → la pub 1 queda en otro grupo; el primer grupo tiene activo=False en grupos.txt; cerrar_compositor llamado 1 vez
def test_cerrado_no_marca(...)         # ["cerrado","publicado"] → el primer grupo sigue activo; registro "saltado"
def test_error_reintentar(...)         # preparar lanza ErrorFacebook 1 vez y UI responde "Reintentar" → mismo link las 2 veces; registro "error"; captura llamada
def test_detener(...)                  # ["publicado","detener"] → Resultado(1, 0, "detenida")
def test_reanudar(...)                 # historial ya tiene pub 1 publicada hoy en G1 → solo se preparan las pubs 2 y 3, y nunca en G1
def test_sin_grupos(...)               # 1 grupo, 2 pubs → Resultado(1, 0, "sin_grupos"); ui.estado con "No hay grupos disponibles"
def test_pide_login(...)               # sesion_activa False la 1ª vez → ui.preguntar con "Inicia sesión"
```

- [ ] **Step 2: Correr y ver que fallan** → FAIL
- [ ] **Step 3: Implementar `ejecutar_tira`**
- [ ] **Step 4: Correr y ver que pasan** → PASS
- [ ] **Step 5: Commit** — `git commit -m "feat: secuencia de publicación de una tira"`

---

### Task 6: Navegador de Facebook (`facebook.py`)

**Files:**
- Create: `src/publicador/facebook.py`
- Test: `tests/test_facebook.py` (solo funciones puras; lo demás se prueba a mano con la cuenta)
- Modify: `pyproject.toml` (agregar la dependencia `playwright`)

**Interfaces:**
- Consumes: `ErrorFacebook`, `Controles`, `NavegadorProto` (Task 5)
- Produces:
  - `normalizar_link_grupo(href: str) -> str | None`: `https://www.facebook.com/groups/<id-o-alias>/`, o `None` si no es un link de grupo o si es una ruta especial (`feed`, `discover`, `joins`, `create`, `notifications`)
  - `class Facebook(perfil_dir: Path, capturas_dir: Path)` que implementa `NavegadorProto`, más `abrir() -> None`, `extraer_grupos(ui_estado: Callable[[str], None]) -> list[tuple[str, str]]` y `cerrar() -> None`

Decisiones:
- `abrir`: `sync_playwright().start()` y `chromium.launch_persistent_context(perfil_dir, channel="chrome", headless=False, no_viewport=True)`; si falla, `channel="msedge"`. Si los dos fallan → `ErrorFacebook("No se encontró Chrome ni Edge instalado")`.
- `sesion_activa`: es `False` si la URL contiene `/login` o si hay un `input[name="email"]` visible.
- `extraer_grupos`: `goto("https://www.facebook.com/groups/joins/?nav_source=tab")`, baja con `mouse.wheel` hasta que el número de links `a[href*="/groups/"]` no cambie en 3 vueltas seguidas, y normaliza y quita repetidos. El nombre es el texto visible del link (el primer link no vacío por grupo). Va reportando el avance con `ui_estado(f"{n} grupos encontrados…")`.
- `preparar_publicacion`: `goto(link)`; clic en `get_by_role("button", name=re.compile("Escribe algo", re.I))` (si no está, se prueba `get_by_text(re.compile("Escribe algo", re.I))`); se espera `get_by_role("dialog")` con un `[contenteditable="true"]` dentro, con timeout de 30 s; se pega el texto disparando un evento `paste` sintético con `DataTransfer` (`text/plain`) sobre el contenteditable, vía `evaluate`; `set_input_files` sobre el `input[type=file]` del diálogo (si no existe, se da clic en el botón con `aria-label` que contenga "Foto" y luego se busca el input); se espera hasta 60 s a que no haya barras de progreso (`[role="progressbar"]`) dentro del diálogo. Se instala un listener de clic en fase de captura que pone `window.__pubClick = true` cuando el clic cae dentro de un elemento con `aria-label="Publicar"` o con el texto exacto "Publicar". Cualquier `TimeoutError` de Playwright se convierte en `ErrorFacebook` con un mensaje en español.
- `esperar_resultado`: cada 0.5 s revisa `controles.saltar` → `"saltar"`, `controles.detener` → `"detener"`, y si el diálogo ya no está visible devuelve `"publicado"` si `window.__pubClick` es verdadero, y `"cerrado"` si no.
- `cerrar_compositor`: `Escape`; si aparece el diálogo "¿Descartar publicación?", clic en "Descartar".
- Todos los selectores son constantes al inicio del archivo, para ajustarlos rápido.

- [ ] **Step 1: Escribir pruebas que fallen**

```python
@pytest.mark.parametrize("href,esperado", [
    ("https://www.facebook.com/groups/123456/", "https://www.facebook.com/groups/123456/"),
    ("/groups/compraventaiguala/?ref=bookmarks", "https://www.facebook.com/groups/compraventaiguala/"),
    ("https://web.facebook.com/groups/987/posts/55", "https://www.facebook.com/groups/987/"),
    ("https://www.facebook.com/groups/feed/", None),
    ("https://www.facebook.com/groups/joins/", None),
    ("https://www.facebook.com/profile.php?id=1", None),
])
def test_normalizar_link_grupo(href, esperado):
    assert normalizar_link_grupo(href) == esperado
```

- [ ] **Step 2: Correr y ver que fallan** → FAIL
- [ ] **Step 3: Implementar `facebook.py`**
- [ ] **Step 4: Correr las pruebas** → PASS. Prueba de humo: `python -c "import publicador.facebook"` sin errores.
- [ ] **Step 5: Commit** — `git commit -m "feat: control del navegador para Facebook"`

---

### Task 7: Ventana (`app.py`)

**Files:**
- Create: `src/publicador/app.py`, `src/publicador/__main__.py`

**Interfaces:**
- Consumes: todo lo anterior.
- Produces: `main() -> None`

Decisiones:
- Un hilo `Trabajador` (daemon) es dueño de `Facebook` y procesa comandos de una `queue.Queue`: `("grupos",)` y `("tira", tira, dia, nombre)`. El navegador se abre en el primer comando y se queda abierto.
- `UITk` implementa `UIProto`: `estado` y `progreso` mandan mensajes a una cola que la ventana revisa con `root.after(100, …)`. `preguntar` manda la pregunta, la ventana muestra un `Toplevel` con un botón por opción y el hilo espera la respuesta en una `queue.Queue` de un solo elemento.
- Botones: Cambiar carpeta (`filedialog.askdirectory`), combos de Día y Tira (`listar_subcarpetas`), Escoger carpeta… (el día es el nombre de la carpeta padre), Actualizar grupos, Abrir carpeta de datos (`os.startfile` en Windows, `xdg-open` en otros), Empezar, Saltar este grupo (`controles.saltar.set()`) y Detener (`controles.detener.set()`). Saltar y Detener solo están activos mientras corre una tira; Empezar solo si `tira.ok` y no hay otra tarea corriendo.
- Al escoger una tira, se muestra el resumen en un `Text` de solo lectura: `"N. Título → imagen"` por línea, `"Ubicación: k archivos"` y los errores en rojo.
- Al dar Empezar, si `historial.publicadas(...)` no está vacío: `messagebox.askyesno("Continuar", f"Ya se publicaron {k} de {total}. ¿Seguir con las que faltan?")`. "Sí" = se ejecuta la tira (`ejecutar_tira` omite las ya publicadas); "No" = no se hace nada.
- `config.json` guarda la carpeta, el día y la tira al cambiar.
- Si no hay grupos guardados al dar Empezar: `"Primero da clic en Actualizar grupos"`.

- [ ] **Step 1: Implementar `app.py` y `__main__.py`**
- [ ] **Step 2: Prueba de humo sin pantalla:** `xvfb-run -a python -c "import publicador.app as a; r=a.crear_ventana(); r.update(); r.destroy()"` (exponer `crear_ventana() -> tk.Tk` para esto) → sin errores. Correr toda la suite: `pytest -v` → PASS.
- [ ] **Step 3: Prueba manual del resumen:** apuntar a una carpeta `Tiras/1.lunes/TIRA 1` de prueba armada con los datos de `tests/datos`, tomar una captura y revisar que se ven los 12 renglones.
- [ ] **Step 4: Commit** — `git commit -m "feat: ventana principal"`

---

### Task 8: Empaquetado, CI y LEEME

**Files:**
- Create: `.github/workflows/build.yml`, `LEEME.md`

Decisiones:
- Workflow `build` en `push` y `workflow_dispatch`, `runs-on: windows-latest`, Python 3.12: `pip install -e . pytest pyinstaller`, `pytest -v`, y `pyinstaller --onefile --windowed --name PublicadorTiras src/publicador/__main__.py`. Sube `dist/PublicadorTiras.exe` con `actions/upload-artifact@v4` con el nombre `PublicadorTiras`.
- `LEEME.md` (en español sencillo): descargar el `.exe` desde Actions → Artifacts; primera vez: abrirlo, escoger la carpeta Tiras, dar "Actualizar grupos" e iniciar sesión en el navegador que se abre; publicar una tira; dónde están `grupos.txt` e `historial.csv`; qué hacer si Windows SmartScreen avisa ("Más información → Ejecutar de todas formas"); recomendación de repartir las publicaciones a lo largo del día.

- [ ] **Step 1: Escribir el workflow y el LEEME**
- [ ] **Step 2: Validar el YAML:** `python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/build.yml'))"` → sin error
- [ ] **Step 3: Commit** — `git commit -m "build: exe para Windows con GitHub Actions y LEEME"`
- [ ] **Step 4: Push** al repo privado y confirmar que el job `build` termina en verde y deja el artifact `PublicadorTiras`.
