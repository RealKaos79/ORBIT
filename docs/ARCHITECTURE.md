# Arquitectura ORBIT

## Principios

1. El launcher no depende de una letra de unidad.
2. La UI no accede directamente al sistema de archivos.
3. Las operaciones peligrosas se centralizan en servicios de backend.
4. Eliminar una entrada de biblioteca nunca elimina el juego original.
5. Los datos se escriben de forma atómica y conservan backups rotativos.
6. La interfaz se diseña primero para mando y televisión.

## Capas

### `app/static/`
Interfaz de consola HTML/CSS/JavaScript. Se comunica únicamente con `/api/...`.

### `app/server.py`
Servidor HTTP local y API. Expone funciones de biblioteca, ajustes, diagnóstico y diálogos nativos.

### `app/services/library.py`
Reglas de biblioteca: juegos, emuladores, escaneo, lanzamiento, historial y estadísticas.

### `app/services/system_info.py`
Detección del PC y del almacenamiento donde vive ORBIT.

### `app/core/paths.py`
Única autoridad para convertir entre rutas reales y rutas portables `@launcher/...`.

### `app/core/storage.py`
Persistencia JSON, escrituras atómicas, recuperación y backups de configuración.

## Datos

Para esta primera fase se usa JSON deliberadamente: es portable, legible, no necesita dependencias nativas y permite validar la arquitectura. Si la biblioteca crece a decenas de miles de entradas o necesita consultas complejas, la capa `JsonStore` podrá reemplazarse por SQLite sin cambiar la UI.

## Seguridad

El servidor escucha solo en `127.0.0.1`. Las operaciones de borrado actuales eliminan exclusivamente registros de biblioteca/configuración, nunca archivos de juegos o ROMs.


## Extensiones de arquitectura v0.6.2

### `app/services/orbitpack.py`
Gestiona el contenedor `.orbitpack`, manifiesto, SHA-256, validación de miembros y extracción segura. La capa `LibraryService` decide fusión, duplicados, carpetas receptoras y rollback.

### `app/services/secrets.py`
Almacén local de credenciales fuera de los JSON exportables. SteamGridDB se guarda por perfil en `data/.secrets/` y el saneador elimina tokens/secretos de manifiestos y recuperación.

### `app/services/ai_assistant.py` + `ai_runtime.py`
ORBIT AI es offline-first. El motor determinista local permanece siempre disponible. El LLM local es opcional y solo acepta endpoints loopback; la búsqueda online es otro camino explícito y opcional.

### `app/static/navigation.js`
Funciones puras y comprobables para navegación espacial, detección de familia de mando, etiquetas y deadzone. `app.js` las integra con foco, scroll, cambio ratón/mando y puntero del joystick derecho.

### Transacciones de importación
Antes de una importación ORBIT crea un punto de recuperación y toma una instantánea de metadatos. Primero verifica por completo SHA-256, después copia solo componentes seleccionados. Ante una excepción restaura los JSON anteriores y elimina únicamente los archivos físicos creados por esa importación.
