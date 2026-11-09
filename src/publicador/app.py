"""Ventana principal (Tkinter) y el hilo de trabajo que controla el navegador."""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import traceback
import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .config import Config, cargar_config, carpeta_datos, guardar_config
from .grupos import actualizar_grupos, cargar_grupos
from .historial import Historial
from .sesion import Controles, ErrorFacebook, NavegadorCerrado, ejecutar_tira
from .tira import Tira, leer_tira, listar_subcarpetas

TITULO = "Publicador de Tiras"


class UITk:
    """Implementa UIProto pasando mensajes a la ventana por una cola (seguro entre hilos)."""

    def __init__(self, cola: queue.Queue):
        self.cola = cola

    def estado(self, mensaje: str) -> None:
        self.cola.put(("estado", mensaje))

    def progreso(self, actual: int, total: int, titulo: str, grupo: str) -> None:
        self.cola.put(("progreso", actual, total, titulo, grupo))

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
                if cmd[0] == "grupos":
                    self._grupos()
                elif cmd[0] == "tira":
                    self._tira(*cmd[1:])
            except NavegadorCerrado:
                self._olvidar_navegador()
                self.cola_ui.put(("fin", "⚠️ Se cerró el navegador. Da clic otra vez para continuar "
                                         "(se abrirá uno nuevo)."))
            except ErrorFacebook as e:
                self.cola_ui.put(("fin", f"⚠️ {e}"))
            except Exception as e:
                with (self.datos / "errores.log").open("a", encoding="utf-8") as f:
                    f.write(traceback.format_exc() + "\n")
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
            self.ui.preguntar("Inicia sesión en Facebook en el navegador que se abrió y luego da clic en Continuar",
                              ["Continuar"])
            fb.pagina.goto("https://www.facebook.com/")

    def _grupos(self) -> None:
        fb = self._navegador()
        self.ui.estado("Abriendo Facebook…")
        fb.pagina.goto("https://www.facebook.com/")
        self._asegurar_sesion(fb)
        encontrados = fb.extraer_grupos(self.ui.estado)
        if not encontrados:
            self.cola_ui.put(("fin", "⚠️ No se encontró ningún grupo. ¿Iniciaste sesión con la cuenta correcta?"))
            return
        nuevos = actualizar_grupos(self.datos / "grupos.txt", encontrados)
        self.cola_ui.put(("fin", f"✅ {len(encontrados)} grupos encontrados ({nuevos} nuevos)."))

    def _tira(self, tira: Tira, dia: str, nombre: str, controles: Controles, minutos: int) -> None:
        fb = self._navegador()
        r = ejecutar_tira(tira, dia, nombre, fb, self.ui, controles, self.datos / "grupos.txt",
                          Historial(self.datos / "historial.csv"), minutos)
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
        self.ruta_grupos = self.datos / "grupos.txt"
        self.historial = Historial(self.datos / "historial.csv")
        self.cfg: Config = cargar_config(self.ruta_config)
        self.tira: Tira | None = None
        self.dia_nombre = ""
        self.tira_nombre = ""
        self.corriendo = False
        self.controles = Controles()

        self.cola_ui: queue.Queue = queue.Queue()
        self.trabajador = Trabajador(self.datos, UITk(self.cola_ui), self.cola_ui)
        self.trabajador.start()

        self._construir()
        self._cargar_dias()
        self._actualizar_conteo_grupos()
        self.root.protocol("WM_DELETE_WINDOW", self._al_cerrar)
        self.root.after(100, self._procesar_cola)

    # --- construcción ----------------------------------------------------------------
    def _construir(self) -> None:
        r = self.root
        r.title(TITULO)
        r.minsize(560, 560)
        marco = ttk.Frame(r, padding=12)
        marco.pack(fill="both", expand=True)
        marco.columnconfigure(1, weight=1)

        ttk.Label(marco, text="Carpeta:").grid(row=0, column=0, sticky="w")
        self.var_carpeta = tk.StringVar(value=self.cfg.carpeta_tiras or "(sin escoger)")
        ttk.Label(marco, textvariable=self.var_carpeta, foreground="#444").grid(row=0, column=1, sticky="w", padx=6)
        ttk.Button(marco, text="Cambiar", command=self._cambiar_carpeta).grid(row=0, column=2, sticky="e")

        fila = ttk.Frame(marco)
        fila.grid(row=1, column=0, columnspan=3, sticky="we", pady=(8, 0))
        ttk.Label(fila, text="Día:").pack(side="left")
        self.combo_dia = ttk.Combobox(fila, state="readonly", width=16)
        self.combo_dia.pack(side="left", padx=(4, 12))
        self.combo_dia.bind("<<ComboboxSelected>>", lambda e: self._dia_elegido())
        ttk.Label(fila, text="Tira:").pack(side="left")
        self.combo_tira = ttk.Combobox(fila, state="readonly", width=12)
        self.combo_tira.pack(side="left", padx=4)
        self.combo_tira.bind("<<ComboboxSelected>>", lambda e: self._tira_elegida())
        ttk.Button(fila, text="Escoger carpeta…", command=self._escoger_carpeta_tira).pack(side="right")

        self.resumen = tk.Text(marco, height=15, wrap="none", relief="solid", borderwidth=1)
        self.resumen.grid(row=2, column=0, columnspan=3, sticky="nsew", pady=8)
        self.resumen.tag_configure("error", foreground="#b00020")
        self.resumen.tag_configure("titulo", font=("TkDefaultFont", 10, "bold"))
        self.resumen.configure(state="disabled")
        marco.rowconfigure(2, weight=1)

        fila = ttk.Frame(marco)
        fila.grid(row=3, column=0, columnspan=3, sticky="we")
        self.btn_grupos = ttk.Button(fila, text="Actualizar grupos", command=self._actualizar_grupos)
        self.btn_grupos.pack(side="left")
        self.var_grupos = tk.StringVar()
        ttk.Label(fila, textvariable=self.var_grupos).pack(side="left", padx=8)
        ttk.Button(fila, text="Abrir carpeta de datos", command=self._abrir_datos).pack(side="right")

        fila = ttk.Frame(marco)
        fila.grid(row=4, column=0, columnspan=3, sticky="we", pady=(6, 0))
        ttk.Label(fila, text="Minutos antes de repetir un grupo:").pack(side="left")
        self.var_minutos = tk.IntVar(value=self.cfg.minutos_entre_publicaciones)
        ttk.Spinbox(fila, from_=0, to=1440, increment=15, width=6, textvariable=self.var_minutos,
                    command=self._guardar_minutos).pack(side="left", padx=4)

        self.btn_empezar = ttk.Button(marco, text="▶  Empezar", command=self._empezar, state="disabled")
        self.btn_empezar.grid(row=5, column=0, columnspan=3, pady=10, ipadx=20, ipady=4)

        self.var_progreso = tk.StringVar()
        ttk.Label(marco, textvariable=self.var_progreso, font=("TkDefaultFont", 10, "bold")).grid(
            row=6, column=0, columnspan=3, sticky="w")
        self.var_estado = tk.StringVar(value="Escoge una tira para empezar.")
        ttk.Label(marco, textvariable=self.var_estado, wraplength=520).grid(row=7, column=0, columnspan=3, sticky="w")

        fila = ttk.Frame(marco)
        fila.grid(row=8, column=0, columnspan=3, pady=(8, 0))
        self.btn_saltar = ttk.Button(fila, text="Saltar este grupo", state="disabled",
                                     command=lambda: self.controles.saltar.set())
        self.btn_saltar.pack(side="left", padx=6)
        self.btn_detener = ttk.Button(fila, text="Detener", state="disabled", command=self._detener)
        self.btn_detener.pack(side="left", padx=6)

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
        t.configure(state="disabled")
        self._actualizar_botones()

    # --- grupos ----------------------------------------------------------------------
    def _actualizar_conteo_grupos(self) -> None:
        gs = cargar_grupos(self.ruta_grupos)
        activos = sum(g.activo for g in gs)
        self.var_grupos.set(f"({len(gs)} grupos guardados, {activos} activos)" if gs else "(sin grupos todavía)")

    def _actualizar_grupos(self) -> None:
        self._marcar_corriendo(True, tira=False)
        self.var_estado.set("Abriendo el navegador…")
        self.trabajador.comandos.put(("grupos",))

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
        self.controles = Controles()
        self._marcar_corriendo(True, tira=True)
        self.var_estado.set("Abriendo el navegador…")
        self.trabajador.comandos.put(("tira", self.tira, self.dia_nombre, self.tira_nombre, self.controles,
                                      self.cfg.minutos_entre_publicaciones))

    def _detener(self) -> None:
        self.controles.detener.set()
        self.var_estado.set("Deteniendo…")

    def _marcar_corriendo(self, corriendo: bool, tira: bool = False) -> None:
        self.corriendo = corriendo
        self.btn_saltar.configure(state="normal" if corriendo and tira else "disabled")
        self.btn_detener.configure(state="normal" if corriendo and tira else "disabled")
        self.btn_grupos.configure(state="disabled" if corriendo else "normal")
        for w in (self.combo_dia, self.combo_tira):
            w.configure(state="disabled" if corriendo else "readonly")
        self._actualizar_botones()

    def _actualizar_botones(self) -> None:
        ok = self.tira is not None and self.tira.ok and not self.corriendo
        self.btn_empezar.configure(state="normal" if ok else "disabled")

    # --- cola de mensajes del hilo de trabajo ------------------------------------------
    def _procesar_cola(self) -> None:
        try:
            while True:
                msg = self.cola_ui.get_nowait()
                tipo = msg[0]
                if tipo == "estado":
                    self.var_estado.set(msg[1])
                elif tipo == "progreso":
                    _, actual, total, titulo, grupo = msg
                    self.var_progreso.set(f"Publicación {actual} de {total} — «{titulo}»\nGrupo: {grupo}")
                elif tipo == "preguntar":
                    _, mensaje, opciones, respuesta = msg
                    respuesta.put(self._dialogo(mensaje, opciones))
                elif tipo == "fin":
                    self.var_estado.set(msg[1])
                    self.var_progreso.set("")
                    self._marcar_corriendo(False)
                    self._actualizar_conteo_grupos()
                    if self.tira is not None:
                        self._mostrar_tira(self.tira)
                        self.var_estado.set(msg[1])
        except queue.Empty:
            pass
        self.root.after(100, self._procesar_cola)

    def _dialogo(self, mensaje: str, opciones: list[str]) -> str:
        win = tk.Toplevel(self.root)
        win.title(TITULO)
        win.transient(self.root)
        win.attributes("-topmost", True)
        eleccion = tk.StringVar(value=opciones[-1])
        ttk.Label(win, text=mensaje, wraplength=420, padding=16).pack()
        fila = ttk.Frame(win, padding=(16, 0, 16, 16))
        fila.pack()
        for op in opciones:
            ttk.Button(fila, text=op, command=lambda o=op: (eleccion.set(o), win.destroy())).pack(side="left", padx=4)
        win.grab_set()
        self.root.wait_window(win)
        return eleccion.get()

    def _al_cerrar(self) -> None:
        if self.corriendo and not messagebox.askyesno(TITULO, "Hay una tira en curso. ¿Cerrar de todos modos?"):
            return
        self.controles.detener.set()
        self.trabajador.comandos.put(("salir",))
        self.trabajador.join(timeout=5)
        self.root.destroy()


def crear_ventana(datos: Path | None = None) -> tk.Tk:
    root = tk.Tk()
    root.app = App(root, datos)  # type: ignore[attr-defined]
    return root


def main() -> None:
    crear_ventana().mainloop()
