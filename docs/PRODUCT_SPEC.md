Quiero crear mi propio **launcher de consola portable para PC**, pensado para ejecutarse desde un USB.

No tengo experiencia programando, así que quiero que actúes como mi desarrollador y me guíes paso a paso. **No quiero que simplemente me des código: quiero que construyas el proyecto conmigo, ejecutes las pruebas necesarias y corrijas los errores que encuentres.**

# OBJETIVO

Quiero que al conectar mi USB a un PC pueda abrir el launcher y tener una interfaz tipo consola desde la que pueda gestionar y ejecutar mis juegos de PC y mis propios juegos compatibles con emuladores.

Quiero que sea **portable**: la configuración, biblioteca, carátulas y demás datos que sea posible deben guardarse en el USB.

El launcher **no debe depender de una letra concreta del USB**. Si Windows lo monta como `D:`, `E:`, `F:`, etc., debe seguir funcionando utilizando rutas relativas al propio launcher.

# 🎨 DISEÑO Y EXPERIENCIA DE USUARIO

La interfaz debe sentirse como una **consola de videojuegos moderna**, no como un programa típico de Windows.

Quiero incluir un **tema principal inspirado en la experiencia de interfaz de SteamOS/Steam Deck**.

Me refiero a:

* Navegación pensada primero para mando.
* Interfaz a pantalla completa.
* Grandes carátulas de juegos.
* Biblioteca visual.
* Menús sencillos y rápidos.
* Animaciones y transiciones suaves.
* Información del juego presentada claramente.
* Acciones importantes muy visibles.
* Navegación mediante mando, teclado y ratón.
* Adaptación a diferentes resoluciones.
* Sensación de estar utilizando una consola.

**No copies literalmente Steam, SteamOS, Steam Deck, sus logotipos, iconos, diseños protegidos ni su identidad visual.** Quiero una interfaz propia que consiga una experiencia similar de comodidad y navegación.

El tema principal debe incluir:

* Tema oscuro.
* Tema claro opcional.
* Posibilidad de crear posteriormente temas personalizados.
* Menú principal visual.
* Biblioteca.
* Vista individual de cada juego.
* Ajustes.
* Animaciones discretas y fluidas.
* Soporte completo para mando.

La estética y la experiencia de usuario son **una prioridad desde el principio**.

# 🏠 PANTALLA PRINCIPAL

Quiero:

* Juegos recientes.
* Favoritos.
* Continuar jugando.
* Juegos organizados por consola/plataforma.
* Juegos de PC.
* Buscador global.
* Tiempo jugado.
* Carátulas.
* Información de los juegos.

Al seleccionar un juego quiero poder pulsar **JUGAR** y que se abra automáticamente.

Para juegos emulados debe utilizar el emulador configurado.

Para juegos de PC debe abrir el ejecutable correspondiente.

# 🛋️ MODO TV / SOFÁ

Quiero un modo pensado para conectar el PC a una televisión:

* Pantalla completa.
* Interfaz especialmente cómoda desde el mando.
* Elementos grandes.
* Navegación sin necesidad de ratón.
* Inicio automático opcional en modo consola.

Debe sentirse como un modo **Big Picture**, pero con diseño propio.

# ⚙️ CONFIGURACIÓN

Quiero que prácticamente TODO pueda configurarse desde la propia aplicación, sin tener que editar archivos manualmente.

## 🕹️ EMULADORES

Debe existir una sección para:

* Añadir un emulador seleccionando su ejecutable.
* Eliminarlo.
* Cambiar su ubicación.
* Indicar qué consola emula.
* Configurar argumentos de lanzamiento.
* Comprobar si el ejecutable sigue existiendo.
* Probar si el emulador funciona correctamente.

Si es técnicamente viable y legal, deja preparada la arquitectura para poder gestionar la instalación/actualización de emuladores desde el launcher.

## 🎮 JUEGOS

Quiero poder:

* Añadir carpetas de juegos.
* Elegir qué plataforma corresponde a cada carpeta.
* Escanear carpetas.
* Detectar juegos nuevos.
* Eliminar juegos de la biblioteca sin borrar el archivo original.
* Volver a escanear.
* Añadir juegos individuales.
* Añadir juegos de PC normales.
* Configurar el ejecutable de cada juego.

## 📂 RUTAS

Quiero poder configurar:

* Carpeta de juegos.
* Carpeta de emuladores.
* Carpeta de partidas.
* Carpeta de carátulas.
* Carpeta de backups.
* Otras carpetas necesarias.

Siempre que sea posible utiliza **rutas relativas al propio launcher/USB**.

Nunca dependas de que el USB tenga siempre la misma letra de unidad.

# 🎮 MANDOS

Quiero:

* Detectar mandos conectados.
* Configurar botones.
* Crear perfiles.
* Guardar configuraciones.
* Detectar automáticamente cuando se conecta/desconecta un mando.
* Poder utilizar teclado y ratón.
* Configurar qué mando controla el launcher.

# 🖥️ DETECCIÓN DEL PC

Quiero una sección que detecte automáticamente:

* Resolución de pantalla.
* Pantalla disponible.
* Mando conectado.
* Espacio disponible en el USB.
* CPU.
* GPU.
* RAM.
* Sistema operativo.

Utiliza esta información para adaptar el launcher cuando sea necesario.

# 📚 BIBLIOTECA

Cada juego debería poder tener:

* Nombre.
* Plataforma.
* Ruta.
* Carátula.
* Descripción.
* Favorito.
* Última vez jugado.
* Tiempo jugado.
* Emulador utilizado.
* Ejecutable.
* Estado de disponibilidad.

También quiero:

* Historial.
* Favoritos.
* Juegos recientes.
* Estadísticas básicas.
* Buscador.
* Filtros por plataforma.
* Ordenar por nombre, recientemente jugado, tiempo jugado, etc.

# 💾 PARTIDAS

Quiero un sistema para hacer **copias de seguridad de las partidas guardadas**, siempre que sea técnicamente posible.

Debe permitir:

* Crear backups.
* Restaurarlos.
* Ver cuándo se hizo cada backup.
* Configurar dónde se guardan.
* Crear backups manuales.
* Preparar la arquitectura para backups automáticos.

No quiero que el launcher modifique o borre partidas sin confirmación.

# 🖼️ CARÁTULAS

Quiero poder:

* Añadir una carátula manualmente.
* Cambiarla.
* Eliminarla.
* Guardarla en el USB.

Si implementas descarga automática de carátulas, utiliza únicamente servicios/APIs apropiados y legales y deja también la opción de añadirlas manualmente.

# 🔍 ESCANEO DE BIBLIOTECA

Quiero que pueda pulsar:

**Actualizar biblioteca**

y que el launcher:

1. Busque juegos nuevos.
2. Detecte juegos eliminados o movidos.
3. Actualice la información.
4. Mantenga los juegos existentes.
5. No borre archivos originales.

Debe ser rápido incluso con una biblioteca grande.

# 📊 ESTADÍSTICAS

Quiero poder ver:

* Tiempo total jugado.
* Juegos más jugados.
* Últimos juegos utilizados.
* Número de juegos por plataforma.

# 🛠️ DIAGNÓSTICO

Quiero una pantalla que compruebe:

* Emuladores configurados.
* Ejecutables existentes.
* Carpetas configuradas.
* Juegos detectados.
* Espacio disponible.
* Mandos.
* Problemas de configuración.
* Archivos importantes del launcher.

Debe explicar los errores de forma sencilla y decir cómo solucionarlos cuando sea posible.

# 🔄 ACTUALIZACIONES

Quiero preparar un sistema para:

* Comprobar si existe una nueva versión del launcher.
* Informar al usuario.
* Actualizar el launcher de forma segura.
* Evitar perder la configuración y biblioteca.

La actualización debe respetar la naturaleza portable del proyecto.

# 📦 PORTABILIDAD

Este punto es MUY importante.

Quiero que el launcher pueda vivir completamente dentro del USB siempre que sea posible.

Debe:

* Utilizar rutas relativas.
* No depender de una letra concreta de unidad.
* Guardar configuración en el USB.
* Guardar biblioteca en el USB.
* Guardar carátulas en el USB.
* Guardar estadísticas en el USB.
* Guardar backups en el USB.
* Evitar escribir datos innecesarios en el PC donde se ejecuta.

Si alguna función necesita escribir datos fuera del USB por limitaciones de Windows o de un emulador, explícame claramente por qué.

# 🧩 PLUGINS Y TEMAS

Quiero que la arquitectura permita añadir en el futuro:

* Temas.
* Plugins.
* Nuevas plataformas.
* Nuevos tipos de juegos.
* Nuevos sistemas de metadatos.
* Nuevas funciones.

No hace falta crear muchos plugins ahora, pero quiero que el proyecto esté preparado para crecer.

# 🔐 SEGURIDAD Y ESTABILIDAD

Quiero que:

* No se borren archivos originales al eliminar juegos de la biblioteca.
* Las operaciones peligrosas pidan confirmación.
* La configuración tenga backups.
* Los errores no hagan que se cierre todo el launcher.
* Los cambios importantes se guarden correctamente.
* Se validen las rutas antes de utilizarlas.

# 🧠 FORMA DE TRABAJAR

Como no sé programar:

1. Antes de empezar analiza el proyecto.
2. Comprueba qué herramientas tengo instaladas.
3. Recomienda la tecnología más adecuada.
4. Explícame brevemente por qué la eliges.
5. Propón una arquitectura.
6. No crees cientos de archivos de golpe.
7. Empieza por una versión mínima pero funcional.
8. Después añade funciones por fases.
9. Ejecuta y prueba el programa durante el desarrollo.
10. Si encuentras errores, corrígelos y vuelve a probar.
11. No rompas funciones que ya funcionen.
12. Mantén el código organizado y fácil de ampliar.
13. Explícame los pasos importantes con palabras sencillas.
14. Dime claramente cuándo necesito hacer algo yo.
15. Antes de realizar cambios grandes, explícame brevemente qué vas a cambiar.

Quiero que el resultado final sea **mi propia consola portable para PC dentro de un USB**, con una interfaz bonita tipo consola, gestión completa de juegos y emuladores, configuración desde la propia aplicación y posibilidad de ampliar el proyecto en el futuro.

**Empieza analizando el proyecto, las tecnologías disponibles en mi PC y proponiendo la arquitectura. No empieces todavía creando todo el proyecto.**
