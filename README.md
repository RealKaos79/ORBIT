# ORBIT Portable Launcher v0.6.2

**Actualización directa de ORBIT 0.5.0: transferencia portable, IA local y navegación avanzada con mando.**

## Novedades principales

### Hotfix transferencia de ROMs (septiembre de 2026)

- La exportación de juegos incluye sus **archivos físicos / ROMs** por defecto; la exportación de solo metadatos sigue siendo opcional.
- Si falta una ROM, la exportación avisa del juego y no crea un paquete engañosamente completo.
- Al inspeccionar un `.orbitpack`, ORBIT muestra el número de ROMs y avisa si faltan.
- La importación respeta las carpetas automáticas, evita sobrescribir otras ROMs y permite completar una ficha que antes se había importado sin archivo físico.
- No modifica ni distribuye ROMs existentes de tu instalación; para recuperar archivos de un paquete antiguo sin ROMs debes volver a exportar desde el ORBIT que los conserva.
- **119 pruebas automáticas** en este hotfix (99 de regresión + 20 de transferencia ROM); también se comprueban los endpoints reales HTTP, reinicio, compilación Python y sintaxis JavaScript.
- Las instrucciones están en `ACTUALIZAR_HOTFIX_0.6.2_TRANSFERENCIA_ROMS.txt`.


## Hotfix de importación y edición de perfiles (septiembre de 2026)

- **Importar ORBIT Pack reparado:** selector de archivo de la interfaz y alternativa de selector nativo Windows, comprobación SHA-256 y selección parcial por contenido; usa las carpetas automáticas de ORBIT que ya tenías configuradas.
- **Importación en segundo plano:** porcentaje real de verificación, descompresión y copia, nombre del archivo y tiempo restante estimado. Los packs antiguos v2 siguen siendo compatibles.
- **Juegos sin ROM en el paquete:** su ficha ya no desaparece silenciosamente; se incorpora a la biblioteca como no disponible, enlazando un ROM que ya exista en la carpeta automática si coincide su nombre.
- **Partidas duplicadas:** no se pisan; se importan a una carpeta diferenciada y ORBIT informa de la ubicación.
- **Editar perfiles existentes en Ajustes:** nombre, avatar ORBIT, foto desde archivo y color identificativo. Las fotos se guardan dentro de ORBIT; renombrar un perfil no borra su avatar ni juegos.
- **Datos protegidos:** el archivo de actualización no incluye directorios de usuario; no borres `data/`, `media/`, `games/`, `emulators/`, `saves/`, `backups/` o `runtime/`.

Consulta `docs/HOTFIX_0.6.2_IMPORTACION_PERFILES.md` y `ACTUALIZAR_HOTFIX_0.6.2_IMPORTACION_PERFILES.txt`.


- **Actualización sobre ORBIT 0.5.0**: se conserva la aplicación, su interfaz y arquitectura; no es un proyecto paralelo ni una reimplementación.
- **ORBIT Pack v2 ampliado**: exportación/importación parcial por componentes, perfil completo, configuración solamente, fusión de perfiles, rutas receptoras, duplicados, asociaciones juego-emulador, SHA-256 y recuperación/rollback.
- **Credenciales fuera de JSON**: SteamGridDB se guarda en `data/.secrets/` y nunca se exporta ni se incluye en recuperación.
- **Carátulas ampliadas y persistentes**: detección por contenido real para PNG, JPG/JPEG/JFIF, WEBP, GIF, AVIF, BMP e ICO; TIFF se convierte a PNG cuando hay decodificador local. Las referencias antiguas se migran sin borrar los originales.
- **ORBIT AI offline mejorada**: comprensión flexible de lenguaje natural, LLM local opcional y búsqueda online opcional e independiente.
- **Mando por posición visual**: navegación espacial corregida, mejor soporte de scroll, puntero con joystick derecho y detección PlayStation/Xbox/Nintendo.
- **Modo aplicación reforzado**: en Windows ORBIT se mantiene como aplicación/kiosk de Edge/Chrome y no degrada a una pestaña normal.
- **99 pruebas automáticas** en el hotfix de importación/perfiles; incluye las 77 pruebas de regresión previas, compatibilidad de carátulas, importación HTTP y reinicios del backend.

### Funciones heredadas y mantenidas de 0.5.0

- **ORBIT Pack v2**: el equipo receptor decide dónde colocar cada consola; incluye comprobación SHA-256, detección de duplicados, reutilización de emuladores portables y opción de incluir partidas. Las partidas existentes nunca se sobrescriben silenciosamente. Si una importación falla, ORBIT revierte los cambios realizados por esa importación.
- **Organización por consola y perfil**: configura carpetas de destino dentro de ORBIT para GameCube, PS2, Switch y el resto de plataformas.
- **Rendimiento por juego**: estimación cualitativa (Excelente / Muy bueno / Aceptable / Puede tener problemas / No recomendado / Sin datos) basada en el PC actual. ORBIT no inventa FPS.
- **Firmware / BIOS / keys**: ORBIT avisa cuando una plataforma necesita archivos de sistema y comprueba si los has añadido. ORBIT no descarga ni distribuye firmware, BIOS o keys propietarios.
- **Temas personalizados**: creador visual con tamaño, forma, separación, sombras, animaciones y colores, sin introducir valores en píxeles. Exportación/importación `.orbittheme`.
- **ORBIT AI offline**: se conserva el motor local determinista de v0.5 para buscar en biblioteca, revisar estado, recomendar y recordar preferencias; v0.6.2 añade comprensión flexible y un LLM local opcional sin convertir Internet en dependencia.
- **Carátulas online opcionales**: búsqueda mediante SteamGridDB usando la clave API personal del usuario. ORBIT funciona normalmente sin Internet y sin esa clave.
- **Modo seguro**: `ORBIT_Modo_Seguro.bat` inicia con tema oscuro, interfaz clásica, animaciones reducidas y Ajustes como pantalla inicial, sin modificar los ajustes guardados.
- **ORBIT Admin retirado**: v0.5 elimina el sistema de autorización/bloqueo y el antiguo modo privacidad por PC. Al actualizar desde v0.4.1 se limpian únicamente sus archivos conocidos; juegos, saves, perfiles, media y emuladores se conservan.

## Actualizar desde v0.4.1

1. Cierra ORBIT.
2. Copia el contenido del ZIP **ACTUALIZACION_DESDE_v0.4.1** encima de tu carpeta ORBIT actual y acepta reemplazar los archivos.
3. Inicia `launcher.bat`. En el primer arranque v0.5 retirará automáticamente los restos conocidos de ORBIT Admin.
4. No borres `data/`, `games/`, `emulators/`, `saves/`, `media/`, `backups/` ni `runtime/`. El ZIP de actualización no contiene esas carpetas.

La versión completa sirve para una instalación nueva. `Preparar_USB.bat` sigue preparando el runtime Python portable cuando el equipo lo necesita.

Consulta `docs/RELEASE_0.6.2.md` para el detalle y las pruebas de esta versión.

---

# ORBIT Portable Console Launcher

ORBIT es un launcher de juegos portable para Windows pensado para vivir en un USB y ofrecer una interfaz tipo consola.

## Funciones base incluidas

Esta primera versión funcional incluye:

- Interfaz tipo consola responsive con 14 temas y 6 modos de distribución combinables.
- Inicio, Biblioteca, Estadísticas, Ajustes y Diagnóstico.
- Navegación por teclado, ratón y Gamepad API.
- Soporte básico de mando con cruceta/stick, A para seleccionar y B para volver.
- Biblioteca con favoritos, recientes, búsqueda, filtros y ordenación.
- Asistente guiado para añadir juegos de PC, ROMs, carpetas completas, Steam y emuladores sin editar archivos.
- Configuración de emuladores con argumentos `{rom}`.
- Carpetas de juegos y escaneo de biblioteca.
- Lanzamiento real de ejecutables y de juegos mediante emuladores configurados.
- Conteo de lanzamientos y tiempo jugado mientras el proceso pueda monitorizarse.
- Diagnóstico de rutas, emuladores, juegos no disponibles y hardware básico.
- Detección de sistema operativo, CPU, GPU, RAM y espacio libre.
- Almacenamiento portable en JSON con escrituras atómicas y backups rotativos.
- Rutas internas guardadas como `@launcher/...`, nunca ligadas a D:, E:, F:, etc.
- Los juegos se eliminan únicamente de la biblioteca; el archivo original no se borra.
- Carátulas personalizadas manuales: añadir, cambiar y quitar desde los detalles del juego.
- Las carátulas seleccionadas se copian a `media/covers/` para mantener la portabilidad; la imagen original nunca se modifica ni se borra.

## Cómo ejecutarlo en Windows

### Opción recomendada: USB completamente portable

1. Copia toda la carpeta ORBIT al USB.
2. En un PC Windows compatible (x64, ARM64 o x86) con Internet, ejecuta **`Preparar_USB.bat`** una sola vez.
3. El script descargará a `runtime/` la distribución embebida oficial de Python.
4. Después podrás ejecutar **`launcher.bat`** incluso en PCs sin Python instalado.

La preparación del runtime se realiza una sola vez. El runtime se queda dentro del USB.

### Durante desarrollo

Si el PC ya tiene Python 3 instalado, `launcher.bat` también puede utilizarlo como alternativa.

## Estructura portable

```text
ORBIT/
├─ app/            Código del launcher
├─ data/           Biblioteca, ajustes, emuladores e historial
├─ games/          Juegos opcionales dentro del USB
├─ emulators/      Emuladores opcionales dentro del USB
├─ media/covers/   Carátulas
├─ saves/          Partidas que el usuario decida centralizar
├─ backups/        Backups de configuración y, en futuras versiones, partidas
├─ plugins/        Preparado para plugins futuros
├─ themes/         Preparado para temas futuros
├─ runtime/        Python embebido de Windows
├─ launcher.bat    Inicio normal en Windows
└─ Preparar_USB.bat Preparación única del runtime portable
```


## Cómo añadir juegos sin complicarte

Pulsa **⚡ Configurar** o **＋ Añadir juego**. ORBIT abre ahora un asistente con seis caminos:

1. **Juego de PC**: selecciona el `.exe`; el nombre es opcional.
2. **Juego emulado / ROM**: selecciona la ROM, la consola y el emulador.
3. **Carpeta completa**: elige una carpeta y una plataforma; después pulsa Actualizar biblioteca.
4. **Configurar emulador**: selecciona el ejecutable del emulador y la consola que utiliza.
5. **Importar Steam**: busca instalaciones locales de Steam.
6. **Detectar juegos de PC**: analiza una carpeta en busca de `.exe` y accesos directos.

Para emulación, el orden recomendado es **Emulador → Carpeta de ROMs → Actualizar biblioteca**. Si es el primer emulador válido de esa plataforma, ORBIT puede asociarlo automáticamente a los juegos detectados.

## Temas y modos de interfaz

Los **temas** cambian colores, superficies y atmósfera. Los **modos** cambian la colocación física de la interfaz. Son independientes: cualquier tema puede usarse con cualquier modo.

- **Clásico**: navegación vertical a la izquierda.
- **Barra superior**: navegación horizontal arriba y mayor anchura útil.
- **Compacto**: muestra más juegos simultáneamente.
- **Cinemático**: héroe y carátulas más grandes.
- **Portátil**: densidad y tamaños pensados para pantallas pequeñas/16:10.
- **Sofá / Mando**: navegación grande en la parte inferior, tarjetas amplias y foco reforzado para cruceta/stick.

## Rutas

Las rutas ubicadas dentro de la carpeta del launcher se almacenan así:

```text
@launcher/games/MiJuego/game.exe
```

Al arrancar, ORBIT resuelve `@launcher/` contra su ubicación actual. Si el USB cambia de `D:` a `F:`, la biblioteca sigue apuntando al mismo archivo.

Las rutas que realmente están fuera del USB pueden guardarse como absolutas porque pertenecen al PC anfitrión.

## Navegación

- Flechas: mover selección.
- Enter / Espacio: seleccionar.
- Escape / Backspace: volver.
- Mando: cruceta/stick para navegar, A seleccionar, B volver.
- Botón ⛶: pantalla completa del navegador.
- “Iniciar en pantalla completa” usa modo kiosk fullscreen de Edge/Chrome al próximo arranque.
- Para evitar lag en USB, el perfil/caché técnica del navegador se guarda temporalmente en Windows; los datos reales de ORBIT continúan en el USB.

## Notas de esta versión

La interfaz se sirve localmente desde `127.0.0.1` y se abre preferentemente en Microsoft Edge o Chrome en modo aplicación. El servidor solo escucha en la máquina local, valida el Host local y limita las operaciones de escritura a peticiones JSON. ORBIT mantiene una sola instancia activa por USB.

No se usan paquetes de terceros en tiempo de ejecución; la aplicación utiliza la biblioteca estándar de Python y las funciones HTML/CSS/JavaScript del navegador.

## Pruebas

Desde la raíz del proyecto:

```bash
python -m unittest discover -s tests -v
```

También se puede comprobar la sintaxis del JavaScript con:

```bash
node --check app/static/app.js
```

## Funciones principales de v0.2.0

- Edición completa de juegos con nombre, plataforma, descripción, género, año, jugadores, etiquetas, estado, rutas, emulador y argumentos propios.
- Estados Pendiente / Jugando / Completado, favoritos, ocultos, colecciones personalizadas y colecciones inteligentes.
- Botón de juego aleatorio y filtros avanzados.
- Carátula, fondo, logo y capturas personalizadas gestionadas dentro del USB.
- Emuladores editables y predeterminados por plataforma, con prueba de ejecutable.
- Importación local de Steam y de carpetas con EXE/accesos directos.
- Backups manuales y automáticos de partidas, restauración con backup de seguridad y sincronización PC ↔ USB.
- Perfiles básicos de usuario y perfiles de mando con remapeo y deadzone.
- 14 temas: Oscuro, Claro, OLED, Neon, Cyber, Océano, Bosque, Atardecer, Violeta, Retro, Ámbar, Hielo, Rose y Medianoche.
- 6 modos de interfaz compatibles con todos los temas: Clásico, Barra superior, Compacto, Cinemático, Portátil y Sofá/Mando.
- Color principal, escala de interfaz y reducción de animaciones.
- Estadísticas ampliadas, historial de sesiones y procesos de juego activos.
- Diagnóstico y desglose de almacenamiento bajo demanda para mantener un arranque rápido.
- Compatibilidad automática con los JSON y configuración de v0.1.x.

## Integraciones externas

La arquitectura y la configuración quedan preparadas para RetroAchievements, Discord Rich Presence, actualizaciones online y plugins. Estas integraciones no se activan automáticamente porque necesitan servicios externos, credenciales, una fuente de actualización confiable o soporte específico de cada emulador. ORBIT no simula una integración externa que no pueda validar de forma segura.

## Próximas fases

- Integraciones externas opcionales con credenciales del usuario.
- Save states por emulador cuando exista soporte documentado.
- Teclado virtual avanzado para modo TV.
- Temas/plugins instalables firmados y actualizador con manifiesto verificado.



## v0.2.1 — Asistente, 14 temas y 6 modos

- Nuevo asistente de configuración accesible desde **⚡ Configurar** y **＋ Añadir juego**.
- Flujo rápido para juegos de PC: basta con elegir el ejecutable.
- Flujo rápido para ROMs con plataforma y emulador.
- Selectores de plataforma en carpetas y emuladores para evitar nombres incorrectos.
- 14 temas visuales y color principal personalizable.
- 6 distribuciones completas compatibles con todos los temas.
- Nuevo modo **Sofá / Mando** con navegación inferior, elementos grandes y foco reforzado.
- Pruebas de regresión ampliadas a 56 tests, más smoke visual de los seis modos y del asistente.

## v0.2.0 — Biblioteca avanzada, partidas y personalización

- Edición completa de la biblioteca y metadatos locales.
- Colecciones, estados, etiquetas, ocultos y filtros inteligentes.
- Multimedia por juego: carátula, fondo, logo y capturas.
- Emuladores predeterminados por plataforma y argumentos por juego.
- Importación de Steam y carpetas locales.
- Backups/restauración de saves y sincronización PC ↔ USB.
- Perfiles, remapeo básico de mando, nuevos temas y opciones de interfaz.
- Estadísticas, historial, sesiones activas, almacenamiento e integridad ampliada.
- Migración compatible desde v0.1.x.
- 52 pruebas automáticas de regresión y funciones v0.2 superadas antes del empaquetado.


## v0.1.1

- Corregido un cierre accidental del servidor local cuando Edge/Chrome delegaba la ventana a otro proceso.
- Añadido botón Salir (⏻) para cerrar ORBIT y su servidor local correctamente.


## v0.1.2 — Auditoría completa de estabilidad

Esta versión incluye una revisión transversal de rutas, persistencia, servidor, biblioteca, emuladores, interfaz y scripts de Windows. Entre las correcciones más importantes:

- Selector nativo de archivos de Windows sin depender de tkinter/Tcl-Tk.
- Protección contra traversal tanto en rutas `@launcher/` como en `/media`.
- Bloqueo de una sola instancia de ORBIT por USB y reapertura de la instancia existente.
- Operaciones de biblioteca protegidas como transacciones para evitar pérdida de cambios concurrentes.
- Validación de Host local, cuerpo JSON y tamaño de peticiones en la API.
- Archivos estáticos sin caché para que los hotfix se apliquen inmediatamente.
- Rutas relativas resueltas siempre desde la raíz del launcher.
- Datos de demostración retirados automáticamente al añadir la biblioteca real y excluidos de estadísticas reales.
- Plataformas normalizadas y escaneo seguro; una plataforma desconocida ya no escanea todas las extensiones.
- Asociación automática de emuladores por plataforma y limpieza de referencias al eliminar un emulador.
- Juegos sin emulador/ruta válida ya no aparecen como listos para jugar.
- Preferencia de inicio en pantalla completa aplicada realmente al arrancar.
- Runtime embebido preparado por arquitectura y validado mediante SHA-256.
- Escrituras JSON atómicas con `fsync` y recuperación desde backups.

Pruebas automáticas de esta versión: **33/33 correctas**, además de compilación Python y comprobación de sintaxis JavaScript.


## v0.1.3 — Carátulas personalizadas

- Añadidos botones **Añadir carátula / Cambiar carátula** en los detalles de cada juego real.
- Añadido botón **Quitar carátula** cuando un juego ya tiene una personalizada.
- Selector nativo de Windows para elegir PNG, JPG/JPEG o WEBP.
- ORBIT copia la imagen elegida a `media/covers/` y guarda una ruta `@launcher/...`, por lo que la carátula sigue funcionando aunque cambie la letra del USB.
- Al sustituir o quitar una carátula, ORBIT solo elimina su copia gestionada; nunca borra la imagen original elegida por el usuario.
- Validación básica de firma de imagen y límite de 25 MB por carátula.
- Las carátulas sustituyen visualmente a las iniciales de marcador de posición en biblioteca y detalles.

Pruebas automáticas de esta versión: **40/40 correctas**, además de compilación Python y comprobación de sintaxis JavaScript.


## v0.1.4 - Conectividad

- `launcher.bat` usa `pythonw.exe` cuando el runtime portable lo incluye, por lo que ORBIT ya no depende de mantener abierta una consola negra.
- `launcher_debug.bat` abre ORBIT con consola para diagnosticar problemas.
- Los errores internos se registran en `data/logs/orbit.log` con rotación automática.
- El frontend distingue una desconexión real del servidor de un error HTTP y reintenta operaciones seguras.
- Los cambios de Ajustes (por ejemplo, tema) realizan un reintento seguro si hay un corte transitorio.



## v0.3.0 — Perfiles completos, ayuda y mando

- Perfiles realmente independientes: biblioteca, emuladores, favoritos, historial, estadísticas, colecciones, temas, ajustes de mando y configuración personal.
- Partidas, backups y sincronización separados por perfil cuando se configura `save_path`, sin duplicar los juegos/ROMs físicos compartidos.
- Selector opcional **¿Quién está jugando?** al iniciar ORBIT.
- Avatares predeterminados y foto personalizada de perfil copiada de forma portable al USB.
- Cambio de perfil bloqueado mientras hay un juego/emulador activo para evitar mezclar partidas.
- Atajos de mando configurables: Triángulo/Y para búsqueda, Cuadrado/X para menú rápido y L1/LB para favorito.
- Nueva pestaña Ayuda y tutorial desde Ajustes.
- Centro de emuladores con enlaces oficiales verificados y plataforma indicada; Kega Fusion se marca como legado cuando no existe una web oficial activa verificable.
- Selector de archivos/carpetas reforzado para fullscreen/kiosk con owner TopMost y recuperación posterior de pantalla completa.
- Eliminada la duplicidad del antiguo botón Configurar: Añadir juego y Centro de emuladores tienen funciones diferenciadas.
- Privacidad, confirmación de cierre y resto de preferencias de experiencia quedan correctamente aisladas por perfil.
- Migración compatible desde v0.2.2 conservando la biblioteca existente del perfil Principal.

Pruebas automáticas de esta versión: **76/76 correctas**, más compilación Python, validación de JavaScript, JSON e integridad de migración.

## v0.2.2 — Privacidad y acabado de aplicación

- Nuevo icono ORBIT y manifest de aplicación.
- Modo privacidad/streaming activado por defecto.
- Confirmación configurable al cerrar juegos/emuladores.
- Selectores de archivo/carpeta reforzados para aparecer delante de ORBIT.
- Logs normales sin IP local ni rutas completas sensibles.
- Script opcional `Crear_acceso_directo_ORBIT.bat` para crear un acceso directo con el icono ORBIT.

## v0.4.0 — Switch, mando, ORBIT Pack y ORBIT Admin (histórico)

- Nintendo Switch como plataforma de biblioteca/escaneo y Eden como emulador configurable desde su proyecto oficial.
- Centro de emuladores con instalación masiva segura cuando existe ZIP Windows verificable y registro automático por plataforma.
- Mesen actualizado a Mesen Community Edition.
- Navegación de mando reconstruida con cambio automático mando/ratón/teclado y tester.
- Exportar/importar `.orbitpack` con SHA-256 y comprobaciones de seguridad.
- Preparar para otro PC, duplicados y puntos de recuperación.
- Esta versión introdujo ORBIT Admin y el bloqueo administrado. **Ambos sistemas están retirados desde v0.5.0** y no forman parte del ORBIT actual.

Consulta `docs/RELEASE_0.4.0.md` para el detalle técnico.

## Hotfix 0.6.2 — carátulas persistentes + exportación selectiva

La revisión actual sustituye la validación antigua por un pipeline único de imagen basado en el **contenido real**: descarga, detección, conversión cuando hace falta, almacenamiento portable, aplicación y recarga posterior. También migra referencias de carátulas heredadas sin borrar sus archivos originales y evita que cambiar la imagen de un juego afecte a otro.

La exportación ORBIT Pack permite seleccionar componentes y **juegos individualmente**, con Seleccionar todo/Deseleccionar todo. La selección parcial se refleja exactamente en el ZIP; configuración solamente no incluye juegos, emuladores, saves ni carátulas. Se conserva el selector nativo de destino y la barra de progreso/ETA del hotfix anterior. Consulta `docs/HOTFIX_0.6.2_CARATULAS_SELECTIVO.md`.
