# Cuentas y modo automático — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Escoger la cuenta (perfil o Página) y publicar en automático con ritmo ajustable, avisos y detección de bloqueo.

**Architecture:** Nuevo módulo `cuentas.py`; `historial`, `config` y `sesion` aceptan cuenta y modo; `facebook.py` gana menú de perfiles, `publicar()` y detección de bloqueo; `app.py` agrega los controles.

**Tech Stack:** igual que el plan original.

**Spec:** `docs/superpowers/specs/2026-11-09-cuentas-y-modo-automatico-design.md`

## Global Constraints

- Mínimo de espera entre publicaciones en automático: **2 minutos**, no se puede bajar.
- Pausa de «revisión» antes del clic: 5–15 s al azar.
- Umbrales de aviso: 24 y 48 publicadas por cuenta en el día; 3 errores seguidos.
- Resultado `bloqueo` en historial; filas sin `cuenta` = cuenta principal.
- Todo texto al usuario en español.

## Review Focus

1. Datos existentes (grupos.txt y historial sin columna cuenta) no deben perderse al actualizar → pruebas en Tasks 1–2.
2. Reanudar una tira tras cambiar de cuenta no debe repetir anuncios ya publicados con otra cuenta → Task 3.
3. Detener/Saltar deben responder durante las esperas largas → Task 3.
4. En automático, un error después de publicar no debe reintentar el mismo anuncio en otro grupo → Task 3.
5. Cerrar el programa durante una espera no debe colgarse → Task 5.

---

### Task 1: Cuentas y configuración

**Files:** Create `src/publicador/cuentas.py`; Modify `src/publicador/config.py`; Tests `tests/test_cuentas.py`, `tests/test_config.py`

**Produces:**
- `@dataclass Cuenta(nombre: str, tipo: str)`; `cargar_cuentas(ruta) -> tuple[list[Cuenta], str]` (cuentas, última); `guardar_cuentas(ruta, cuentas, ultima)`
- `principal(cuentas) -> Cuenta | None` (primer `perfil`, o el primero)
- `ruta_grupos(datos: Path, cuenta: str) -> Path` → `datos/grupos/<slug>.txt` (slug: letras/números/guion, sin acentos)
- `migrar_grupos(datos: Path, cuenta_principal: str) -> None`: si existe `datos/grupos.txt` y no el de la cuenta, lo mueve
- `Config` gana `modo: str = "revision"`, `espera_min: int = 5`, `espera_max: int = 10`, `ultima_cuenta: str = ""`; `ajustar_espera(cfg) -> None` aplica mín ≥ 2 y máx ≥ mín

Tests: roundtrip de cuentas; json corrupto → `([], "")`; slug con acentos y espacios; migración mueve y no pisa uno existente; `ajustar_espera` (1→2, máx<mín).

### Task 2: Historial por cuenta

**Files:** Modify `src/publicador/historial.py`; Test `tests/test_historial.py`

**Produces:** `Registro` gana `cuenta: str = ""` (último campo); `CAMPOS` agrega `cuenta`; `Historial(ruta, cuenta_principal: str = "")`;
`ultimas_publicaciones(cuenta: str | None = None)`, `grupos_usados(dia, tira, fecha, cuenta: str | None = None)`,
`publicadas_hoy_cuenta(cuenta, fecha) -> int`, `bloqueada_hoy(cuenta, fecha) -> bool`. `publicadas()` no filtra por cuenta.
Archivo con encabezado viejo (sin `cuenta`) se reescribe con la columna al agregar.

Tests: filas viejas cuentan para la principal; filtros por cuenta; publicadas() ignora cuenta; encabezado viejo migra; bloqueada_hoy.

### Task 3: Secuencia con cuenta y modo automático

**Files:** Modify `src/publicador/sesion.py`, `src/publicador/rotacion.py`; Test `tests/test_sesion.py`

**Produces:**
- `class CuentaBloqueada(Exception)` con `.mensaje`; `class GrupoSinPermiso(ErrorFacebook)`
- `NavegadorProto` gana `publicar(self) -> None`
- `UIProto` gana `aviso(self, nivel: str, mensaje: str) -> None`
- `@dataclass Ritmo(modo: str = "revision", espera_min: int = 5, espera_max: int = 10)`
- `ejecutar_tira(..., cuenta: str = "", ritmo: Ritmo | None = None, dormir: Callable[[float], None] = time.sleep)`; `Resultado` gana `cuenta_bloqueada: str = ""`, `mensaje_bloqueo: str = ""`; `motivo_fin` puede ser `"bloqueada"`
- `elegir_grupo(..., cuenta: str | None = None)`

Comportamiento: spec §4–§6. Las esperas se hacen en pasos de 1 s con `dormir`, revisando `detener`/`saltar` y mostrando `ui.estado("Siguiente publicación en m:ss")`. No hay espera después de la última publicación.

Tests: auto publica y llama `publicar()`; esperas dentro del rango; detener durante espera; grupo sin permiso se ignora en esa cuenta sin preguntar; error al preparar en auto prueba otro grupo sin preguntar; fallo tras publicar en auto pasa a la siguiente pub; bloqueo → `Resultado.motivo_fin == "bloqueada"` y registro `bloqueo`; avisos 24/48 y 3 errores seguidos; reanudar no repite pubs hechas por otra cuenta; modo revisión sigue igual (pruebas existentes).

### Task 4: Facebook: perfiles, publicar, bloqueo

**Files:** Modify `src/publicador/facebook.py`; Create `tests/datos/menu_cuentas_falso.html`, `tests/datos/bloqueo_falso.html`; Modify `tests/datos/grupo_falso.html`; Test `tests/test_facebook.py`

**Produces:** `leer_cuentas() -> list[tuple[str, str]]`, `cuenta_actual() -> str | None`, `cambiar_cuenta(nombre: str) -> None` (ErrorFacebook si no se logra), `publicar() -> None`, `revisar_bloqueo() -> None` (lanza `CuentaBloqueada`), `GrupoSinPermiso` cuando no aparece el compositor.

### Task 5: Ventana

**Files:** Modify `src/publicador/app.py`; Test `tests/test_app.py`

Combo Cuenta + «Actualizar cuentas»; modo (radio); mín/máx (spinbox) con aviso de riesgo en vivo; franja de avisos; flujo «Seguir con otra cuenta» tras bloqueo; aviso al escoger cuenta bloqueada hoy; grupos y conteo por cuenta.

### Task 6: LEEME, build y publicación

LEEME con cuentas, modo automático y riesgos; push; CI verde; release.
