"""Ventana principal (Tkinter) y el hilo de trabajo que controla el navegador."""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import traceback
import tkinter as tk
from datetime import date, datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import estilo
from .config import (Config, ajustar_espera, bloquear_instancia, cargar_config, carpeta_datos,
                     guardar_config)
from .cuentas import Cuenta, cargar_cuentas, guardar_cuentas, migrar_grupos, principal, ruta_grupos
from .grupos import actualizar_grupos, cargar_grupos
from .historial import Historial
from .sesion import (DETENER, Controles, ErrorFacebook, NavegadorCerrado, Ritmo, SesionCerrada,
                     ejecutar_tira)
from .tira import Tira, leer_tira, listar_subcarpetas

TITULO = "Publicador de Tiras"
RECURSOS = Path(__file__).parent / "recursos"


def escribir_log(datos: Path, texto: str) -> None:
    """Anota un error técnico en errores.log; si no se puede, no pasa nada."""
    try:
        with (Path(datos) / "errores.log").open("a", encoding="utf-8") as f:
            f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}\n{texto}\n")
    except OSError:
        pass


class UITk:
    """Implementa UIProto pasando mensajes a la ventana por una cola (seguro entre hilos)."""

    def __init__(self, cola: queue.Queue):
        self.cola = cola

    def estado(self, mensaje: str) -> None:
        self.cola.put(("estado", mensaje))

    def progreso(self, actual: int, total: int, titulo: str, grupo: str) -> None:
        self.cola.put(("progreso", actual, total, titulo, grupo))

    def aviso(self, nivel: str, mensaje: str) -> None:
        self.cola.put(("aviso", nivel, mensaje))

    def preguntar(self, mensaje: str, opciones: list[str]) -> str:
        respuesta: queue.Queue = queue.Queue(maxsize=1)
        self.cola.put(("preguntar", mensaje, opciones, respuesta))
        return respuesta.get()


class Trabajador(threading.Thread):
    """Único dueño del navegador: Playwright exige usarlo siempre desde el mismo hilo."""

    def __init__(self, datos: Path, ui: UITk, cola_ui: queue.Queue):
        super().__init__(daemon=True)
        self.datos = datos
        self.ui = ui
        self.cola_ui = cola_ui
        self.comandos: queue.Queue = queue.Queue()
        self.fb = None

    def _navegador(self):
        if self.fb is None:
            from .facebook import Facebook
            fb = Facebook(self.datos / "navegador", self.datos / "capturas")
            fb.abrir()
            self.fb = fb
        return self.fb

    def run(self) -> None:
        while True:
            cmd = self.comandos.get()
            if cmd[0] == "salir":
                if self.fb is not None:
                    try:
                        self.fb.cerrar()
                    except Exception:
                        pass
                return
            try:
                if cmd[0] == "cuentas":
                    self._cuentas()
                elif cmd[0] == "grupos":
                    self._grupos(*cmd[1:])
                elif cmd[0] == "tira":
                    self._tira(*cmd[1:])
            except NavegadorCerrado:
                self._olvidar_navegador()
                self.cola_ui.put(("fin", "⚠️ Se cerró el navegador. Da clic otra vez para continuar "
                                         "(se abrirá uno nuevo)."))
            except SesionCerrada:
                self.cola_ui.put(("fin", "⚠️ Facebook pide iniciar sesión. Inicia sesión en el navegador y "
                                         "vuelve a intentar."))
            except ErrorFacebook as e:
                self.cola_ui.put(("fin", f"⚠️ {e}"))
            except Exception as e:
                escribir_log(self.datos, traceback.format_exc())
                if self.fb is not None and self.fb.cerrado:
                    self._olvidar_navegador()
                self.cola_ui.put(("fin", f"⚠️ Error inesperado: {e} (detalle en errores.log)"))

    def _olvidar_navegador(self) -> None:
        if self.fb is not None:
            try:
                self.fb.cerrar()
            except Exception:
                pass
        self.fb = None

    def _asegurar_sesion(self, fb) -> None:
        while not fb.sesion_activa():
            resp = self.ui.preguntar("Inicia sesión en Facebook en el navegador que se abrió y luego da clic "
                                     "en Continuar", ["Continuar", "Cancelar"])
            if resp != "Continuar":
                raise ErrorFacebook("Se canceló.")
            fb.pagina.goto("https://www.facebook.com/")

    def _inicio(self):
        fb = self._navegador()
        self.ui.estado("Abriendo Facebook…")
        fb.pagina.goto("https://www.facebook.com/")
        self._asegurar_sesion(fb)
        return fb

    def _cambiar(self, fb, cuenta: str) -> None:
        if cuenta:
            self.ui.estado(f"Revisando que esté activa la cuenta «{cuenta}»…")
            fb.cambiar_cuenta(cuenta)

    def _cuentas(self) -> None:
        fb = self._inicio()
        self.ui.estado("Leyendo las cuentas del menú de Facebook…")
        cuentas = fb.leer_cuentas()
        if not cuentas:
            self.cola_ui.put(("fin", "⚠️ No se encontraron cuentas en el menú de Facebook."))
            return
        self.cola_ui.put(("cuentas", cuentas))
        self.cola_ui.put(("fin", f"✅ {len(cuentas)} cuentas encontradas."))

    def _grupos(self, cuenta: str = "", ruta: Path | None = None) -> None:
        fb = self._inicio()
        self._cambiar(fb, cuenta)
        encontrados = fb.extraer_grupos(self.ui.estado)
        if not encontrados:
            self.cola_ui.put(("fin", "⚠️ No se encontró ningún grupo. ¿Es la cuenta correcta?"))
            return
        nuevos = actualizar_grupos(ruta or self.datos / "grupos.txt", encontrados)
        de = f" de «{cuenta}»" if cuenta else ""
        self.cola_ui.put(("fin", f"✅ {len(encontrados)} grupos encontrados{de} ({nuevos} nuevos)."))

    def _tira(self, tira: Tira, dia: str, nombre: str, controles: Controles, minutos: int,
              cuenta: str = "", ritmo: Ritmo | None = None, ruta: Path | None = None,
              cuenta_principal: str = "") -> None:
        fb = self._inicio()
        self._cambiar(fb, cuenta)
        r = ejecutar_tira(tira, dia, nombre, fb, self.ui, controles, ruta or self.datos / "grupos.txt",
                          Historial(self.datos / "historial.csv", cuenta_principal), minutos,
                          cuenta=cuenta, ritmo=ritmo)
        if r.motivo_fin == "bloqueada":
            self.cola_ui.put(("bloqueada", r.cuenta_bloqueada, r.mensaje_bloqueo, (tira, dia, nombre)))
            return
        if r.motivo_fin == "terminada":
            msg = f"{nombre} terminada ✅ ({r.publicadas} publicadas, {r.saltadas} grupos saltados)"
        elif r.motivo_fin == "detenida":
            msg = f"Detenido. Se publicaron {r.publicadas} en esta vuelta."
        else:
            msg = f"No hay grupos disponibles ahora. Se publicaron {r.publicadas}. Intenta más tarde."
        self.cola_ui.put(("fin", msg))


class App:
    def __init__(self, root: tk.Tk, datos: Path | None = None):
        self.root = root
        self.datos = Path(datos) if datos else carpeta_datos()
        self.ruta_config = self.datos / "config.json"
        self.ruta_cuentas = self.datos / "cuentas.json"
        self.cfg: Config = cargar_config(self.ruta_config)
        ajustar_espera(self.cfg)
        self.cuentas, self._ultima_cuenta = cargar_cuentas(self.ruta_cuentas)
        self.historial = Historial(self.datos / "historial.csv", self._principal())
        self._migrar()
        self.tira: Tira | None = None
        self.dia_nombre = ""
        self.tira_nombre = ""
        self.corriendo = False
        self.cerrando = False
        self.controles = Controles()
        self._responder_pendiente = None  # función para contestar el aviso abierto, si hay uno

        self.cola_ui: queue.Queue = queue.Queue()
        self.trabajador = Trabajador(self.datos, UITk(self.cola_ui), self.cola_ui)
        self.trabajador.start()

        self._construir()
        self._cargar_cuentas_en_combo()
        self._cargar_dias()
        self._actualizar_conteo_grupos()
        self._revisar_riesgo()
        self.root.protocol("WM_DELETE_WINDOW", self._al_cerrar)
        self.root.report_callback_exception = self._error_en_ventana
        self.root.after(100, self._procesar_cola)

    # --- construcción ----------------------------------------------------------------
    def _tarjeta(self, padre, titulo: str, ayuda: str = "") -> ttk.Frame:
        """Una tarjeta con título y una frase de ayuda. Devuelve el marco interior."""
        borde = tk.Frame(padre, background=estilo.BORDE, padx=1, pady=1)
        borde.pack(fill="x", padx=14, pady=(8, 0))
        caja = ttk.Frame(borde, style="Panel.TFrame", padding=(12, 8))
        caja.pack(fill="both", expand=True)
        ttk.Label(caja, text=titulo, style="Seccion.Panel.TLabel").pack(anchor="w")
        if ayuda:
            ttk.Label(caja, text=ayuda, style="Suave.Panel.TLabel", wraplength=680, justify="left").pack(
                anchor="w", pady=(0, 4))
        interior = ttk.Frame(caja, style="Panel.TFrame")
        interior.pack(fill="both", expand=True)
        return interior

    def _construir(self) -> None:
        r = self.root
        r.title(TITULO)
        r.minsize(740, 700)
        r.geometry("780x730")
        self.fuentes = estilo.aplicar_estilo(r)

        # Encabezado
        cab = tk.Frame(r, background=estilo.AZUL_OSCURO, padx=18, pady=10)
        cab.pack(fill="x")
        self.logo_cabecera = tk.PhotoImage(master=r, file=str(RECURSOS / "logo_44.png"))
        self.logo_ventana = tk.PhotoImage(master=r, file=str(RECURSOS / "logo_64.png"))
        r.iconphoto(True, self.logo_ventana)  # ícono en la barra de tareas
        tk.Label(cab, image=self.logo_cabecera, background=estilo.AZUL_OSCURO).pack(side="left", padx=(0, 10))
        tk.Label(cab, text="Publicador de Tiras", background=estilo.AZUL_OSCURO, foreground="white",
                 font=self.fuentes["titulo"]).pack(side="left")
        self.var_cabecera = tk.StringVar()
        tk.Label(cab, textvariable=self.var_cabecera, background=estilo.AZUL_OSCURO, foreground="#a5c8ff",
                 font=self.fuentes["base"]).pack(side="right")

        self.pestanas = ttk.Notebook(r)
        self.pestanas.pack(fill="both", expand=True, pady=(4, 0))
        pub = ttk.Frame(self.pestanas)
        cue = ttk.Frame(self.pestanas)
        aju = ttk.Frame(self.pestanas)
        self.pestanas.add(pub, text="📢 Publicar")
        self.pestanas.add(cue, text="👤 Cuentas y grupos")
        self.pestanas.add(aju, text="⚙️ Ajustes")
        self._construir_publicar(pub)
        self._construir_cuentas(cue)
        self._construir_ajustes(aju)

    def _construir_publicar(self, pub) -> None:
        # ① Cuenta
        c = self._tarjeta(pub, "①  ¿Con qué cuenta publico?")
        self.combo_cuenta = ttk.Combobox(c, state="readonly", width=40)
        self.combo_cuenta.pack(anchor="w")
        self.combo_cuenta.bind("<<ComboboxSelected>>", lambda e: self._cuenta_elegida())

        # ② Tira
        t = self._tarjeta(pub, "②  ¿Qué tira publico?")
        fila = ttk.Frame(t, style="Panel.TFrame")
        fila.pack(fill="x")
        ttk.Label(fila, text="Día", style="Panel.TLabel").pack(side="left")
        self.combo_dia = ttk.Combobox(fila, state="readonly", width=16)
        self.combo_dia.pack(side="left", padx=(6, 14))
        self.combo_dia.bind("<<ComboboxSelected>>", lambda e: self._dia_elegido())
        ttk.Label(fila, text="Tira", style="Panel.TLabel").pack(side="left")
        self.combo_tira = ttk.Combobox(fila, state="readonly", width=12)
        self.combo_tira.pack(side="left", padx=6)
        self.combo_tira.bind("<<ComboboxSelected>>", lambda e: self._tira_elegida())
        self.btn_escoger = ttk.Button(fila, text="📁 Escoger carpeta…", command=self._escoger_carpeta_tira)
        self.btn_escoger.pack(side="right")
        self.var_chip = tk.StringVar(value="Escoge una tira.")
        self.lbl_chip = tk.Label(t, textvariable=self.var_chip, anchor="w", padx=8, pady=4,
                                 font=self.fuentes["base"], background=estilo.PANEL_2, foreground=estilo.TEXTO_SUAVE)
        self.lbl_chip.pack(fill="x", pady=(8, 4))
        self.resumen = tk.Text(t, height=5, wrap="none", relief="flat", borderwidth=0, padx=8, pady=6,
                               background=estilo.FONDO, foreground=estilo.TEXTO, insertbackground=estilo.TEXTO,
                               font=self.fuentes["lista"], highlightthickness=0)
        self.resumen.pack(fill="both", expand=True)
        self.resumen.tag_configure("error", foreground="#ff7b72")
        self.resumen.tag_configure("titulo", foreground="#a5c8ff", font=self.fuentes["seccion"])
        self.resumen.tag_configure("suave", foreground=estilo.TEXTO_SUAVE)
        self.resumen.configure(state="disabled")

        # ③ Cómo publicar
        m = self._tarjeta(pub, "③  ¿Cómo publico?")
        fila = ttk.Frame(m, style="Panel.TFrame")
        fila.pack(fill="x")
        self.var_modo = tk.StringVar(value=self.cfg.modo)
        self.controles_ritmo: list = []
        for texto, valor in (("👀 Con revisión", "revision"), ("⚡ Automático", "automatico")):
            rb = ttk.Radiobutton(fila, text=texto, variable=self.var_modo, value=valor, command=self._cambio_ritmo,
                                 style="Panel.TRadiobutton")
            rb.pack(side="left", padx=(0, 16))
            self.controles_ritmo.append(rb)
        ttk.Label(fila, text="Esperar entre", style="Panel.TLabel").pack(side="left")
        self.var_espera_min = tk.IntVar(value=self.cfg.espera_min)
        self.var_espera_max = tk.IntVar(value=self.cfg.espera_max)
        for var, texto in ((self.var_espera_min, "y"), (self.var_espera_max, "minutos")):
            caja = ttk.Spinbox(fila, from_=2, to=240, width=4, textvariable=var, command=self._cambio_ritmo)
            caja.pack(side="left", padx=4)
            caja.bind("<FocusOut>", lambda e: self._cambio_ritmo())
            caja.bind("<KeyRelease>", lambda e: self._revisar_riesgo())
            self.controles_ritmo.append(caja)
            ttk.Label(fila, text=texto, style="Panel.TLabel").pack(side="left")
        self.var_aviso = tk.StringVar()
        self.lbl_aviso = tk.Label(m, textvariable=self.var_aviso, wraplength=680, justify="left", anchor="w",
                                  padx=8, pady=0, font=self.fuentes["base"], background=estilo.PANEL)
        self.lbl_aviso.pack(fill="x", pady=(8, 0))

        # ④ Empezar y progreso
        p = self._tarjeta(pub, "④  ¡A publicar!")
        fila = ttk.Frame(p, style="Panel.TFrame")
        fila.pack(fill="x", pady=(0, 6))
        self.btn_empezar = ttk.Button(fila, text="▶  EMPEZAR", style="Grande.Azul.TButton", command=self._empezar,
                                      state="disabled")
        self.btn_empezar.pack(side="left")
        self.btn_detener = ttk.Button(fila, text="⏹ Detener", style="Rojo.TButton", state="disabled",
                                      command=self._detener)
        self.btn_detener.pack(side="right")
        self.btn_saltar = ttk.Button(fila, text="⏭ Saltar grupo", state="disabled",
                                     command=lambda: self.controles.saltar.set())
        self.btn_saltar.pack(side="right", padx=6)
        self.var_progreso = tk.StringVar(value="Todavía no empieza.")
        ttk.Label(p, textvariable=self.var_progreso, style="Grande.Panel.TLabel", wraplength=680,
                  justify="left").pack(anchor="w")
        self.barra = ttk.Progressbar(p, style="Azul.Horizontal.TProgressbar", mode="determinate", maximum=12)
        self.barra.pack(fill="x", pady=6)
        self.var_estado = tk.StringVar(value="Escoge una tira para empezar.")
        ttk.Label(p, textvariable=self.var_estado, style="Suave.Panel.TLabel", wraplength=680,
                  justify="left").pack(anchor="w")

    def _construir_cuentas(self, cue) -> None:
        c = self._tarjeta(cue, "Cuentas de Facebook",
                          "El programa lee las cuentas del menú de tu foto en Facebook: el perfil de la empresa y "
                          "sus Páginas (una por sucursal). Hazlo una vez, o cuando agreguen otra Página.")
        self.lista_cuentas = tk.Listbox(c, height=5, activestyle="none", relief="flat", highlightthickness=0,
                                        background=estilo.FONDO, foreground=estilo.TEXTO,
                                        selectbackground=estilo.AZUL, font=self.fuentes["lista"])
        self.lista_cuentas.pack(fill="x", pady=(0, 8))
        self.btn_cuentas = ttk.Button(c, text="🔄 Actualizar cuentas", style="Azul.TButton",
                                      command=self._actualizar_cuentas)
        self.btn_cuentas.pack(anchor="w")

        g = self._tarjeta(cue, "Grupos de la cuenta escogida",
                          "Cada cuenta tiene sus propios grupos: una Página solo puede publicar en los grupos a "
                          "los que ella se unió. Si una cuenta no puede publicar en un grupo, se ignora solo para "
                          "esa cuenta.")
        self.var_cuenta_grupos = tk.StringVar()
        ttk.Label(g, textvariable=self.var_cuenta_grupos, style="Grande.Panel.TLabel").pack(anchor="w")
        self.var_grupos = tk.StringVar()
        ttk.Label(g, textvariable=self.var_grupos, style="Panel.TLabel").pack(anchor="w", pady=(2, 8))
        self.btn_grupos = ttk.Button(g, text="🔄 Actualizar grupos", style="Azul.TButton",
                                     command=self._actualizar_grupos)
        self.btn_grupos.pack(anchor="w")

    def _construir_ajustes(self, aju) -> None:
        c = self._tarjeta(aju, "Carpeta de las tiras", "La carpeta que tiene los días (1.lunes, 2 MARTES…).")
        fila = ttk.Frame(c, style="Panel.TFrame")
        fila.pack(fill="x")
        self.var_carpeta = tk.StringVar(value=self.cfg.carpeta_tiras or "(sin escoger)")
        ttk.Label(fila, textvariable=self.var_carpeta, style="Panel.TLabel").pack(side="left")
        self.btn_cambiar = ttk.Button(fila, text="📁 Cambiar", command=self._cambiar_carpeta)
        self.btn_cambiar.pack(side="right")

        g = self._tarjeta(aju, "Repetir grupos",
                          "Cuánto tiempo debe pasar antes de volver a publicar en el mismo grupo con la misma cuenta.")
        fila = ttk.Frame(g, style="Panel.TFrame")
        fila.pack(fill="x")
        self.var_minutos = tk.IntVar(value=self.cfg.minutos_entre_publicaciones)
        ttk.Spinbox(fila, from_=0, to=1440, increment=15, width=6, textvariable=self.var_minutos,
                    command=self._guardar_minutos).pack(side="left")
        ttk.Label(fila, text="minutos", style="Panel.TLabel").pack(side="left", padx=6)

        a = self._tarjeta(aju, "Archivos", "Historial de lo publicado, lista de grupos, capturas de errores.")
        fila = ttk.Frame(a, style="Panel.TFrame")
        fila.pack(fill="x")
        ttk.Button(fila, text="📂 Abrir carpeta de datos", command=self._abrir_datos).pack(side="left")
        ttk.Button(fila, text="📊 Abrir historial (Excel)", command=self._abrir_historial).pack(side="left", padx=8)

        h = self._tarjeta(aju, "Guía rápida")
        for linea in ("👀  Con revisión: el programa deja todo listo y tú das clic en «Publicar» en Facebook.",
                      "⚡  Automático: el programa publica solo y espera los minutos que pongas entre una y otra.",
                      "🟡  Cuidado: el riesgo de bloqueo va subiendo (ritmo rápido, muchas publicaciones, errores).",
                      "🔴  Peligro: riesgo alto de bloqueo. Conviene bajar el ritmo o parar.",
                      "⛔  Facebook bloqueó o pidió verificación: la tira se detiene; puedes seguir con otra cuenta.",
                      "💡  Consejo: prueba cada cuenta nueva primero «Con revisión» con 1 o 2 publicaciones."):
            ttk.Label(h, text=linea, style="Panel.TLabel", wraplength=680, justify="left").pack(anchor="w", pady=2)

    # --- cuentas -----------------------------------------------------------------------
    def _principal(self) -> str:
        c = principal(self.cuentas)
        return c.nombre if c else ""

    def _migrar(self) -> None:
        if self._principal():
            try:
                migrar_grupos(self.datos, self._principal())
            except OSError:
                pass

    @property
    def cuenta(self) -> str:
        return self.combo_cuenta.get() if hasattr(self, "combo_cuenta") else ""

    @property
    def ruta_grupos(self) -> Path:
        return ruta_grupos(self.datos, self.cuenta) if self.cuenta else self.datos / "grupos.txt"

    def _cargar_cuentas_en_combo(self) -> None:
        nombres = [c.nombre for c in self.cuentas]
        self.combo_cuenta["values"] = nombres
        self.lista_cuentas.delete(0, "end")
        for c in self.cuentas:
            self.lista_cuentas.insert("end", f"  {'👤 Perfil' if c.tipo == 'perfil' else '🏪 Página'}   {c.nombre}")
        if not self.cuentas:
            self.lista_cuentas.insert("end", "  (todavía no hay cuentas: da clic en «Actualizar cuentas»)")
        if self._ultima_cuenta in nombres:
            self.combo_cuenta.set(self._ultima_cuenta)
        elif nombres:
            self.combo_cuenta.set(self._principal())
        else:
            self.combo_cuenta.set("")

    def _cuenta_elegida(self, avisar: bool = True) -> None:
        self._ultima_cuenta = self.cuenta
        try:
            guardar_cuentas(self.ruta_cuentas, self.cuentas, self._ultima_cuenta)
        except OSError:
            pass
        self._actualizar_conteo_grupos()
        if self.tira is not None:
            self._mostrar_tira(self.tira)
        self._revisar_riesgo()
        if avisar and self.cuenta and self.historial.bloqueada_hoy(self.cuenta, date.today()):
            texto = f"🔴 «{self.cuenta}» tuvo un bloqueo hoy. Usarla de nuevo puede empeorarlo."
            self._mostrar_aviso("rojo", texto)
            messagebox.showwarning(TITULO, texto)

    def _actualizar_cuentas(self) -> None:
        self._marcar_corriendo(True, tira=False)
        self.var_estado.set("Abriendo el navegador…")
        self.trabajador.comandos.put(("cuentas",))

    def _cuentas_encontradas(self, lista: list[tuple[str, str]]) -> None:
        nombres = [n for n, _ in lista]
        anterior = self._principal()
        if anterior in nombres:
            elegido = anterior  # se respeta el principal que ya se conocía, aunque cambie el orden del menú
        elif len(nombres) == 1:
            elegido = nombres[0]
        else:
            elegido = self._elegir_opcion("¿Cuál es el perfil principal (con el que se publicaba antes)? "
                                          "Los grupos y el historial de antes quedan a su nombre.", nombres)
            if elegido not in nombres:
                elegido = nombres[0]
        self.cuentas = [Cuenta(n, "perfil" if n == elegido else "pagina") for n in nombres]
        try:
            self.historial.fijar_cuenta_vacia(elegido)
        except OSError:
            pass
        if self._ultima_cuenta not in [c.nombre for c in self.cuentas]:
            self._ultima_cuenta = self._principal()
        self.historial.cuenta_principal = self._principal()
        self._migrar()
        self._cargar_cuentas_en_combo()
        self._cuenta_elegida(avisar=False)

    # --- ritmo y avisos ----------------------------------------------------------------
    def _leer_entero(self, var: tk.IntVar, defecto: int) -> int:
        try:
            return int(var.get())
        except (tk.TclError, ValueError):
            return defecto

    def _cambio_ritmo(self) -> None:
        self.cfg.modo = self.var_modo.get()
        self.cfg.espera_min = self._leer_entero(self.var_espera_min, self.cfg.espera_min)
        self.cfg.espera_max = self._leer_entero(self.var_espera_max, self.cfg.espera_max)
        ajustar_espera(self.cfg)
        self.var_espera_min.set(self.cfg.espera_min)
        self.var_espera_max.set(self.cfg.espera_max)
        self._guardar()
        self._revisar_riesgo()

    def _revisar_riesgo(self) -> None:
        if self.var_modo.get() != "automatico":
            self._mostrar_aviso("", "")
            return
        minimo = self._leer_entero(self.var_espera_min, self.cfg.espera_min)
        if minimo <= 3:
            self._mostrar_aviso("rojo", "🔴 Ritmo muy rápido: riesgo alto de bloqueo de la cuenta.")
        elif minimo < 5:
            self._mostrar_aviso("amarillo", "🟡 Ritmo rápido: aumenta el riesgo de bloqueo.")
        else:
            self._mostrar_aviso("", "")

    def _mostrar_aviso(self, nivel: str, mensaje: str) -> None:
        fondo, texto = estilo.AVISOS.get(nivel if mensaje else "", estilo.AVISOS[""])
        self.var_aviso.set(mensaje)
        self.lbl_aviso.configure(background=fondo, foreground=texto, pady=6 if mensaje else 0)

    def _ritmo(self) -> Ritmo:
        return Ritmo(self.cfg.modo, self.cfg.espera_min, self.cfg.espera_max)

    # --- carpetas y tiras ------------------------------------------------------------
    def _guardar(self) -> None:
        guardar_config(self.ruta_config, self.cfg)

    def _guardar_minutos(self) -> None:
        try:
            self.cfg.minutos_entre_publicaciones = max(0, int(self.var_minutos.get()))
        except (tk.TclError, ValueError):
            return
        self._guardar()

    def _cambiar_carpeta(self) -> None:
        ruta = filedialog.askdirectory(title="Escoge la carpeta Tiras", initialdir=self.cfg.carpeta_tiras or None)
        if ruta:
            self.cfg.carpeta_tiras = ruta
            self.var_carpeta.set(ruta)
            self._guardar()
            self._cargar_dias()

    def _cargar_dias(self) -> None:
        dias = [p.name for p in listar_subcarpetas(Path(self.cfg.carpeta_tiras))] if self.cfg.carpeta_tiras else []
        self.combo_dia["values"] = dias
        if self.cfg.ultimo_dia in dias:
            self.combo_dia.set(self.cfg.ultimo_dia)
            self._dia_elegido(restaurar=True)
        else:
            self.combo_dia.set("")
            self.combo_tira["values"] = []
            self.combo_tira.set("")

    def _dia_elegido(self, restaurar: bool = False) -> None:
        carpeta = Path(self.cfg.carpeta_tiras) / self.combo_dia.get()
        tiras = [p.name for p in listar_subcarpetas(carpeta)]
        self.combo_tira["values"] = tiras
        if restaurar and self.cfg.ultima_tira in tiras:
            self.combo_tira.set(self.cfg.ultima_tira)
            self._tira_elegida()
        else:
            self.combo_tira.set("")
            self._mostrar_tira(None)

    def _tira_elegida(self) -> None:
        dia, tira = self.combo_dia.get(), self.combo_tira.get()
        self.cfg.ultimo_dia, self.cfg.ultima_tira = dia, tira
        self._guardar()
        self.cargar_tira(Path(self.cfg.carpeta_tiras) / dia / tira)

    def _escoger_carpeta_tira(self) -> None:
        ruta = filedialog.askdirectory(title="Escoge la carpeta de una tira (por ejemplo TIRA 1)")
        if ruta:
            self.cargar_tira(Path(ruta))

    def cargar_tira(self, carpeta: Path) -> None:
        self.dia_nombre = carpeta.parent.name
        self.tira_nombre = carpeta.name
        self._mostrar_tira(leer_tira(carpeta))

    def _mostrar_tira(self, tira: Tira | None) -> None:
        self.tira = tira
        t = self.resumen
        t.configure(state="normal")
        t.delete("1.0", "end")
        if tira is not None:
            t.insert("end", f"{self.tira_nombre} — {self.dia_nombre}\n", "titulo")
            for p in tira.publicaciones:
                t.insert("end", f"{p.numero:>2}. {p.titulo}  →  {p.imagen.name}\n")
            t.insert("end", f"Ubicación: {len(tira.ubicaciones)} archivos "
                            f"({', '.join(u.name for u in tira.ubicaciones)})\n")
            ya = self.historial.publicadas(self.dia_nombre, self.tira_nombre, date.today())
            if ya:
                t.insert("end", f"Hoy ya se publicaron {len(ya)} de {len(tira.publicaciones)}.\n")
            for e in tira.errores:
                t.insert("end", f"⚠️ {e}\n", "error")
            self.var_estado.set("Listo para empezar." if tira.ok else "Corrige los problemas marcados en rojo.")
            if tira.ok:
                faltan = len(tira.publicaciones) - len(ya)
                extra = f" (hoy ya van {len(ya)}, faltan {faltan})" if ya else ""
                self._chip("verde", f"✅  Lista para publicar: {len(tira.publicaciones)} anuncios{extra}")
            else:
                n = len(tira.errores)
                self._chip("rojo", f"❌  {n} problema{'s' if n > 1 else ''}: {tira.errores[0]}")
        else:
            self._chip("", "Escoge una tira.")
        t.configure(state="disabled")
        self._actualizar_botones()

    def _chip(self, nivel: str, texto: str) -> None:
        fondo, color = estilo.AVISOS.get(nivel, (estilo.PANEL_2, estilo.TEXTO_SUAVE))
        if not nivel:
            fondo, color = estilo.PANEL_2, estilo.TEXTO_SUAVE
        self.var_chip.set(texto)
        self.lbl_chip.configure(background=fondo, foreground=color)

    # --- grupos ----------------------------------------------------------------------
    def _actualizar_conteo_grupos(self) -> None:
        gs = cargar_grupos(self.ruta_grupos)
        activos = sum(g.activo for g in gs)
        self.var_grupos.set(f"✅ {activos} activos   ·   🚫 {len(gs) - activos} ignorados" if gs
                            else "(sin grupos todavía: da clic en «Actualizar grupos»)")
        self.var_cuenta_grupos.set(f"Cuenta: {self.cuenta}" if self.cuenta else "Cuenta: (sin escoger)")
        self.var_cabecera.set(f"Cuenta activa: {self.cuenta}" if self.cuenta else "")

    def _actualizar_grupos(self) -> None:
        self._marcar_corriendo(True, tira=False)
        self.var_estado.set("Abriendo el navegador…")
        self.trabajador.comandos.put(("grupos", self.cuenta, self.ruta_grupos))

    def _abrir_historial(self) -> None:
        ruta = self.datos / "historial.csv"
        if not ruta.exists():
            messagebox.showinfo(TITULO, "Todavía no hay historial: se crea con la primera publicación.")
            return
        self._abrir(ruta)

    def _abrir(self, ruta: Path) -> None:
        if sys.platform.startswith("win"):
            os.startfile(str(ruta))  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", str(ruta)])

    def _abrir_datos(self) -> None:
        ruta = str(self.datos)
        if sys.platform.startswith("win"):
            os.startfile(ruta)  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", ruta])

    # --- publicar --------------------------------------------------------------------
    def _empezar(self) -> None:
        if self.tira is None or not self.tira.ok or self.corriendo:
            return
        if not any(g.activo for g in cargar_grupos(self.ruta_grupos)):
            messagebox.showinfo(TITULO, "Primero da clic en «Actualizar grupos».")
            return
        ya = self.historial.publicadas(self.dia_nombre, self.tira_nombre, date.today())
        total = len(self.tira.publicaciones)
        if ya:
            if len(ya) >= total:
                messagebox.showinfo(TITULO, "Esta tira ya se publicó completa hoy.")
                return
            if not messagebox.askyesno("Continuar", f"Ya se publicaron {len(ya)} de {total}. "
                                                    "¿Seguir con las que faltan?"):
                return
        self._guardar_minutos()
        self._cambio_ritmo()
        if self.cfg.modo == "automatico":
            quien = f"«{self.cuenta}»" if self.cuenta else "la cuenta"
            if not messagebox.askyesno(
                    TITULO, f"Modo automático: el programa va a publicar SOLO con {quien}, esperando entre "
                            f"{self.cfg.espera_min} y {self.cfg.espera_max} minutos entre publicaciones.\n\n"
                            "⚠️ Publicar automáticamente en muchos grupos puede hacer que Facebook bloquee la "
                            "cuenta. El programa se detiene si ve señales de bloqueo.\n\n¿Empezar?"):
                return
        self.controles = Controles()
        self._marcar_corriendo(True, tira=True)
        self.var_estado.set("Abriendo el navegador…")
        self._enviar_tira(self.tira, self.dia_nombre, self.tira_nombre)

    def _enviar_tira(self, tira: Tira, dia: str, nombre: str) -> None:
        self.trabajador.comandos.put(("tira", tira, dia, nombre, self.controles,
                                      self.cfg.minutos_entre_publicaciones, self.cuenta, self._ritmo(),
                                      self.ruta_grupos, self._principal()))

    def _detener(self) -> None:
        self.controles.detener.set()
        self.var_estado.set("Deteniendo…")

    def _marcar_corriendo(self, corriendo: bool, tira: bool = False) -> None:
        self.corriendo = corriendo
        self.btn_saltar.configure(state="normal" if corriendo and tira else "disabled")
        self.btn_detener.configure(state="normal" if corriendo and tira else "disabled")
        for b in (self.btn_grupos, self.btn_cambiar, self.btn_escoger, self.btn_cuentas):
            b.configure(state="disabled" if corriendo else "normal")
        self.combo_cuenta.configure(state="disabled" if corriendo else "readonly")
        for w in self.controles_ritmo:
            w.configure(state="disabled" if corriendo else "normal")
        for w in (self.combo_dia, self.combo_tira):
            w.configure(state="disabled" if corriendo else "readonly")
        self._actualizar_botones()

    def _actualizar_botones(self) -> None:
        ok = self.tira is not None and self.tira.ok and not self.corriendo
        self.btn_empezar.configure(state="normal" if ok else "disabled")

    # --- cola de mensajes del hilo de trabajo ------------------------------------------
    def _error_en_ventana(self, exc_tipo, exc, tb) -> None:
        """Cualquier error en la ventana se anota y se avisa, pero la ventana sigue funcionando."""
        escribir_log(self.datos, "".join(traceback.format_exception(exc_tipo, exc, tb)))
        try:
            messagebox.showerror(TITULO, f"Ocurrió un problema: {exc}\n\nEl detalle quedó en errores.log.")
        except tk.TclError:
            pass

    def _procesar_cola(self) -> None:
        try:
            self._procesar_mensajes()
        except Exception:
            self._error_en_ventana(*sys.exc_info())
            if self.corriendo and not self.trabajador.is_alive():
                self._marcar_corriendo(False)
        finally:
            if not self.cerrando:
                self.root.after(100, self._procesar_cola)

    def _procesar_mensajes(self) -> None:
        try:
            while True:
                msg = self.cola_ui.get_nowait()
                tipo = msg[0]
                if tipo == "estado":
                    self.var_estado.set(msg[1])
                elif tipo == "progreso":
                    _, actual, total, titulo, grupo = msg
                    self.var_progreso.set(f"Publicación {actual} de {total}: {titulo}\n👥 {grupo}")
                    self.barra.configure(maximum=max(1, total), value=actual)
                elif tipo == "preguntar":
                    _, mensaje, opciones, respuesta = msg
                    self._dialogo(mensaje, opciones, respuesta)
                    if self.cerrando:
                        return
                elif tipo == "aviso":
                    _, nivel, mensaje = msg
                    self._mostrar_aviso(nivel, mensaje)
                    if nivel == "rojo" and not mensaje.startswith("⛔"):  # el bloqueo tiene su propia ventana
                        messagebox.showwarning(TITULO, mensaje)
                elif tipo == "cuentas":
                    self._cuentas_encontradas(msg[1])
                elif tipo == "bloqueada":
                    self._cuenta_bloqueada(*msg[1:])
                elif tipo == "fin":
                    self.var_estado.set(msg[1])
                    self.var_progreso.set("Todavía no empieza.")
                    self.barra.configure(value=0)
                    self._marcar_corriendo(False)
                    self._actualizar_conteo_grupos()
                    if self.tira is not None:
                        self._mostrar_tira(self.tira)
                        self.var_estado.set(msg[1])
        except queue.Empty:
            pass

    def _elegir_opcion(self, mensaje: str, opciones: list[str]) -> str:
        respuesta: queue.Queue = queue.Queue(maxsize=1)
        self._dialogo(mensaje, opciones, respuesta)
        return respuesta.get_nowait()

    def _cuenta_bloqueada(self, cuenta: str, mensaje: str, args: tuple) -> None:
        hoy = date.today()
        otras = [c.nombre for c in self.cuentas
                 if c.nombre != cuenta and not self.historial.bloqueada_hoy(c.nombre, hoy)]
        texto = (f"⛔ Facebook bloqueó o pidió verificación a «{cuenta}»:\n«{mensaje}»\n\n"
                 "La tira se detuvo. Lo que ya se publicó quedó guardado.")
        self._mostrar_aviso("rojo", texto.replace("\n\n", " ").replace("\n", " "))
        opciones = (["Seguir con otra cuenta"] if otras else []) + [DETENER]
        if self._elegir_opcion(texto, opciones) == "Seguir con otra cuenta":
            nueva = self._elegir_opcion("¿Con qué cuenta sigo la tira?", otras + ["Cancelar"])
            if nueva in otras and not any(g.activo for g in cargar_grupos(ruta_grupos(self.datos, nueva))):
                messagebox.showinfo(TITULO, f"«{nueva}» todavía no tiene grupos. Escógela, da clic en "
                                            "«Actualizar grupos» y vuelve a empezar la tira.")
                nueva = ""
            if nueva in otras:
                self.combo_cuenta.set(nueva)
                self._cuenta_elegida(avisar=False)
                self.controles = Controles()
                self.var_estado.set(f"Siguiendo la tira con «{nueva}»…")
                self._enviar_tira(*args)
                return
        self.var_estado.set(f"⛔ Se detuvo: «{cuenta}» tuvo un bloqueo.")
        self.var_progreso.set("Todavía no empieza.")
        self.barra.configure(value=0)
        self._marcar_corriendo(False)

    def _dialogo(self, mensaje: str, opciones: list[str], respuesta: queue.Queue) -> None:
        """Muestra un aviso con botones. Cerrar el aviso con la X equivale a la última opción."""
        win = tk.Toplevel(self.root)
        win.title(TITULO)
        win.configure(background=estilo.FONDO)
        win.transient(self.root)
        win.attributes("-topmost", True)
        # Abajo a la derecha, para no tapar el formulario de Facebook (por ejemplo, el de iniciar sesión).
        win.update_idletasks()
        x = max(0, win.winfo_screenwidth() - 520)
        y = max(0, win.winfo_screenheight() - 260)
        win.geometry(f"+{x}+{y}")
        contestado = []

        def responder(opcion: str) -> None:
            if contestado:
                return
            contestado.append(opcion)
            respuesta.put(opcion)
            self._responder_pendiente = None
            try:
                win.destroy()
            except tk.TclError:
                pass

        self._responder_pendiente = lambda: responder(DETENER if DETENER in opciones else opciones[-1])
        win.protocol("WM_DELETE_WINDOW", lambda: responder(opciones[-1]))
        ttk.Label(win, text=mensaje, wraplength=440, padding=18).pack()
        fila = ttk.Frame(win, padding=(18, 0, 18, 18))
        fila.pack()
        for i, op in enumerate(opciones):
            estilo_boton = "Rojo.TButton" if op == DETENER else ("Azul.TButton" if i == 0 else "TButton")
            ttk.Button(fila, text=op, style=estilo_boton, command=lambda o=op: responder(o)).pack(side="left", padx=4)
        win.grab_set()
        self.root.wait_window(win)
        responder(opciones[-1])  # por si la ventana se destruyó de otra forma

    def _al_cerrar(self) -> None:
        if self.corriendo and not messagebox.askyesno(TITULO, "Hay una tira en curso. ¿Cerrar de todos modos?"):
            return
        self.cerrando = True
        self.controles.detener.set()
        if self._responder_pendiente is not None:
            self._responder_pendiente()
        self.trabajador.comandos.put(("salir",))
        self.trabajador.join(timeout=10)
        self.root.destroy()


def crear_ventana(datos: Path | None = None) -> tk.Tk:
    root = tk.Tk()
    root.app = App(root, datos)  # type: ignore[attr-defined]
    return root


def main() -> None:
    if sys.platform.startswith("win"):
        try:  # texto nítido en pantallas con escala (125 %, 150 %…)
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass
    candado = bloquear_instancia(carpeta_datos())
    if candado is None:
        r = tk.Tk()
        r.withdraw()
        messagebox.showinfo(TITULO, "El programa ya está abierto en otra ventana.")
        r.destroy()
        return
    try:
        crear_ventana().mainloop()
    finally:
        candado.close()
