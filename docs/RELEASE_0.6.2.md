# ORBIT Portable Launcher v0.6.2

Esta versión es una **actualización directa de ORBIT v0.5.0**. Mantiene el launcher, la interfaz, los perfiles, la biblioteca, las estadísticas, Ajustes, Diagnóstico y la arquitectura backend/frontend existentes. ORBIT Admin continúa fuera de la aplicación principal.

## ORBIT Pack v2 ampliado

- Exportación e importación `.orbitpack` por componentes: juegos, emuladores, configuración, partidas, multimedia y otros datos de perfil.
- Exportación de perfil completo en un único paquete.
- Exportación de configuración solamente, sin juegos, ROMs, binarios de emulador ni otros archivos innecesarios.
- Importación parcial: el receptor decide qué componentes aplicar.
- Rutas portables: las rutas del PC origen no se reutilizan; los archivos físicos se ubican en las carpetas automáticas del ORBIT receptor.
- Fusión de perfiles sin sustituir por defecto el perfil existente. También puede crearse un perfil nuevo con nombre único.
- Detección de duplicados y políticas seguras: conservar/omitir, actualizar metadatos o mantener ambos.
- Conservación de asociaciones juego → emulador. Si existe un emulador compatible y disponible en el receptor, se reutiliza.
- Punto de recuperación automático antes de importar y rollback de metadatos/archivos creados si la importación falla.
- SHA-256 para el manifiesto y todos los payloads. Se rechazan archivos sin firma o modificados.
- Compatibilidad mantenida con ORBIT Pack v1 y con el contrato v2 de ORBIT 0.5.0.

## Credenciales y SteamGridDB

- La clave personal de SteamGridDB se guarda en `data/.secrets/` y ya no forma parte de `settings.json`.
- La clave no se incluye en `.orbitpack`, puntos de recuperación ni JSON de configuración exportados.
- La migración limpia claves heredadas de settings y backups JSON antiguos.
- Se admiten carátulas PNG, JPG/JPEG, WEBP, GIF y AVIF en selección, validación, almacenamiento y servicio local.
- Las miniaturas de SteamGridDB están permitidas por la política CSP únicamente para los hosts de SteamGridDB; las imágenes aplicadas se descargan y validan en backend.

## ORBIT AI

- Motor offline mejorado con normalización de acentos, puntuación y variaciones de lenguaje natural.
- Preguntas como `que emulador necesito` ya no dependen de signos de interrogación ni frases exactas.
- Soporte opcional para LLM local mediante Ollama o endpoint OpenAI-compatible en `localhost/127.0.0.1`.
- Si el modelo local no está configurado o no responde, ORBIT vuelve al motor offline integrado.
- Búsqueda online separada y opcional. Solo se utiliza cuando está activada y la petición solicita explícitamente Internet/web.
- La falta de conexión no rompe ORBIT AI.

## Mando y navegación

- Nuevo cálculo de foco mediante la posición visual real de cada elemento.
- Arriba/abajo priorizan elementos de la misma columna visual; izquierda/derecha, de la misma fila.
- El foco se conserva mediante `scrollIntoView` en estanterías, carruseles y listas desplazables.
- Joystick derecho como puntero de emergencia. Al aceptar sobre un elemento, ese elemento recibe foco, el puntero se desactiva y continúa la navegación normal.
- Detección automática PlayStation / Xbox / Nintendo y leyendas dinámicas en la barra inferior.
- En Nintendo, el mapeo estándar adapta A/B sin modificar remapeos personalizados.
- El cambio ratón ↔ mando sigue siendo inmediato; al volver al ratón reaparecen su cursor y comportamiento normales.

## Aplicación, backend y selector de Windows

- Se conserva el backend local real de juegos y lanzamientos. Añadir un juego persiste en backend y lanzar utiliza su asociación con el emulador.
- Los selectores de juego/ROM usan el selector nativo de Windows con filtro de formatos habituales.
- ORBIT se abre en Edge/Chrome en modo aplicación/kiosk. En Windows ya no degrada silenciosamente a una pestaña web normal.
- El servidor continúa limitado a `127.0.0.1` y la UI continúa accediendo al sistema mediante `/api/...`.

## Pruebas de la actualización

La entrega v0.6.2 incluye **53 pruebas automáticas**: 29 pruebas de regresión de v0.5.0 y 24 pruebas específicas de v0.6.2. Cubren perfiles, juegos, emuladores, asociaciones, ORBIT Pack, integridad SHA-256, importación parcial, rutas receptoras, recuperación, credenciales, GIF/AVIF, IA offline, LLM local, búsqueda online y navegación JavaScript con Node.

Antes del empaquetado se comprueba además:

- `python -m unittest -v tests.test_v050 tests.test_v062`
- `python -m compileall -q app launcher.py`
- `node --check app/static/navigation.js`
- `node --check app/static/app.js`
- smoke test HTTP del servidor local
- reextracción del ZIP final y repetición de pruebas/sintaxis sobre la copia empaquetada
