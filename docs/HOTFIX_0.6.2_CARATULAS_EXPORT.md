# ORBIT 0.6.2 — Hotfix carátulas y exportación

Este hotfix se aplica sobre ORBIT 0.6.2 y conserva la arquitectura e interfaz existentes.

## Carátulas
- Corrige la aplicación de carátulas descargadas desde SteamGridDB.
- `cover` vuelve a resolverse explícitamente a `media/covers`.
- La descarga valida el formato por la firma real del archivo, no solo por la cabecera HTTP.
- Compatibilidad verificada con PNG, JPG/JPEG, WEBP, GIF y AVIF.
- Las carátulas siguen entrando y saliendo correctamente en ORBIT Pack cuando se selecciona contenido multimedia.

## Exportación ORBIT Pack
- El botón Exportar abre un diálogo nativo de Windows para elegir dónde guardar el `.orbitpack`.
- La exportación se ejecuta en segundo plano.
- Se muestra progreso real, bytes procesados y estimación aproximada del tiempo restante.
- El paquete conserva SHA-256 y escritura atómica mediante archivo temporal.

## Validación
- 59 pruebas automáticas superadas.
- Compilación Python correcta.
- Sintaxis JavaScript verificada con Node.
- Smoke test HTTP del trabajo de exportación completado correctamente.
