# Publicador de Tiras — Especificación de diseño

Fecha: 2026-11-09

## 1. Objetivo

El negocio publica "tiras" de publicidad en grupos de Facebook. Una tira son 12 publicaciones
(texto + imagen + archivo de ubicación), y cada una va en un grupo diferente. Hoy se suben a mano,
una por una. El programa debe hacer casi todo el trabajo: leer la carpeta de la tira, abrir cada
grupo, pegar el texto y subir los archivos. Una persona solo revisa y da clic en "Publicar".

**Éxito =** publicar una tira completa de 12 publicaciones en pocos minutos, con solo un clic por
publicación, sin repetir grupos de forma abusiva y sin que Facebook bloquee la cuenta.

### Fuera de alcance
- Publicación 100 % automática (sin clic humano). Se descartó por el riesgo de bloqueo de la cuenta.
- Publicar como Página de Facebook o usar la API de Facebook (la API de grupos ya no existe desde 2024).
- Editar o crear el contenido de las tiras.

## 2. Contexto y restricciones

- Se publica desde **un perfil de Facebook de la empresa** que ya es miembro de los grupos.
- Se usa en **Windows** (el desarrollo se hizo viendo carpetas en Linux Mint). El usuario final
  necesita algo de **doble clic**: un `.exe`, sin instalar Python.
- Hay muchos grupos (no se sabe cuántos). No existe una lista; hoy se buscan en "Tus grupos".
- El contenido cambia cada cierto tiempo, pero **el formato de carpetas y archivos siempre es el mismo**
  (sección 3). El programa lee la carpeta cada vez y nunca guarda el contenido.
- Volumen posible: 7 días × 10 tiras × 12 = hasta 120 publicaciones al día.

## 3. Formato de entrada (fijo)

```
Tiras/
  1.lunes/ … 7. DOMINGO/              ← carpetas de día (nombre libre, ordenadas por número inicial)
    TIRA 1/ … TIRA 10/                ← carpetas de tira (ordenadas por número)
      0 TEXTOS TIRA.txt               ← los 12 textos
      1 PANTALLA.png … 12 TECLADO.png ← imagen del anuncio, empieza con el número del texto
      000.ALTAMIRANO.jpeg             ← foto del local      ┐
      0.CROQUIS ALTAMIRANO.jpg        ← croquis             ├ archivos de ubicación
      0.UBICACION ALTAMIRANO.mp4      ← video de ubicación  ┘
```

### Reglas de lectura
- **Archivo de textos:** el único `.txt` de la carpeta, leído en UTF-8 (con respaldo a UTF-8 con BOM
  y cp1252 si falla).
- Se ignora el encabezado (`TIRA #`) y todo lo anterior al primer bloque numerado.
- Los bloques están separados por líneas formadas solo por guiones (3 o más `-`).
- Cada bloque empieza con una línea `N. Título` (por ejemplo `1. Cambio de Pantalla`). `N` es el número
  de publicación y el título solo se usa para mostrarlo en la ventana; **no se publica**.
- El **texto a publicar** es todo lo que sigue a la línea del título, sin líneas en blanco al inicio ni
  al final y sin espacios sobrantes al inicio de cada línea. Los saltos de línea y emojis se conservan.
- **Imagen del anuncio:** archivo de imagen (`.png`, `.jpg`, `.jpeg`, `.webp`) cuyo nombre empieza con
  `N` seguido de un carácter que no sea dígito (`1 PANTALLA.png`, `3 CENTRO DE CARGA 2.png`). Las que
  empiezan con `0` no son anuncios.
- **Archivos de ubicación:** los archivos de imagen o video (`.mp4`, `.mov`) cuyo nombre empieza con `0`.
- **Validación**, antes de publicar: cada texto tiene exactamente una imagen, no hay imágenes sin texto,
  no hay números repetidos y hay al menos 1 archivo de ubicación. Si algo falla, se muestra el problema
  y no se puede empezar.
- El número de publicaciones normalmente es 12, pero el programa acepta el número que encuentre.

## 4. Arquitectura

Python 3.12 + Playwright (maneja Chromium) + Tkinter (ventana), empaquetado con PyInstaller como `.exe`.

| Módulo | Responsabilidad | Depende de |
|---|---|---|
| `tira.py` (Lector de tiras) | Recibe la ruta de una carpeta de tira y devuelve la lista de publicaciones (número, título, texto, imagen) y los archivos de ubicación, o una lista de errores de validación | nada |
| `grupos.py` (Lista de grupos) | Lee y escribe `grupos.txt`; agrega grupos nuevos sin perder los marcados con `#`; marca un grupo como ignorado | nada |
| `historial.py` | Agrega registros a `historial.csv` y responde: ¿cuándo se publicó por última vez en el grupo X?, ¿qué publicaciones de la tira Y ya se hicieron hoy? | nada |
| `rotacion.py` | Elige el grupo para la siguiente publicación con la regla de la sección 6 | `grupos`, `historial` |
| `facebook.py` (Publicador) | Controla el navegador: iniciar sesión, extraer "Tus grupos", abrir el compositor de un grupo, pegar el texto, adjuntar archivos y detectar que se publicó | Playwright |
| `app.py` (Ventana) | Interfaz Tkinter y la secuencia de la sección 7. El navegador corre en un hilo aparte para que la ventana no se congele | todos |
| `config.py` | Lee y guarda `config.json` | nada |

Solo `facebook.py` sabe de Facebook. Todo lo que depende de cómo está hecha la página (selectores,
textos de botones) vive ahí, para que los ajustes por cambios de Facebook toquen un solo archivo.

### Archivos de datos
Se guardan en `%APPDATA%\PublicadorTiras\` (en Windows) y la ventana tiene un botón para abrir la carpeta:
- `config.json`: carpeta de Tiras, minutos mínimos entre publicaciones en el mismo grupo (por defecto
  `60`) y el último día y tira usados.
- `grupos.txt`: una línea por grupo, `nombre | link`. Las líneas que empiezan con `#` se ignoran.
- `historial.csv`: `fecha_hora, dia, tira, numero, titulo, grupo, link_grupo, archivo_ubicacion, resultado`,
  donde `resultado` es `publicado`, `saltado` o `error`. Se guarda en UTF-8 con BOM para que Excel
  muestre bien los acentos.
- `navegador/`: perfil de Chromium donde queda guardada la sesión de Facebook.
- `capturas/`: capturas de pantalla de los errores.

## 5. La ventana

```
┌─ Publicador de Tiras ──────────────────────────┐
│ Carpeta: C:\...\Documentos\Tiras   [Cambiar]   │
│ Día:  [2 MARTES   ▼]     Tira: [TIRA 3 ▼]      │
│ o  [Escoger carpeta…]                          │
│                                                │
│ [Actualizar grupos]  (142 grupos guardados)    │
│ [Abrir carpeta de datos]                       │
│                                                │
│            [ ▶ Empezar ]                       │
│                                                │
│ Publicación 4 de 12 — "Mantenimiento Celular"  │
│ Grupo: Compra Venta Iguala                     │
│ Esperando a que des clic en Publicar...        │
│            [Saltar este grupo]   [Detener]     │
└────────────────────────────────────────────────┘
```

- Las listas de Día y Tira se llenan con las subcarpetas de la carpeta de Tiras, ordenadas por su
  número inicial.
- **Escoger carpeta…** permite elegir cualquier carpeta de tira directo (USB, escritorio, etc.).
- Al escoger una tira se muestra el **resumen**: cada número y título con su imagen, la cantidad de
  archivos de ubicación y los errores de validación, si hay. **Empezar** solo se activa si no hay errores.

## 6. Rotación de grupos

Para cada publicación:
1. Candidatos = grupos de `grupos.txt` sin `#`.
2. Se quitan los grupos que tuvieron una publicación (`publicado`) hace menos de `minutos_entre_publicaciones`
   (por defecto 60), y también los ya usados en esta misma tira.
3. De los que quedan, se elige el que **lleva más tiempo sin publicación**. Los que nunca han recibido una
   van primero. Si hay empate, se elige al azar.
4. Si no queda ninguno, se avisa *"No hay grupos disponibles ahora"* y se detiene la tira. Se puede
   reanudar más tarde (sección 8).

**Actualizar grupos:** abre `facebook.com/groups/joins/` (Tus grupos), baja la página hasta que no
aparezcan más grupos, junta nombre y link de cada uno y los combina con `grupos.txt`. Los grupos nuevos se
agregan, los existentes se respetan, incluido su `#`, y los que ya no aparecen se conservan comentados
con `# (ya no aparece)`.

## 7. Flujo de una publicación (semiautomático)

1. Se elige el grupo (sección 6) y se muestra en la ventana.
2. El navegador abre el link del grupo y da clic en "Escribe algo…" para abrir el compositor.
3. Pega el texto. Se inserta como si se pegara desde el portapapeles, para conservar emojis y saltos de
   línea.
4. Adjunta la imagen del anuncio y **un archivo de ubicación elegido al azar** (de los 3), con el campo
   de archivos del compositor. Espera a que terminen de cargar las vistas previas.
5. La ventana muestra *"Esperando a que des clic en Publicar…"*. **El programa nunca da clic en Publicar.**
6. Se detecta que se publicó cuando el compositor se cierra sin aviso de error. Se anota `publicado` en el
   historial y se pasa a la siguiente publicación.

Botones mientras corre:
- **Saltar este grupo:** cierra el compositor sin publicar, anota `saltado`, marca el grupo con `#` en
  `grupos.txt` y repite la misma publicación en otro grupo.
- **Detener:** cierra el compositor sin publicar y termina la tira. Lo que ya se publicó queda anotado.

Al terminar: *"TIRA 3 terminada ✅ (12 publicadas)"*.

## 8. Manejo de errores

| Situación | Comportamiento |
|---|---|
| La carpeta de tira no pasa la validación | Errores en el resumen; Empezar desactivado |
| Sesión de Facebook cerrada (aparece la pantalla de login) | Pausa: *"Inicia sesión en el navegador y da clic en Continuar"* |
| No aparece "Escribe algo…" o el compositor no abre en 30 s | Captura en `capturas/`, anota `error` y ofrece **Reintentar** o **Saltar este grupo** |
| Un archivo no termina de subir en 60 s | Igual que la fila anterior |
| La persona cierra el compositor sin publicar | Se toma como Saltar (sin marcar el grupo con `#`), se anota `saltado` y se ofrece otro grupo |
| Se cierra el programa o se va la luz a media tira | Al abrir la misma tira el mismo día, si el historial tiene publicaciones ya hechas: *"Ya se publicaron 5 de 12. ¿Seguir desde la 6?"* |
| No hay grupos disponibles | Aviso y se detiene (sección 6) |

## 9. Pruebas

- **Automáticas (pytest):** `tira.py` con una copia del `0 TEXTOS TIRA.txt` real, más casos rotos (falta
  una imagen, número repetido, separador con otra cantidad de guiones, archivo en cp1252); `grupos.py`
  (combinar listas sin perder los `#`); `historial.py`; `rotacion.py` con reloj simulado (regla de 60
  minutos, empates, sin candidatos).
- **Manuales con la cuenta real:** `facebook.py` no se puede probar sin la cuenta. Primera prueba:
  actualizar grupos y publicar 1 o 2 publicaciones en un grupo de confianza. Con eso se ajustan los
  selectores.

## 10. Entrega

- Repositorio en GitHub con el código, las pruebas y esta especificación.
- Un flujo de GitHub Actions en `windows-latest` que corre las pruebas y genera `PublicadorTiras.exe`
  (PyInstaller, con el Chromium de Playwright incluido) como archivo descargable.
- Un `LEEME.md` corto para el usuario: cómo abrirlo, iniciar sesión la primera vez y publicar una tira.

## 11. Riesgos

- **Bloqueo de la cuenta por spam:** se reduce con el clic humano, la regla de 60 minutos y la rotación
  pareja. Aun así, 120 publicaciones al día desde una cuenta es mucho; conviene repartirlas a lo largo del día.
- **Cambios en la página de Facebook:** pueden romper `facebook.py`. Los selectores se basan en roles y
  textos visibles (en español), no en clases internas, y todo está en ese único módulo.
- **Facebook en otro idioma:** se asume que el perfil está en español.
