"""Todo lo que depende de Facebook y del navegador vive aquí (spec §4, §7).

Si Facebook cambia su página, normalmente basta con ajustar las constantes de abajo.
"""
from __future__ import annotations

import re
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from .grupos import normalizar_link_grupo  # noqa: F401 (se usa y se reexporta)
from .sesion import (Controles, CuentaBloqueada, ErrorFacebook, GrupoSinPermiso, NavegadorCerrado,
                     SesionCerrada)

# --- Selectores y textos (ajustar aquí si Facebook cambia) -----------------------------
URL_TUS_GRUPOS = "https://www.facebook.com/groups/joins/?nav_source=tab"
TEXTO_ABRIR_COMPOSITOR = re.compile(r"Escribe algo|Crea una publicaci[oó]n p[uú]blica|Write something", re.I)
SEL_DIALOGO = '[role="dialog"]'
SEL_EDITOR = '[contenteditable="true"]'
SEL_INPUT_ARCHIVOS = 'input[type="file"]'
SEL_BOTON_FOTO = '[aria-label*="Foto" i], [aria-label*="Photo" i]'
SEL_PROGRESO = '[role="progressbar"]'
SEL_LOGIN = 'input[name="email"], input[name="pass"]'
TEXTO_PUBLICAR = "Publicar"
TEXTO_DESCARTAR = re.compile(r"^\s*Descartar\s*$", re.I)
SEL_AVISO = '[role="alert"], [role="alertdialog"]'
TEXTO_AVISO_ERROR = re.compile(r"no se pudo|no se puede publicar|algo sali[oó] mal|intenta(lo)? de nuevo|"
                               r"se produjo un error|ocurri[oó] un error", re.I)
ESPERA_AVISO_S = 3.5
ESPERA_CIERRE_S = 1.5  # el compositor debe seguir cerrado este tiempo para contar como cerrado
# Menú de cuenta (foto de arriba a la derecha) y perfiles.
URL_INICIO = "https://www.facebook.com/"
SEL_MENU_CUENTA = ('[aria-label="Tu perfil"], [aria-label="Your profile"], '
                   '[aria-label="Cuenta"], [aria-label="Account"]')
TEXTO_VER_PERFILES = re.compile(r"Ver todos los perfiles|See all profiles", re.I)
SEL_PERFIL = '[role="radio"], [role="menuitemradio"]'
SEL_PUBLICAR_ACTIVO = '[aria-label="Publicar"]:not([aria-disabled="true"])'
ESPERA_BOTON_PUBLICAR_MS = 120_000
# Señales de bloqueo o verificación.
TEXTO_BLOQUEO = re.compile(r"bloquead[oa]s? temporalmente|est[aá]s bloquead|restringid|confirma tu identidad|"
                           r"revisi[oó]n de seguridad|actividad sospechosa|limitamos|demasiado r[aá]pido|"
                           r"no puedes usar esta funci[oó]n|can.t use this feature|we limit how often|"
                           r"temporarily blocked|you.re blocked|restricted|confirm your identity", re.I)
SEL_AVISOS_BLOQUEO = '[role="dialog"], [role="alertdialog"], [role="alert"]'

_JS_ESCUCHAR_PUBLICAR = """
(texto) => {
  window.__pubClick = false;
  if (window.__pubListener) return;
  window.__pubListener = true;
  document.addEventListener('click', (e) => {
    let el = e.target;
    while (el && el !== document) {
      const etiqueta = el.getAttribute && el.getAttribute('aria-label');
      const rol = el.getAttribute && el.getAttribute('role');
      if (el.getAttribute && el.getAttribute('aria-disabled') === 'true') return;
      if (etiqueta === texto || ((rol === 'button' || el.tagName === 'BUTTON') && el.innerText && el.innerText.trim() === texto)) {
        window.__pubClick = true;
        return;
      }
      el = el.parentNode;
    }
  }, true);
}
"""

_JS_PEGAR = """
(el, texto) => {
  el.focus();
  const dt = new DataTransfer();
  dt.setData('text/plain', texto);
  el.dispatchEvent(new ClipboardEvent('paste', {clipboardData: dt, bubbles: true, cancelable: true}));
  return el.innerText;
}
"""

_JS_LINKS_GRUPOS = """
() => Array.from(document.querySelectorAll('a[href*="/groups/"]')).map(a => [a.href, (a.innerText || '').trim()])
"""


def _solo_letras(texto: str) -> str:
    """Solo letras y números, en minúsculas: para comparar sin emojis ni espacios."""
    return "".join(c for c in (texto or "").lower() if c.isalnum())


class Facebook:
    """Controla un navegador con un perfil propio donde queda guardada la sesión.

    Todos los métodos deben llamarse desde el mismo hilo (requisito de Playwright).
    """

    def __init__(self, perfil_dir: Path, capturas_dir: Path,
                 canales: tuple[str | None, ...] = ("chrome", "msedge", None), headless: bool = False):
        self.perfil_dir = Path(perfil_dir)
        self.capturas_dir = Path(capturas_dir)
        self.canales = canales
        self.headless = headless
        self.url_tus_grupos = URL_TUS_GRUPOS
        self.timeout_compositor_ms = 30_000
        self.timeout_subida_s = 60
        self.pausa_scroll_s = 2.0
        self.url_inicio = URL_INICIO
        self.pausa_cambio_s = 4.0
        self._pw = None
        self._ctx = None
        self.pagina = None
        self._dialogo = None
        self._avisos_previos: set[str] = set()

    # --- ciclo de vida ---------------------------------------------------------------
    @property
    def cerrado(self) -> bool:
        try:
            return self.pagina is None or self.pagina.is_closed()
        except Exception:
            return True

    def abrir(self) -> None:
        if not self.cerrado:
            return
        if self._pw is not None:  # el navegador se cerró a mano: se limpia y se abre otro
            try:
                self.cerrar()
            except Exception:
                self._ctx = self._pw = self.pagina = self._dialogo = None
        from playwright.sync_api import sync_playwright

        self.perfil_dir.mkdir(parents=True, exist_ok=True)
        self._pw = sync_playwright().start()
        ultimo_error: Exception | None = None
        for canal in self.canales:
            try:
                opciones = dict(headless=self.headless, no_viewport=True, locale="es-MX",
                                args=["--disable-notifications"])
                if canal:
                    opciones["channel"] = canal
                self._ctx = self._pw.chromium.launch_persistent_context(str(self.perfil_dir), **opciones)
                break
            except Exception as e:
                ultimo_error = e
                texto = str(e).lower()
                # Solo se prueba otro navegador si este no está instalado; si no, se podría perder la sesión.
                if not any(k in texto for k in ("is not found", "doesn't exist", "does not exist", "not installed",
                                                "no such file", "executable")):
                    break
        if self._ctx is None:
            self._pw.stop()
            self._pw = None
            raise ErrorFacebook("No se pudo abrir el navegador. Revisa que no haya otra ventana del programa "
                                f"abierta y que Chrome o Edge estén instalados. (Detalle: {ultimo_error})")
        self.pagina = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()

    def cerrar(self) -> None:
        try:
            if self._ctx is not None:
                self._ctx.close()
        finally:
            if self._pw is not None:
                self._pw.stop()
            self._ctx = self._pw = self.pagina = self._dialogo = None

    # --- utilidades ------------------------------------------------------------------
    def sesion_activa(self) -> bool:
        url = self.pagina.url or ""
        if "/login" in url or "/checkpoint" in url:
            return False
        try:
            return not self.pagina.locator(SEL_LOGIN).first.is_visible()
        except Exception:
            return True

    def captura(self, nombre: str) -> Path:
        self.capturas_dir.mkdir(parents=True, exist_ok=True)
        limpio = re.sub(r"[^\w\-]+", "_", nombre)
        ruta = self.capturas_dir / f"{limpio}_{datetime.now():%Y%m%d_%H%M%S}.png"
        try:
            self.pagina.screenshot(path=str(ruta))
        except Exception:
            pass
        return ruta

    # --- grupos ----------------------------------------------------------------------
    def extraer_grupos(self, ui_estado: Callable[[str], None]) -> list[tuple[str, str]]:
        self.pagina.goto(self.url_tus_grupos)
        time.sleep(self.pausa_scroll_s)
        nombres: dict[str, str] = {}
        estables = 0
        anterior = -1
        for _ in range(500):
            for href, texto in self.pagina.evaluate(_JS_LINKS_GRUPOS):
                link = normalizar_link_grupo(href)
                if link and (link not in nombres or (not nombres[link] and texto)):
                    nombres[link] = texto.splitlines()[0].strip() if texto else ""
            ui_estado(f"{len(nombres)} grupos encontrados…")
            if len(nombres) == anterior:
                estables += 1
                if estables >= 5:
                    break
            else:
                estables = 0
                anterior = len(nombres)
            self.pagina.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            ancho, alto = self.pagina.evaluate("[window.innerWidth, window.innerHeight]")
            self.pagina.mouse.move(ancho / 2, alto / 2)  # la rueda se aplica donde está el mouse
            self.pagina.mouse.wheel(0, 4000)
            time.sleep(self.pausa_scroll_s)
        return [(nombre or link, link) for link, nombre in nombres.items()]

    # --- publicación -----------------------------------------------------------------
    def preparar_publicacion(self, link: str, texto: str, archivos: list[Path]) -> None:
        from playwright.sync_api import Error as ErrorPW

        if self.cerrado:
            raise NavegadorCerrado()
        try:
            self.pagina.goto(link)
            if not self.sesion_activa():
                raise SesionCerrada()
            self.revisar_bloqueo()
            self._abrir_compositor()
            self.pagina.evaluate(_JS_ESCUCHAR_PUBLICAR, TEXTO_PUBLICAR)
            self._pegar_texto(texto)
            self._adjuntar(archivos)
            self._avisos_previos = set(self._textos_de_avisos())
        except ErrorPW as e:
            if self.cerrado or "closed" in str(e).lower():
                raise NavegadorCerrado() from e
            raise ErrorFacebook(f"Facebook no respondió como se esperaba ({e.__class__.__name__})") from e

    def _abrir_compositor(self) -> None:
        p = self.pagina
        boton = p.get_by_role("button", name=TEXTO_ABRIR_COMPOSITOR)
        try:
            boton.first.wait_for(state="visible", timeout=self.timeout_compositor_ms)
        except Exception:
            boton = p.get_by_text(TEXTO_ABRIR_COMPOSITOR)
            if boton.count() == 0:
                self.revisar_bloqueo()
                # Solo se concluye «sin permiso» si la página sí terminó de cargar (no por internet lento).
                try:
                    cargada = p.evaluate("document.readyState") == "complete"
                except Exception:
                    cargada = False
                if not cargada:
                    raise ErrorFacebook("El grupo no terminó de cargar.")
                raise GrupoSinPermiso("no aparece el cuadro «Escribe algo…»")
        boton.first.click()
        dialogo = p.locator(SEL_DIALOGO).filter(has=p.locator(SEL_EDITOR)).last
        try:
            dialogo.wait_for(state="visible", timeout=self.timeout_compositor_ms)
        except Exception as e:
            raise ErrorFacebook("No se abrió la ventana para crear la publicación.") from e
        # Se marca la ventana: así se sigue reconociendo aunque Facebook cambie de vista adentro
        # (editar foto, agregar a tu publicación…) y el editor desaparezca un momento.
        marca = str(time.monotonic_ns())
        dialogo.evaluate("(el, m) => el.setAttribute('data-publicador', m)", marca)
        self._dialogo = p.locator(f'[data-publicador="{marca}"]')

    def _pegar_texto(self, texto: str) -> None:
        editor = self._dialogo.locator(SEL_EDITOR).first
        editor.click()
        # Facebook puede recordar un borrador: se limpia antes de pegar.
        self.pagina.keyboard.press("Control+A")
        self.pagina.keyboard.press("Delete")
        editor.evaluate(_JS_PEGAR, texto)
        muestra = _solo_letras(texto)[:30]
        if not muestra:
            return
        # Facebook (Lexical) aplica el pegado un instante después: se espera antes de revisar.
        for _ in range(8):
            self.pagina.wait_for_timeout(200)
            if muestra in _solo_letras(editor.inner_text()):
                return
        # Respaldo: se borra lo que haya y se escribe como si se tecleara.
        editor.click()
        self.pagina.keyboard.press("Control+A")
        self.pagina.keyboard.press("Delete")
        self.pagina.keyboard.insert_text(texto)

    def _adjuntar(self, archivos: list[Path]) -> None:
        rutas = [str(a) for a in archivos]
        entrada = self._dialogo.locator(SEL_INPUT_ARCHIVOS)
        if entrada.count() > 0:
            entrada.first.set_input_files(rutas)
        else:
            foto = self._dialogo.locator(SEL_BOTON_FOTO)
            if foto.count() == 0:
                raise ErrorFacebook("No se encontró el botón para agregar fotos o videos.")
            try:
                # Si el botón abre la ventana «Abrir» de Windows, se contesta sin que aparezca.
                with self.pagina.expect_file_chooser(timeout=5_000) as selector:
                    foto.first.click()
                selector.value.set_files(rutas)
            except Exception:
                entrada = self._dialogo.locator(SEL_INPUT_ARCHIVOS)
                try:
                    entrada.first.wait_for(state="attached", timeout=10_000)
                except Exception as e:
                    raise ErrorFacebook("No se encontró dónde subir los archivos.") from e
                entrada.first.set_input_files(rutas)
        # Se espera a que terminen de subir (sobre todo el video). Si tarda más, se deja así:
        # Facebook no deja dar clic en Publicar hasta que termine.
        time.sleep(1)
        limite = time.monotonic() + self.timeout_subida_s
        while self._barras_visibles() > 0 and time.monotonic() < limite:
            time.sleep(0.5)

    def _barras_visibles(self) -> int:
        try:
            barras = self._dialogo.locator(SEL_PROGRESO)
            return sum(1 for i in range(barras.count()) if barras.nth(i).is_visible())
        except Exception:
            return 0

    def _textos_de_avisos(self) -> list[str]:
        textos = []
        avisos = self.pagina.locator(SEL_AVISO)
        for i in range(avisos.count()):
            a = avisos.nth(i)
            if a.is_visible():
                textos.append((a.inner_text() or "").strip())
        return textos

    def _dialogo_abierto(self) -> bool:
        if self._dialogo is None:
            return False
        try:
            if self._dialogo.count() > 0 and self._dialogo.is_visible():
                return True
            # Por si Facebook redibujó la ventana y se perdió la marca: cualquier compositor visible.
            otro = self.pagina.locator(SEL_DIALOGO).filter(has=self.pagina.locator(SEL_EDITOR))
            return any(otro.nth(i).is_visible() for i in range(otro.count()))
        except Exception:
            return False

    def _sigue_cerrado(self) -> bool:
        """Confirma que el compositor sigue cerrado un momento (no fue solo un cambio de vista)."""
        limite = time.monotonic() + ESPERA_CIERRE_S
        while time.monotonic() < limite:
            if self._dialogo_abierto():
                return False
            try:
                self.pagina.wait_for_timeout(250)
            except Exception as e:
                raise NavegadorCerrado() from e
        return True

    def esperar_resultado(self, controles: Controles) -> str:
        limite = getattr(controles, "limite_s", None)
        fin = time.monotonic() + limite if limite else None
        while True:
            if self.cerrado:
                raise NavegadorCerrado()
            if fin is not None and time.monotonic() > fin:
                return "sin_respuesta"
            # Primero se revisa si ya se publicó: gana a un «Saltar» apretado justo después.
            if not self._dialogo_abierto() and self._sigue_cerrado():
                if self.cerrado:
                    raise NavegadorCerrado()
                try:
                    publicado = bool(self.pagina.evaluate("window.__pubClick === true"))
                except Exception:
                    if self.cerrado:
                        raise NavegadorCerrado()
                    publicado = False
                try:
                    self.revisar_bloqueo()
                except CuentaBloqueada as e:
                    raise CuentaBloqueada(e.mensaje, publicado=publicado) from e
                if not publicado:
                    return "cerrado"
                return "fallo" if self._hay_aviso_de_error() else "publicado"
            if controles.detener.is_set():
                return "detener"
            if controles.saltar.is_set():
                return "saltar"
            try:
                self.pagina.wait_for_timeout(500)
            except Exception as e:
                raise NavegadorCerrado() from e

    def _hay_aviso_de_error(self) -> bool:
        """Después de publicar, Facebook puede mostrar un aviso de error: se espera un momento a verlo."""
        limite = time.monotonic() + ESPERA_AVISO_S
        while time.monotonic() < limite:
            try:
                for texto in self._textos_de_avisos():
                    if texto not in self._avisos_previos and TEXTO_AVISO_ERROR.search(texto):
                        return True
                self.pagina.wait_for_timeout(250)
            except Exception:
                if self.cerrado:
                    raise NavegadorCerrado()
                return False
        return False

    def cerrar_compositor(self) -> None:
        if not self._dialogo_abierto():
            return
        try:
            self.pagina.keyboard.press("Escape")
            descartar = self.pagina.get_by_role("button", name=TEXTO_DESCARTAR)
            try:
                descartar.first.wait_for(state="visible", timeout=3000)
                descartar.first.click()
            except Exception:
                pass
        except Exception:
            pass

    # --- bloqueo -----------------------------------------------------------------------
    def revisar_bloqueo(self) -> None:
        """Lanza CuentaBloqueada si Facebook muestra una señal de bloqueo o verificación."""
        url = self.pagina.url or ""
        if "/checkpoint" in url:
            raise CuentaBloqueada("Facebook pidió una verificación de seguridad.")
        try:
            avisos = self.pagina.locator(SEL_AVISOS_BLOQUEO)
            for i in range(avisos.count()):
                a = avisos.nth(i)
                if not a.is_visible() or a.locator(SEL_EDITOR).count() > 0:
                    continue  # la ventana donde se escribe el anuncio no es un aviso
                texto = " ".join((a.inner_text() or "").split())
                if TEXTO_BLOQUEO.search(texto):
                    raise CuentaBloqueada(texto[:200])
        except CuentaBloqueada:
            raise
        except Exception:
            if self.cerrado:
                raise NavegadorCerrado()

    # --- publicar solo -----------------------------------------------------------------
    def publicar(self, controles: Controles | None = None) -> bool:
        """Da clic en «Publicar» cuando esté activo (espera a que terminen de subir los archivos).

        Devuelve False, sin dar clic, si mientras espera se pide Saltar o Detener.
        """
        boton = self._dialogo.locator(SEL_PUBLICAR_ACTIVO).last
        fin = time.monotonic() + ESPERA_BOTON_PUBLICAR_MS / 1000
        while time.monotonic() < fin:
            if controles is not None and (controles.saltar.is_set() or controles.detener.is_set()):
                return False
            if self.cerrado:
                raise NavegadorCerrado()
            try:
                if boton.count() > 0 and boton.is_visible():
                    boton.click()
                    return True
            except Exception:
                if self.cerrado:
                    raise NavegadorCerrado()
            time.sleep(0.5)
        self.revisar_bloqueo()
        raise ErrorFacebook("El botón «Publicar» no se activó.")

    def asegurar_cuenta(self, nombre: str) -> None:
        """Confirma que la cuenta activa sea esta; si no, se cambia (o lanza ErrorFacebook)."""
        self.cambiar_cuenta(nombre)

    # --- cuentas -----------------------------------------------------------------------
    def _abrir_lista_perfiles(self):
        """Abre el menú de cuenta y la lista de perfiles. Devuelve el localizador de perfiles."""
        p = self.pagina
        menu = p.locator(SEL_MENU_CUENTA).first
        try:
            menu.wait_for(state="visible", timeout=self.timeout_compositor_ms)
        except Exception as e:
            raise ErrorFacebook("No se encontró el menú de cuenta (tu foto, arriba a la derecha).") from e
        menu.click()
        perfiles = p.locator('[role="dialog"], [role="menu"]').locator(SEL_PERFIL)
        ver = p.get_by_text(TEXTO_VER_PERFILES)
        try:
            ver.first.wait_for(state="visible", timeout=5_000)
            ver.first.click()
        except Exception:
            pass  # algunas versiones muestran los perfiles directo
        try:
            perfiles.first.wait_for(state="visible", timeout=10_000)
        except Exception as e:
            self.pagina.keyboard.press("Escape")
            raise ErrorFacebook("No se encontró la lista de perfiles en el menú de cuenta.") from e
        return perfiles

    @staticmethod
    def _nombre_perfil(elemento) -> str:
        nombre = (elemento.get_attribute("aria-label") or elemento.inner_text() or "").strip()
        return nombre.splitlines()[0].strip() if nombre else ""

    def _ir_a_inicio(self) -> None:
        if not (self.pagina.url or "").startswith(self.url_inicio.split("?")[0]):
            self.pagina.goto(self.url_inicio)
        if not self.sesion_activa():
            raise SesionCerrada()

    def leer_cuentas(self) -> list[tuple[str, str]]:
        """Perfiles disponibles: el primero es el perfil personal; los demás, Páginas."""
        self._ir_a_inicio()
        perfiles = self._abrir_lista_perfiles()
        nombres: list[str] = []
        for i in range(perfiles.count()):
            n = self._nombre_perfil(perfiles.nth(i))
            if n and n not in nombres:
                nombres.append(n)
        self.pagina.keyboard.press("Escape")
        return [(n, "perfil" if i == 0 else "pagina") for i, n in enumerate(nombres)]

    def cuenta_actual(self) -> str | None:
        self._ir_a_inicio()
        perfiles = self._abrir_lista_perfiles()
        actual = None
        for i in range(perfiles.count()):
            el = perfiles.nth(i)
            if el.get_attribute("aria-checked") == "true":
                actual = self._nombre_perfil(el)
                break
        self.pagina.keyboard.press("Escape")
        return actual

    def cambiar_cuenta(self, nombre: str) -> None:
        if self.cuenta_actual() == nombre:
            return
        perfiles = self._abrir_lista_perfiles()
        for i in range(perfiles.count()):
            el = perfiles.nth(i)
            if self._nombre_perfil(el) == nombre:
                el.click()
                break
        else:
            self.pagina.keyboard.press("Escape")
            raise ErrorFacebook(f"No se encontró la cuenta «{nombre}» en el menú de perfiles. "
                                "Da clic en «Actualizar cuentas».")
        try:
            self.pagina.wait_for_load_state("load", timeout=30_000)
        except Exception:
            pass
        time.sleep(self.pausa_cambio_s)
        if self.cuenta_actual() != nombre:
            raise ErrorFacebook(f"No se pudo cambiar a la cuenta «{nombre}».")
