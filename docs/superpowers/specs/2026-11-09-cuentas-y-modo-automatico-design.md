# Cuentas y modo automático — Especificación de diseño

Fecha: 2026-11-09 · Amplía `2026-11-09-publicador-tiras-design.md` (que sigue vigente en todo lo que esta no cambie).

## 1. Objetivo

1. **Escoger la cuenta** con la que se publica: el perfil de la empresa o cualquiera de sus Páginas (una por
   sucursal). Al perfil principal lo banearon en algunos grupos.
2. **Publicar solo**: el programa da el clic en «Publicar», con protecciones y avisos contra baneos.

**Éxito =** escoger «Sucursal X», darle Empezar y que la tira se publique sola, a un ritmo ajustable, con
avisos claros de riesgo y deteniéndose si Facebook muestra señales de bloqueo.

## 2. Decisiones del usuario

- Las Páginas se usan cambiando de perfil en el menú de Facebook (foto de arriba a la derecha → cambiar a la
  Página). Todas cuelgan del mismo inicio de sesión.
- Ritmo **ajustable**, con un mínimo de seguridad de **2 minutos** que no se puede bajar, y avisos de riesgo.
- **Sin límite** de publicaciones al día. Solo hay avisos informativos al llegar a 24 y 48 por cuenta.
- Si Facebook bloquea o pide verificación: **avisar** (qué cuenta y qué mensaje) y **ofrecer seguir con otra
  cuenta** o detener.
- Se mantiene el modo **con revisión** (clic humano) como opción.

## 3. Cuentas

- `cuentas.json` guarda `{"cuentas": [{"nombre": str, "tipo": "perfil"|"pagina"}], "ultima": str}`.
- Botón **Actualizar cuentas**: abre el menú de cuenta de Facebook, lee los perfiles disponibles y los guarda.
  El primero de tipo `perfil` es el **principal**.
- Combo **Cuenta** en la ventana. Antes de cada tira y antes de «Actualizar grupos», el programa revisa la cuenta
  activa en Facebook y, si no es la escogida, se cambia.
- **Grupos por cuenta:** `grupos/<cuenta>.txt`, con el mismo formato. Al detectar las cuentas por primera vez, el
  `grupos.txt` existente pasa a ser el del perfil principal (se renombra; no se pierde nada).
- **Historial:** nueva columna `cuenta`. Las filas sin cuenta se consideran del principal. La regla de minutos,
  la rotación y los grupos usados se calculan **por cuenta**. Las publicaciones hechas de una tira (para
  reanudar) se cuentan **sin importar la cuenta**, para no repetir un anuncio al cambiar de cuenta.
- Un grupo donde no se puede publicar (no aparece «Escribe algo…») se ignora **solo en esa cuenta**.

## 4. Modo de publicar y ritmo

- **Automático:** preparar → pausa de «revisión» al azar de 5 a 15 s → clic en «Publicar» (cuando esté
  habilitado, hasta 120 s por si sigue subiendo el video) → confirmar resultado → espera al azar entre
  `[mín, máx]` minutos con cuenta regresiva → siguiente. Detener y Saltar funcionan durante las esperas.
- **Con revisión:** igual que hoy.
- Ajustes en la ventana: modo, minutos mín. y máx. (mín ≥ 2; si máx < mín, máx = mín). Se guardan en
  `config.json`.
- Errores en automático (sin nadie mirando):
  - Grupo sin permiso para publicar → se ignora en esa cuenta y se usa otro grupo.
  - Otro error al preparar → captura, se anota `error` y se prueba otro grupo, sin marcarlo.
  - Facebook muestra error después de publicar → se anota `error` y se pasa a la **siguiente publicación**
    (si en realidad sí salió, así no se repite el anuncio).
  - Sesión cerrada → se pregunta (no se puede seguir sin sesión).

## 5. Avisos

Nivel `amarillo` (cuidado) o `rojo` (peligro), en una franja de color de la ventana. Los rojos además abren un
mensaje.

| Cuándo | Nivel | Texto |
|---|---|---|
| Mínimo < 5 min (ajuste) | amarillo | «Ritmo rápido: aumenta el riesgo de bloqueo» |
| Mínimo ≤ 3 min (ajuste) | rojo | «Ritmo muy rápido: riesgo alto de bloqueo» |
| La cuenta llega a 24 / 48 publicadas hoy | amarillo | ««X» lleva N publicaciones hoy: el riesgo de bloqueo sube» |
| 3 errores seguidos | amarillo | «Facebook podría estar limitando «X»» |
| Cuenta bloqueada hoy y se vuelve a escoger | rojo | ««X» tuvo un bloqueo hoy» |

## 6. Señales de bloqueo

- URL con `/checkpoint`, o un diálogo o aviso visible con textos como «bloqueado temporalmente», «estás
  bloqueado», «restringid», «confirma tu identidad», «revisión de seguridad», «actividad sospechosa»,
  «limitamos», «vas demasiado rápido».
- Se revisan al abrir cada grupo y después de publicar.
- Al detectarse: captura, se anota `bloqueo` en el historial, se detiene la tira y aparece en rojo
  «⛔ Facebook bloqueó o pidió verificación a «X»: «mensaje»», con las opciones **Seguir con otra cuenta** o
  **Detener**. Si se elige seguir, se escoge la cuenta y la tira sigue con las publicaciones que falten.

## 7. Pruebas

- Automáticas: cuentas, migración de grupos, historial por cuenta, `sesion` con dobles (modo automático, esperas
  con reloj falso, avisos, bloqueo, grupo sin permiso por cuenta, error después de publicar) y `facebook` contra
  páginas falsas (menú de perfiles, cambio de cuenta, clic en Publicar, detección de bloqueo).
- Manual con Facebook real (no se puede automatizar): Actualizar cuentas → que salgan las 3; escoger una Página
  → Actualizar grupos → 1 o 2 publicaciones en modo con revisión → luego automático.

## 8. Riesgos

- El menú de perfiles y los textos de bloqueo de Facebook pueden ser distintos a lo esperado. Todo está en
  constantes de `facebook.py`, y cada fallo deja captura.
- Publicar automáticamente sin límite aumenta el riesgo de bloqueo. El usuario lo eligió; el programa avisa.
