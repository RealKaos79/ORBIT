# ORBIT v0.1.6 — Rendimiento de arranque

Este hotfix corrige regresiones de rendimiento observadas tras v0.1.5.

## Cambios

- El perfil temporal de Edge/Chrome deja de residir en el USB. Solo la caché/runtime del navegador se guarda en la carpeta temporal local de Windows.
- Biblioteca, configuración, estadísticas, carátulas, emuladores y demás datos de ORBIT siguen residiendo en el USB.
- El perfil antiguo `data/browser-profile` de v0.1.5 ya no se usa.
- Se incluye `Limpiar_cache_antigua_v015.bat` para eliminar esa caché antigua manualmente y de forma segura con ORBIT cerrado.
- `/api/state` ya no bloquea el arranque esperando la consulta de GPU; la GPU se obtiene al abrir Diagnóstico.
- ORBIT ya no renderiza Biblioteca, Estadísticas y Ajustes mientras esas pantallas están ocultas.
- Las carátulas usan carga diferida (`loading=lazy`) y decodificación asíncrona.
- Las carátulas gestionadas por ORBIT pueden almacenarse en caché del navegador. Un `cover_version` cambia la URL al sustituir una imagen para evitar mostrar una versión antigua.
- Cambiar tema ya no fuerza un render completo de toda la biblioteca.

## Portabilidad

La única información que se guarda temporalmente fuera del USB es la caché/perfil técnico de Edge/Chrome, bajo la carpeta temporal de Windows. No contiene la biblioteca ni la configuración de ORBIT y puede eliminarse sin perder datos del launcher.
