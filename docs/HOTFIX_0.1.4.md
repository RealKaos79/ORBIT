# ORBIT 0.1.4 — Hotfix de conectividad

Este hotfix corrige la experiencia de `Failed to fetch` cuando la interfaz pierde el proceso servidor local.

## Cambios
- Arranque normal con `pythonw.exe` (sin consola negra persistente).
- Nuevo `launcher_debug.bat` para diagnóstico.
- Registro persistente y rotativo en `data/logs/orbit.log`.
- Mensajes de error de conexión comprensibles.
- Reintento de GET y de guardado de Ajustes, que son operaciones seguras/idempotentes.
- Las rutas de API se resuelven explícitamente contra `window.location.origin`.

El hotfix no incluye `data/`, `runtime/`, `media/`, `games/`, `emulators/`, `saves/` ni `backups/`.
