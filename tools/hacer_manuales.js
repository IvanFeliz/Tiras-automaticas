const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType, ImageRun, Table, TableRow, TableCell,
  WidthType, ShadingType, BorderStyle, LevelFormat, PageBreak, Footer, PageNumber, TableOfContents,
} = require("docx");

const SP = process.argv[2];      // carpeta con capturas
const SALIDA = process.argv[3];  // carpeta de salida
const LOGO = process.argv[4];
const img = (n) => fs.readFileSync(path.join(SP, n));

const AZUL = "1F4E9A", AZUL_CLARO = "DCE8FA", GRIS = "F2F2F2", AMARILLO = "FFF3CD", ROJO = "F8D7DA", VERDE = "D4EDDA";
const ANCHO = 9360; // carta con márgenes de 1": 12240 - 2*1440

const estilos = {
  default: { document: { run: { font: "Calibri", size: 22 } } },
  paragraphStyles: [
    { id: "Title", name: "Title", basedOn: "Normal", run: { font: "Calibri", size: 52, bold: true, color: AZUL },
      paragraph: { spacing: { before: 0, after: 120 }, alignment: AlignmentType.CENTER } },
    { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
      run: { font: "Calibri", size: 32, bold: true, color: AZUL },
      paragraph: { spacing: { before: 360, after: 120 }, keepNext: true, outlineLevel: 0 } },
    { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
      run: { font: "Calibri", size: 26, bold: true, color: "333333" },
      paragraph: { spacing: { before: 240, after: 80 }, keepNext: true, outlineLevel: 1 } },
  ],
};
const numeracion = {
  config: [
    { reference: "vinetas", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 540, hanging: 270 } } } }] },
    ...Array.from({ length: 30 }, (_, i) => ({ reference: `pasos${i}`, levels: [{ level: 0, format: LevelFormat.DECIMAL,
      text: "%1.", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 540, hanging: 360 } } } }] })),
  ],
};

// --- ayudantes ---------------------------------------------------------------
// Texto con **negritas**
function runs(texto, extra = {}) {
  return texto.split(/(\*\*[^*]+\*\*)/).filter(Boolean).map((t) =>
    t.startsWith("**") ? new TextRun({ text: t.slice(2, -2), bold: true, ...extra }) : new TextRun({ text: t, ...extra }));
}
const P = (t, o = {}) => new Paragraph({ children: runs(t), spacing: { after: 120 }, ...o });
const H1 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(t)] });
const H2 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(t)] });
const V = (t) => new Paragraph({ numbering: { reference: "vinetas", level: 0 }, children: runs(t), spacing: { after: 60 } });
let lista = 0;
const pasos = (items) => { const ref = `pasos${lista++}`;
  return items.map((t) => new Paragraph({ numbering: { reference: ref, level: 0 }, children: runs(t), spacing: { after: 60 } })); };
const salto = () => new Paragraph({ children: [new PageBreak()] });
function captura(nombre, pie, ancho = 470) {
  const alto = Math.round(ancho * 730 / 780);
  return [
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 120, after: 40 },
      children: [new ImageRun({ type: "png", data: img(nombre), transformation: { width: ancho, height: alto },
        altText: { title: pie, description: pie, name: nombre } })] }),
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 200 },
      children: [new TextRun({ text: pie, italics: true, size: 18, color: "666666" })] }),
  ];
}
const borde = { style: BorderStyle.SINGLE, size: 4, color: "BFBFBF" };
const bordes = { top: borde, bottom: borde, left: borde, right: borde };
function celda(texto, ancho, fondo, negrita = false) {
  return new TableCell({ width: { size: ancho, type: WidthType.DXA }, borders: bordes,
    shading: fondo ? { fill: fondo, type: ShadingType.CLEAR, color: "auto" } : undefined,
    margins: { top: 80, bottom: 80, left: 120, right: 120 },
    children: [new Paragraph({ children: runs(texto, negrita ? { bold: true } : {}) })] });
}
function tabla(encabezado, filas, anchos, colores = []) {
  return new Table({ width: { size: ANCHO, type: WidthType.DXA }, columnWidths: anchos, rows: [
    new TableRow({ tableHeader: true, children: encabezado.map((t, i) => celda(t, anchos[i], AZUL_CLARO, true)) }),
    ...filas.map((f, r) => new TableRow({ children: f.map((t, i) => celda(t, anchos[i], i === 0 ? colores[r] : undefined)) })),
  ] });
}
function recuadro(titulo, texto, fondo) {
  return new Table({ width: { size: ANCHO, type: WidthType.DXA }, columnWidths: [ANCHO], rows: [new TableRow({ children: [
    new TableCell({ width: { size: ANCHO, type: WidthType.DXA }, borders: bordes,
      shading: { fill: fondo, type: ShadingType.CLEAR, color: "auto" }, margins: { top: 120, bottom: 120, left: 180, right: 180 },
      children: [new Paragraph({ children: [new TextRun({ text: titulo, bold: true })] }),
                 ...[].concat(texto).map((t) => new Paragraph({ children: runs(t), spacing: { before: 60 } }))] })] })] });
}
const espacio = () => new Paragraph({ children: [], spacing: { after: 80 } });
function portada(titulo, subtitulo) {
  return [
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 1200, after: 240 },
      children: [new ImageRun({ type: "png", data: fs.readFileSync(LOGO), transformation: { width: 180, height: 180 },
        altText: { title: "Logo", description: "Logo del Publicador de Tiras", name: "logo" } })] }),
    new Paragraph({ style: "Title", children: [new TextRun(titulo)] }),
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 600 },
      children: [new TextRun({ text: subtitulo, size: 28, color: "555555" })] }),
    new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: "Publicador de Tiras · Versión de noviembre de 2026", size: 20, color: "777777" })] }),
  ];
}
const pie = () => ({ default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
  children: [new TextRun({ text: "Página ", size: 18, color: "777777" }), new TextRun({ children: [PageNumber.CURRENT], size: 18, color: "777777" })] })] }) });
function documento(hijos) {
  return new Document({ creator: "Publicador de Tiras", title: "Manual", styles: estilos, numbering: numeracion,
    sections: [{ properties: { page: { size: { width: 12240, height: 15840 }, margin: { top: 1440, bottom: 1440, left: 1440, right: 1440 } } },
      footers: pie(), children: hijos }] });
}
const LINK = "https://github.com/IvanFeliz/Tiras-automaticas/releases/latest/download/PublicadorTiras.zip";

// =============================================================================================
// 1) MANUAL DE USUARIO
// =============================================================================================
const usuario = [
  ...portada("Manual de usuario", "Cómo publicar las tiras de publicidad en los grupos de Facebook"),
  salto(),
  new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun("Contenido")] }),
  ...["1. ¿Qué hace el programa?", "2. Instalarlo", "3. La pantalla", "4. La primera vez", "5. Publicar una tira",
      "6. Los dos modos de publicar", "7. Los avisos", "8. Si algo sale mal", "9. Cómo deben estar las carpetas",
      "10. Actualizar a una versión nueva"].map((t) => new Paragraph({ children: [new TextRun({ text: t, size: 24 })],
      spacing: { after: 100 }, indent: { left: 360 } })),
  salto(),

  H1("1. ¿Qué hace el programa?"),
  P("El **Publicador de Tiras** sube por ti las tiras de publicidad a los grupos de Facebook. Una tira son 12 anuncios; cada anuncio lleva su **texto**, su **imagen** y una **foto o video de ubicación** del local (se escoge uno al azar). Cada anuncio va en un **grupo diferente**."),
  P("El programa abre el grupo, pega el texto, sube las imágenes y publica (o espera a que tú des clic, según el modo). Lleva la cuenta de en qué grupos ya se publicó para ir rotando y no repetir."),
  recuadro("Lo más importante", [
    "• Puedes publicar con el **perfil de la empresa** o con cualquiera de sus **Páginas** (sucursales).",
    "• Dos formas de publicar: **Con revisión** (tú das clic en «Publicar») o **Automático** (el programa publica solo).",
    "• Si Facebook muestra señales de bloqueo, el programa **se detiene solo** y te avisa.",
  ], AZUL_CLARO),

  H1("2. Instalarlo"),
  ...pasos([
    `Descarga el programa desde este link: **${LINK}**`,
    "En tu carpeta **Descargas**, da clic derecho en **PublicadorTiras.zip** → **Extraer todo…** → **Extraer**.",
    "Entra a la carpeta **PublicadorTiras**. Adentro está **PublicadorTiras.exe** (el programa) y una carpeta **_internal**. **No separes el .exe de esa carpeta.**",
    "Opcional: clic derecho en **PublicadorTiras.exe** → **Enviar a** → **Escritorio (crear acceso directo)**.",
    "Ábrelo con doble clic. Si Windows dice **«Windows protegió su PC»**, da clic en **Más información** → **Ejecutar de todas formas** (pasa porque el programa no tiene firma digital; solo la primera vez).",
  ]),
  P("Necesitas tener **Google Chrome** o **Microsoft Edge** (Edge ya viene con Windows)."),
  recuadro("Ojo", "En GitHub, el botón verde **«Code → Download ZIP»** baja el código, **no** el programa. Usa siempre el link de arriba.", AMARILLO),

  H1("3. La pantalla"),
  P("El programa tiene tres pestañas:"),
  tabla(["Pestaña", "Para qué sirve"], [
    ["📢 **Publicar**", "La del día a día: escoger cuenta y tira, y publicar."],
    ["👤 **Cuentas y grupos**", "Leer las cuentas de Facebook y los grupos de cada cuenta. Se usa de vez en cuando."],
    ["⚙️ **Ajustes**", "Carpeta de las tiras, tiempo para repetir grupos, abrir el historial y guía rápida."],
  ], [2800, 6560]),
  ...captura("v6_publicar.png", "Pestaña Publicar"),

  H1("4. La primera vez"),
  H2("4.1 Escoger la carpeta de las tiras"),
  ...pasos([
    "Ve a la pestaña **⚙️ Ajustes**.",
    "En **Carpeta de las tiras**, da clic en **📁 Cambiar** y escoge la carpeta **Tiras** (la que tiene 1.lunes, 2 MARTES, etc.).",
  ]),
  H2("4.2 Leer las cuentas de Facebook"),
  ...pasos([
    "Ve a **👤 Cuentas y grupos** y da clic en **🔄 Actualizar cuentas**.",
    "Se abre un navegador aparte. **Inicia sesión en Facebook** con la cuenta de la empresa (solo la primera vez; la sesión se queda guardada) y regresa al programa a dar **Continuar**.",
    "El programa lee el menú de tu foto en Facebook y muestra las cuentas: **👤 Perfil** y **🏪 Página** (sucursales).",
    "La primera vez te pregunta **cuál es el perfil principal**: escoge el que usaban antes. Los grupos e historial anteriores quedan a su nombre.",
  ]),
  H2("4.3 Leer los grupos de cada cuenta"),
  P("**Cada cuenta tiene sus propios grupos**: una Página solo puede publicar en los grupos a los que ella se unió."),
  ...pasos([
    "En la pestaña **📢 Publicar**, escoge la cuenta en el paso ①.",
    "Ve a **👤 Cuentas y grupos** y da clic en **🔄 Actualizar grupos**. El programa recorre «Tus grupos» de esa cuenta (tarda un par de minutos).",
    "Repite con cada cuenta que vayas a usar.",
  ]),
  ...captura("v6_cuentas.png", "Pestaña Cuentas y grupos"),

  H1("5. Publicar una tira"),
  P("En la pestaña **📢 Publicar**, sigue los pasos de arriba hacia abajo:"),
  tabla(["Paso", "Qué hacer"], [
    ["① ¿Con qué cuenta publico?", "Escoge el perfil o la Página. El encabezado azul siempre muestra la cuenta activa."],
    ["② ¿Qué tira publico?", "Escoge el **Día** y la **Tira**, o usa **📁 Escoger carpeta…** para una tira que esté en otro lado. Revisa la etiqueta: ✅ verde = lista; ❌ roja = falta algo (dice qué)."],
    ["③ ¿Cómo publico?", "**👀 Con revisión** o **⚡ Automático**, y los minutos de espera entre publicaciones."],
    ["④ ¡A publicar!", "Da clic en **▶ EMPEZAR**. La barra muestra el avance (por ejemplo 4 de 12), el grupo actual y la cuenta regresiva."],
  ], [3000, 6360]),
  ...captura("v6_corriendo.png", "Mientras publica: barra de progreso, grupo actual y cuenta regresiva"),
  H2("Botones mientras publica"),
  V("**⏭ Saltar grupo**: no publica en ese grupo, lo deja de usar con esa cuenta y prueba otro."),
  V("**⏹ Detener**: para todo. Lo publicado queda guardado. Si vuelves a abrir la misma tira el mismo día, te ofrece seguir con las que faltan **sin repetir** las que ya salieron."),

  H1("6. Los dos modos de publicar"),
  tabla(["Modo", "Cómo funciona", "Cuándo usarlo"], [
    ["👀 **Con revisión**", "El programa deja todo listo en Facebook y **tú das clic en «Publicar»**. Detecta solo que ya publicaste y pasa al siguiente.", "Para probar una cuenta o tira nueva, o si quieres revisar cada anuncio."],
    ["⚡ **Automático**", "El programa **publica solo**. Antes de cada clic hace una pausa corta al azar y entre una publicación y otra espera los minutos que pusiste (mínimo 2).", "Para el día a día, cuando ya probaste que todo sale bien."],
  ], [2000, 4360, 3000]),
  espacio(),
  recuadro("Recomendación para cuidar las cuentas", [
    "• Usa un ritmo de **5 a 10 minutos** entre publicaciones. El mínimo de 2 minutos es posible, pero el riesgo de bloqueo es alto.",
    "• **Reparte las tiras a lo largo del día** en lugar de publicar todas seguidas.",
    "• Prueba cada cuenta nueva primero **Con revisión** con 1 o 2 publicaciones.",
  ], VERDE),

  H1("7. Los avisos"),
  tabla(["Aviso", "Qué significa", "Qué hacer"], [
    ["🟡 Amarillo", "Cuidado: el riesgo de bloqueo va subiendo (ritmo rápido, la cuenta lleva 24 o 48 publicaciones hoy, o hay errores seguidos).", "Considera bajar el ritmo o seguir más tarde."],
    ["🔴 Rojo", "Peligro: ritmo muy rápido (3 minutos o menos) o una cuenta que ya tuvo un bloqueo hoy.", "Baja el ritmo o usa otra cuenta."],
    ["⛔ Bloqueo", "Facebook bloqueó la cuenta o pidió verificación. La tira se detiene sola.", "El programa te ofrece **seguir con otra cuenta** (sin repetir anuncios). Revisa la cuenta bloqueada en Facebook."],
  ], [1700, 4260, 3400], [AMARILLO, ROJO, ROJO]),

  H1("8. Si algo sale mal"),
  tabla(["Lo que pasa", "Qué hacer"], [
    ["La etiqueta de la tira sale en rojo ❌", "Lee qué falta (por ejemplo «Falta la imagen del texto 5»), corrígelo en la carpeta y vuelve a escoger la tira."],
    ["«Facebook pide iniciar sesión»", "Inicia sesión en el navegador que abrió el programa y da **Continuar**. El programa sigue donde iba, con la cuenta correcta."],
    ["«No se pudo confirmar la cuenta»", "El programa se detuvo para no publicar con otra cuenta. Da clic en **Actualizar cuentas** y vuelve a empezar."],
    ["Un grupo «no deja publicar»", "La cuenta no puede publicar ahí (por ejemplo, la banearon). Se ignora **solo para esa cuenta**; las demás lo siguen usando."],
    ["«Van 5 errores seguidos»", "Facebook podría estar limitando la cuenta. Revisa el navegador; si ves algo raro, elige **Detener**."],
    ["«No hay grupos disponibles ahora»", "Ya se usaron los grupos de esa cuenta en la última hora. Espera, usa otra cuenta, o da **Actualizar grupos**."],
    ["Cerré el navegador sin querer", "No pasa nada. Da clic otra vez en **EMPEZAR**: se abre uno nuevo y sigue con lo que falta."],
    ["«historial.csv está abierto en Excel»", "Cierra Excel y da **Reintentar**."],
    ["«El programa ya está abierto»", "Ya hay una ventana del programa abierta; búscala en la barra de tareas."],
    ["Algo raro que no está aquí", "En **⚙️ Ajustes → Abrir carpeta de datos** está la carpeta **capturas** (fotos del error) y **errores.log**. Mándalos a quien mantiene el programa."],
  ], [3300, 6060]),

  H1("9. Cómo deben estar las carpetas"),
  P("El programa lee las carpetas tal como ya las tienen. **No cambies el formato:**"),
  tabla(["Elemento", "Formato"], [
    ["Carpetas", "Tiras → día (1.lunes, 2 MARTES…) → TIRA 1, TIRA 2…"],
    ["Textos", "Un solo archivo **.txt** por tira. Cada texto empieza con su número y título (**1. Cambio de Pantalla**) y se separa del siguiente con una línea de guiones (**-----**)."],
    ["Imágenes", "Empiezan con el número del texto: **1 PANTALLA.png**, **2 TAPA.png**… (png, jpg, jpeg o webp)."],
    ["Ubicación", "Archivos que empiezan con **0** o **000** (foto del local, croquis, video). En cada publicación se usa uno al azar."],
  ], [2000, 7360]),
  P("La línea del título (**1. Cambio de Pantalla**) **no se publica**; se publica todo lo que va debajo."),

  H1("10. Actualizar a una versión nueva"),
  ...pasos([
    "Cierra el programa.",
    "Borra la carpeta **PublicadorTiras** vieja.",
    `Descarga y descomprime la nueva desde el mismo link: **${LINK}**`,
  ]),
  P("Tus cuentas, grupos, historial y la sesión de Facebook **no se pierden**: se guardan en otra carpeta de Windows."),
];

// =============================================================================================
// 2) GUÍA RÁPIDA (una hoja)
// =============================================================================================
const rapida = [
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 60 },
    children: [new ImageRun({ type: "png", data: fs.readFileSync(LOGO), transformation: { width: 70, height: 70 },
      altText: { title: "Logo", description: "Logo", name: "logo" } })] }),
  new Paragraph({ style: "Title", children: [new TextRun("Guía rápida")] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 200 }, children: [new TextRun({ text: "Publicador de Tiras", color: "555555", size: 24 })] }),
  H2("La primera vez"),
  ...pasos([
    "**⚙️ Ajustes → 📁 Cambiar**: escoge la carpeta **Tiras**.",
    "**👤 Cuentas y grupos → 🔄 Actualizar cuentas**: inicia sesión en Facebook y da **Continuar**.",
    "Escoge cada cuenta y da **🔄 Actualizar grupos**.",
  ]),
  H2("Cada vez que publiques"),
  ...pasos([
    "**① Cuenta**: con cuál publicas (perfil o Página).",
    "**② Tira**: día y tira. Debe salir ✅ verde.",
    "**③ Modo**: 👀 Con revisión (tú das clic) o ⚡ Automático (publica solo; recomendado 5 a 10 minutos).",
    "**④ ▶ EMPEZAR**. Para parar: **⏹ Detener** (lo publicado se guarda; después sigue sin repetir).",
  ]),
  H2("Avisos"),
  tabla(["Aviso", "Qué hacer"], [
    ["🟡 Cuidado", "Riesgo de bloqueo subiendo: baja el ritmo o sigue más tarde."],
    ["🔴 Peligro", "Riesgo alto: baja el ritmo o cambia de cuenta."],
    ["⛔ Bloqueo", "Se detuvo solo. Sigue con otra cuenta y revisa la bloqueada."],
  ], [2000, 7360], [AMARILLO, ROJO, ROJO]),
  espacio(),
  recuadro("Consejos", [
    "• Prueba cada cuenta nueva **Con revisión** con 1 o 2 publicaciones.",
    "• Reparte las tiras a lo largo del día.",
    `• Versión nueva: borra la carpeta vieja y baja la nueva de ${LINK}`,
  ], AZUL_CLARO),
];

// =============================================================================================
// 3) MANUAL TÉCNICO
// =============================================================================================
const tecnico = [
  ...portada("Manual técnico", "Datos, mantenimiento y solución de problemas"),
  salto(),
  H1("1. Componentes"),
  tabla(["Parte", "Descripción"], [
    ["Programa", "Carpeta **PublicadorTiras** con **PublicadorTiras.exe** y **_internal**. Hecho en Python (Tkinter + Playwright), empaquetado con PyInstaller."],
    ["Navegador", "Usa el **Chrome** o **Edge** instalado en Windows, con un perfil propio (no toca el perfil personal de Chrome)."],
    ["Código", "Repositorio **github.com/IvanFeliz/Tiras-automaticas** (rama **main**)."],
    ["Versiones", "Cada cambio en **main** genera solo una versión nueva en **Releases** (GitHub Actions corre las pruebas en Windows y arma el programa)."],
  ], [2000, 7360]),

  H1("2. Dónde se guardan los datos"),
  P("Todo está en **%APPDATA%\\PublicadorTiras** (se abre con **⚙️ Ajustes → Abrir carpeta de datos**). No se pierde al actualizar el programa."),
  tabla(["Archivo o carpeta", "Contenido"], [
    ["config.json", "Carpeta de tiras, último día/tira, modo, minutos de espera, minutos para repetir grupo."],
    ["cuentas.json", "Cuentas detectadas (nombre y tipo: perfil o página) y la última usada."],
    ["grupos\\<cuenta>-xxxxxx.txt", "Grupos de cada cuenta, una línea **nombre | link**."],
    ["historial.csv", "Todo lo publicado: fecha, día, tira, número, título, grupo, link, archivo de ubicación, resultado y cuenta."],
    ["navegador\\", "Perfil del navegador con la **sesión de Facebook**. **No compartir esta carpeta.**"],
    ["capturas\\", "Capturas de pantalla de errores y bloqueos."],
    ["errores.log", "Detalle técnico de errores inesperados."],
    ["*.bak", "Respaldo automático de grupos e historial antes de reescribirlos."],
  ], [3000, 6360]),

  H1("3. Formato de los archivos de grupos"),
  V("**Nombre | https://www.facebook.com/groups/123/** → grupo activo."),
  V("**# Nombre | link** → ignorado a mano. Quitar el # lo vuelve a activar."),
  V("**# (sin permiso) Nombre | link** → la cuenta no pudo publicar ahí. Se ignora solo para esa cuenta."),
  V("**# (ya no aparece) Nombre | link** → ya no salió en «Tus grupos». Se reactiva solo si vuelve a aparecer."),
  P("Al dar **Actualizar grupos** se agregan los nuevos y se respetan las marcas. Si el escaneo encuentra menos de la mitad de los grupos activos (internet lento), no desactiva ninguno."),

  H1("4. Reglas que sigue el programa"),
  tabla(["Regla", "Detalle"], [
    ["Rotación", "Escoge primero los grupos que llevan más tiempo sin publicación de esa cuenta; si hay empate, al azar."],
    ["Repetir grupo", "La misma cuenta no publica en el mismo grupo antes de los minutos configurados (60 por defecto)."],
    ["Misma tira", "En una tira no se repite grupo, ni siquiera entre cuentas distintas, para no poner el mismo anuncio dos veces en un grupo."],
    ["Reanudar", "Las publicaciones ya hechas hoy de una tira (con cualquier cuenta) se omiten al volver a empezarla."],
    ["Cuenta correcta", "Antes de cada publicación confirma la cuenta activa en el menú de Facebook; si no puede, se detiene."],
    ["Automático", "Pausa de 5 a 15 s antes del clic; espera al azar entre el mínimo y máximo de minutos; límite de 3 minutos esperando el resultado."],
    ["Bloqueo", "Si detecta textos de bloqueo o verificación (o la página /checkpoint) se detiene, guarda captura y anota «bloqueo»."],
    ["Errores seguidos", "Aviso a los 3; a los 5 se pausa y pregunta."],
  ], [2200, 7160]),

  H1("5. Solución de problemas"),
  tabla(["Problema", "Causa probable y solución"], [
    ["No abre el navegador", "No hay Chrome ni Edge, u otra ventana del programa está abierta. Cerrar todo y volver a abrir."],
    ["«No se encontró el menú de cuenta» o la lista de perfiles", "Facebook cambió su página. Mandar la captura de **capturas\\** a quien mantiene el programa; los textos y selectores están en **src/publicador/facebook.py** (constantes al inicio)."],
    ["Siempre dice «no aparece el cuadro Escribe algo…»", "Igual que arriba, o Facebook está en otro idioma (el programa espera español)."],
    ["Se perdió la sesión de Facebook", "Iniciar sesión otra vez en el navegador del programa. Si persiste, borrar la carpeta **navegador\\** (se pedirá iniciar sesión de nuevo)."],
    ["Historial o grupos dañados", "Usar el archivo **.bak** que está al lado (renombrarlo quitando .bak)."],
    ["Se abre dos veces", "El programa lo impide con un candado (**.abierto.lock**). Si quedó trabado tras un apagón, borrar ese archivo."],
  ], [3200, 6160]),

  H1("6. Pruebas y calidad"),
  P("El proyecto tiene **más de 200 pruebas automáticas** que corren en Windows en cada cambio, entre ellas:"),
  V("3,000 simulaciones de publicación al azar (cuentas, bloqueos, errores y botones en momentos al azar)."),
  V("4,500 archivos raros de tiras, grupos e historial (formatos del Bloc de notas y de Excel)."),
  V("Corridas completas con navegador real contra páginas que imitan a Facebook."),
  V("La ventana con todo conectado: publicar, bloquearse y seguir con otra cuenta, detener y cerrar."),
  recuadro("Límite conocido", "Las pruebas usan páginas que imitan a Facebook. El menú de perfiles, los mensajes de bloqueo y el botón «Publicar» reales solo se confirman usando el programa con la cuenta real.", AMARILLO),
];

(async () => {
  for (const [nombre, hijos] of [["Manual de usuario - Publicador de Tiras.docx", usuario],
                                  ["Guia rapida - Publicador de Tiras.docx", rapida],
                                  ["Manual tecnico - Publicador de Tiras.docx", tecnico]]) {
    fs.writeFileSync(path.join(SALIDA, nombre), await Packer.toBuffer(documento(hijos)));
    console.log("ok", nombre);
  }
})();
