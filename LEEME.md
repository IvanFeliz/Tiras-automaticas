# Publicador de Tiras

Programa para publicar las tiras de publicidad en los grupos de Facebook. Abre cada grupo, pega el
texto y sube la imagen y la foto de ubicación. **Tú solo revisas y das clic en «Publicar».**

## 1. Descargarlo

1. En GitHub, entra a la pestaña **Actions** de este repositorio.
2. Abre la ejecución más reciente que tenga ✅ verde.
3. Hasta abajo, en **Artifacts**, descarga **PublicadorTiras**. Es un `.zip`: descomprímelo y te queda
   `PublicadorTiras.exe`. Ponlo donde quieras, por ejemplo en el Escritorio.

> Si Windows muestra «Windows protegió su PC», da clic en **Más información → Ejecutar de todas formas**.
> Sale porque el programa no tiene firma digital.

Necesitas **Google Chrome** o **Microsoft Edge** (Edge ya viene con Windows).

## 2. La primera vez

1. Abre `PublicadorTiras.exe`.
2. Da clic en **Cambiar** y escoge la carpeta **Tiras** (la que tiene `1.lunes`, `2 MARTES`, etc.).
3. Da clic en **Actualizar grupos**. Se abre un navegador aparte:
   - Inicia sesión en Facebook con la cuenta de la empresa. Solo se hace la primera vez: la sesión se queda guardada.
   - Regresa a la ventana del programa y da clic en **Continuar**.
   - El programa recorre «Tus grupos» y guarda la lista. Puede tardar un par de minutos.

## 3. Publicar una tira

1. Escoge el **Día** y la **Tira** (o usa **Escoger carpeta…** para una tira que esté en otro lado).
2. Revisa el resumen. Si algo sale en rojo (por ejemplo, falta una imagen), corrígelo en la carpeta y
   vuelve a escoger la tira.
3. Da clic en **▶ Empezar**.
4. En cada publicación, el programa deja todo listo en el navegador. **Revisa y da clic en «Publicar»
   en Facebook.** El programa lo detecta solo y pasa a la siguiente.
   - **Saltar este grupo**: no publica ahí, ignora ese grupo de ahora en adelante y usa otro.
   - Si cierras la ventanita de Facebook sin publicar, el programa prueba con otro grupo (sin ignorar el primero).
   - **Detener**: para todo. Lo publicado queda guardado y, si vuelves a abrir la misma tira el mismo día,
     te ofrece seguir con las que faltan.
   - Si Facebook muestra un error al publicar, el programa pregunta qué hacer. Revisa el grupo: si la
     publicación sí salió, elige **Sí se publicó**.
   - Si se vence la sesión de Facebook, el programa te pide volver a iniciarla y sigue donde iba.
   - Si tienes `historial.csv` abierto en Excel, el programa te pide cerrarlo para poder anotar.

## Archivos de datos

Con **Abrir carpeta de datos** ves:

- `grupos.txt`: la lista de grupos. Si pones `#` al principio de una línea, el programa ignora ese grupo.
  Si le quitas el `#`, el grupo vuelve a usarse.
- `historial.csv`: todo lo que se publicó, en qué grupo y a qué hora. Se abre en Excel.
- `capturas/`: capturas de pantalla de cuando algo falló.
- `errores.log`: detalles técnicos de errores inesperados (útil para arreglar el programa).

## Recomendaciones

- **Reparte las publicaciones a lo largo del día.** Muchas publicaciones seguidas desde la misma cuenta
  pueden hacer que Facebook la marque como spam.
- «Minutos antes de repetir un grupo» (60 por defecto) evita volver a publicar en el mismo grupo antes de ese tiempo.
- Si Facebook cambia su página y el programa ya no encuentra «Escribe algo…», saldrá un aviso con una
  captura. Manda esa captura para ajustar el programa.

## Formato de las carpetas (no cambiarlo)

```
Tiras/<día>/TIRA N/
  0 TEXTOS TIRA.txt     textos numerados "1. Título", separados por una línea de guiones -----
  1 ALGO.png … 12 ….png la imagen de cada texto, empieza con su número
  000.….jpeg, 0.….jpg, 0.….mp4   archivos de ubicación (se usa uno al azar en cada publicación)
```

La línea del título (`1. Cambio de Pantalla`) no se publica; se publica todo lo que va debajo.
