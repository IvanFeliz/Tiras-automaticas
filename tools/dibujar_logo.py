"""Dibuja el logo: gato con media cara de máscara de hacker sobre código verde (original, hecho a mano)."""
import random
import sys

from PIL import Image, ImageDraw, ImageFilter, ImageFont

S = 1024  # se dibuja grande y luego se reduce (bordes suaves)
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))

# --- Fondo: círculo negro con lluvia de código verde ---------------------------------
fondo = Image.new("RGBA", (S, S), (6, 10, 8, 255))
d = ImageDraw.Draw(fondo)
rng = random.Random(7)
try:
    fuente = ImageFont.truetype("DejaVuSansMono-Bold.ttf", 34)
except OSError:
    fuente = ImageFont.load_default()
for x in range(14, S, 40):
    largo = rng.randint(8, 26)
    inicio = rng.randint(-10, 20)
    for k in range(largo):
        y = (inicio + k) * 38
        brillo = int(60 + 170 * (k / largo))
        d.text((x, y), rng.choice("01"), fill=(30, brillo, 60, 255), font=fuente)
fondo = fondo.filter(ImageFilter.GaussianBlur(0.6))
mascara_circulo = Image.new("L", (S, S), 0)
ImageDraw.Draw(mascara_circulo).ellipse((8, 8, S - 8, S - 8), fill=255)
img.paste(fondo, (0, 0), mascara_circulo)
ImageDraw.Draw(img).ellipse((8, 8, S - 8, S - 8), outline=(47, 129, 247, 255), width=22)  # aro azul

# --- Cabeza del gato --------------------------------------------------------------
cx, cy = S // 2, 575
cara = Image.new("RGBA", (S, S), (0, 0, 0, 0))
dc = ImageDraw.Draw(cara)
GRIS, GRIS_OSC, ROSA = (150, 146, 140, 255), (88, 84, 80, 255), (232, 150, 150, 255)
BLANCO, NEGRO = (240, 240, 236, 255), (20, 20, 20, 255)
# orejas
dc.polygon([(255, 470), (300, 190), (450, 360)], fill=GRIS)
dc.polygon([(290, 430), (315, 255), (410, 365)], fill=ROSA)
dc.polygon([(769, 470), (724, 190), (574, 360)], fill=GRIS)
# cara
dc.ellipse((cx - 300, cy - 250, cx + 300, cy + 270), fill=GRIS)
# rayas de gato (lado izquierdo)
for i, (x0, y0, x1, y1) in enumerate([(430, 345, 470, 440), (380, 365, 420, 450), (480, 340, 505, 430)]):
    dc.line((x0, y0, x1, y1), fill=GRIS_OSC, width=18)
dc.line((240, 600, 330, 590), fill=GRIS_OSC, width=14)
dc.line((235, 650, 330, 640), fill=GRIS_OSC, width=14)

# --- Lado derecho: máscara de hacker ------------------------------------------------
mitad = Image.new("L", (S, S), 0)
ImageDraw.Draw(mitad).rectangle((cx, 0, S, S), fill=255)
mask_layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
dm = ImageDraw.Draw(mask_layer)
dm.ellipse((cx - 300, cy - 255, cx + 300, cy + 275), fill=BLANCO)
dm.polygon([(769, 470), (724, 190), (574, 360)], fill=BLANCO)  # la máscara cubre también la oreja
dm.polygon([(734, 430), (709, 255), (614, 365)], fill=(215, 215, 210, 255))
cara.paste(mask_layer, (0, 0), mitad)
dc = ImageDraw.Draw(cara)

# ojo de gato (izquierdo): verde con pupila
dc.ellipse((350, 470, 470, 570), fill=(170, 200, 60, 255))
dc.ellipse((395, 475, 425, 565), fill=NEGRO)
dc.ellipse((405, 490, 418, 505), fill=(255, 255, 255, 255))
# ojo de la máscara (derecho): rendija con ceja marcada
dc.polygon([(555, 505), (690, 490), (660, 535), (575, 538)], fill=NEGRO)
dc.line((545, 450, 700, 425), fill=NEGRO, width=26)
# mejilla rosada de la máscara
dc.ellipse((640, 600, 720, 655), fill=(230, 120, 130, 200))
# nariz (mitad rosa / mitad máscara)
dc.polygon([(cx - 45, 600), (cx, 600), (cx, 650)], fill=ROSA)
dc.polygon([(cx, 600), (cx + 45, 600), (cx, 650)], fill=(205, 205, 200, 255))
# boca: lado gato
dc.arc((cx - 80, 630, cx, 700), 20, 160, fill=NEGRO, width=10)
# lado máscara: bigote enroscado, sonrisa y piocha
dc.chord((cx, 665, cx + 190, 735), 180, 360, fill=NEGRO)
dc.ellipse((cx + 165, 655, cx + 205, 695), fill=NEGRO)
dc.arc((cx - 10, 700, cx + 170, 790), 10, 120, fill=NEGRO, width=12)
dc.polygon([(cx, 800), (cx + 30, 800), (cx + 8, 880)], fill=NEGRO)
# línea que divide las dos mitades
dc.line((cx, cy - 250, cx, cy + 270), fill=(60, 60, 60, 120), width=4)

img.alpha_composite(cara)
img = img.resize((512, 512), Image.LANCZOS)
img.save(sys.argv[1])
print("ok")
