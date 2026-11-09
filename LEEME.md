# Publicador de Tiras

Programa para publicar las tiras de publicidad en los grupos de Facebook. Abre cada grupo, pega el
texto y sube la imagen y la foto de ubicación. **Tú solo revisas y das clic en «Publicar».**

## 1. Descargarlo

1. Descarga la última versión desde este link:
   https://github.com/IvanFeliz/Tiras-automaticas/releases/latest/download/PublicadorTiras.zip
   (o entra a la sección **Releases** del repositorio y descarga `PublicadorTiras.zip`).
2. **No** uses el botón verde «Code → Download ZIP»: ese es el código, no el programa.
3. El archivo es un `.zip`: descomprímelo completo
   (clic derecho → **Extraer todo…**). Te queda una carpeta con `PublicadorTiras.exe` y una subcarpeta
   `_internal`. **No saques el `.exe` de esa carpeta**: necesita lo que está en `_internal`.
   Puedes poner la carpeta donde quieras y crear un acceso directo al `.exe` en el Escritorio
   (clic derecho en `PublicadorTiras.exe` → **Enviar a → Escritorio (crear acceso directo)**).

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

## Cuentas (perfil y Páginas de sucursal)

1. Da clic en **Actualizar cuentas**. El programa abre el menú de tu foto en Facebook y lee los perfiles
   disponibles (el perfil de la empresa y sus Páginas).
2. Escoge la cuenta en **Cuenta**. El programa se cambia solo a esa cuenta antes de publicar.
3. **Cada cuenta tiene sus propios grupos**: con la cuenta escogida, da clic en **Actualizar grupos**.
   Una Página solo puede publicar en los grupos a los que ella se unió.
4. Si en un grupo una cuenta no puede publicar (por ejemplo, la banearon), el programa lo ignora **solo para
   esa cuenta** y sigue con otro.

## Modo automático

- **Con revisión:** el programa deja todo listo y tú das clic en «Publicar».
- **Automático:** el programa publica solo y espera entre los minutos que pongas (mínimo 2) antes de la
  siguiente publicación. Mientras espera, ves la cuenta regresiva. **Detener** funciona en cualquier momento.
- ⚠️ **Riesgo:** publicar automáticamente en muchos grupos puede hacer que Facebook bloquee la cuenta.
  El programa avisa:
  - 🟡 / 🔴 si el ritmo es rápido (menos de 5 minutos, o 3 o menos).
  - 🟡 cuando una cuenta llega a 24 y a 48 publicaciones en el día.
  - 🟡 si hay varios errores seguidos (Facebook podría estar limitando la cuenta).
- ⛔ Si Facebook muestra un bloqueo o pide verificación, el programa **se detiene**, te dice qué cuenta y qué
  mensaje, y te ofrece **seguir la tira con otra cuenta**. Lo ya publicado no se repite.
- Recomendación: prueba primero cada cuenta nueva en **Con revisión** con 1 o 2 publicaciones.

## Archivos de datos

Con **Abrir carpeta de datos** ves:

- `grupos/<cuenta>.txt`: la lista de grupos de cada cuenta. Si pones `#` al principio de una línea, el programa ignora ese grupo.
  Si le quitas el `#`, el grupo vuelve a usarse.
- `historial.csv`: todo lo que se publicó, en qué grupo y a qué hora. Se abre en Excel para consultarlo;
  mejor **no lo guardes desde Excel** (si pasa, el programa lo repara solo, pero es mejor evitarlo).
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
