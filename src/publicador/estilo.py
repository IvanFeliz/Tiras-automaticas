"""Colores, tipos de letra y estilos de la ventana (tema oscuro azul y negro)."""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

FONDO = "#0d1117"        # fondo general
PANEL = "#161b22"        # tarjetas
PANEL_2 = "#21262d"      # campos y botones normales
BORDE = "#30363d"
TEXTO = "#e6edf3"
TEXTO_SUAVE = "#8b949e"
AZUL = "#2f81f7"
AZUL_HOVER = "#4493f8"
AZUL_OSCURO = "#0b2a5b"  # encabezado
ROJO = "#da3633"
ROJO_HOVER = "#f85149"
VERDE = "#3fb950"

AVISOS = {  # fondo, texto
    "amarillo": ("#3b2e05", "#f2cc60"),
    "rojo": ("#3d1214", "#ff7b72"),
    "verde": ("#0f2d1a", "#56d364"),
    "": (PANEL, TEXTO),
}


def _familia(root: tk.Misc) -> str:
    disponibles = set(tkfont.families(root))
    for f in ("Segoe UI", "Helvetica Neue", "Ubuntu", "DejaVu Sans"):
        if f in disponibles:
            return f
    return "TkDefaultFont"


def aplicar_estilo(root: tk.Tk) -> dict[str, tuple]:
    """Configura el tema oscuro y devuelve los tipos de letra a usar."""
    fam = _familia(root)
    fuentes = {
        "base": (fam, 10),
        "suave": (fam, 9),
        "seccion": (fam, 12, "bold"),
        "titulo": (fam, 17, "bold"),
        "grande": (fam, 13, "bold"),
        "lista": (fam, 10),
    }
    root.configure(background=FONDO)
    root.option_add("*Font", fuentes["base"])
    # Lista desplegable de los combos (no la controla ttk)
    root.option_add("*TCombobox*Listbox.background", PANEL_2)
    root.option_add("*TCombobox*Listbox.foreground", TEXTO)
    root.option_add("*TCombobox*Listbox.selectBackground", AZUL)
    root.option_add("*TCombobox*Listbox.selectForeground", "white")
    root.option_add("*TCombobox*Listbox.font", fuentes["base"])

    s = ttk.Style(root)
    s.theme_use("clam")
    s.configure(".", background=FONDO, foreground=TEXTO, font=fuentes["base"], bordercolor=BORDE,
                lightcolor=BORDE, darkcolor=BORDE, troughcolor=PANEL_2, focuscolor=AZUL)
    s.configure("TFrame", background=FONDO)
    s.configure("Panel.TFrame", background=PANEL)
    s.configure("TLabel", background=FONDO, foreground=TEXTO)
    s.configure("Panel.TLabel", background=PANEL, foreground=TEXTO)
    s.configure("Suave.Panel.TLabel", background=PANEL, foreground=TEXTO_SUAVE, font=fuentes["suave"])
    s.configure("Seccion.Panel.TLabel", background=PANEL, foreground=TEXTO, font=fuentes["seccion"])
    s.configure("Grande.Panel.TLabel", background=PANEL, foreground=TEXTO, font=fuentes["grande"])

    s.configure("TButton", background=PANEL_2, foreground=TEXTO, borderwidth=1, padding=(12, 6),
                relief="flat")
    s.map("TButton", background=[("disabled", PANEL), ("active", BORDE)],
          foreground=[("disabled", TEXTO_SUAVE)])
    for nombre, color, hover in (("Azul", AZUL, AZUL_HOVER), ("Rojo", ROJO, ROJO_HOVER)):
        s.configure(f"{nombre}.TButton", background=color, foreground="white", bordercolor=color,
                    font=(fam, 10, "bold"))
        s.map(f"{nombre}.TButton", background=[("disabled", PANEL_2), ("active", hover)],
              foreground=[("disabled", TEXTO_SUAVE)], bordercolor=[("disabled", BORDE)])
    s.configure("Grande.Azul.TButton", font=(fam, 13, "bold"), padding=(26, 8))

    for clase in ("TCombobox", "TSpinbox"):
        s.configure(clase, fieldbackground=PANEL_2, background=PANEL_2, foreground=TEXTO, arrowcolor=TEXTO,
                    insertcolor=TEXTO, padding=4)
        s.map(clase, fieldbackground=[("readonly", PANEL_2), ("disabled", PANEL)],
              foreground=[("disabled", TEXTO_SUAVE)], selectbackground=[("readonly", PANEL_2)],
              selectforeground=[("readonly", TEXTO)])

    s.configure("Panel.TRadiobutton", background=PANEL, foreground=TEXTO, indicatorcolor=PANEL_2,
                indicatorbackground=PANEL_2)
    s.map("Panel.TRadiobutton", background=[("active", PANEL)], indicatorcolor=[("selected", AZUL)],
          foreground=[("disabled", TEXTO_SUAVE)])

    s.configure("TNotebook", background=FONDO, borderwidth=0, tabmargins=(12, 8, 12, 0))
    s.configure("TNotebook.Tab", background=PANEL, foreground=TEXTO_SUAVE, padding=(18, 8),
                font=(fam, 11, "bold"), borderwidth=0)
    s.map("TNotebook.Tab", background=[("selected", AZUL)], foreground=[("selected", "white")])

    s.configure("Azul.Horizontal.TProgressbar", background=AZUL, troughcolor=PANEL_2, bordercolor=PANEL_2,
                lightcolor=AZUL, darkcolor=AZUL, thickness=14)
    return fuentes
