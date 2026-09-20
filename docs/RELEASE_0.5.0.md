# ORBIT v0.5.0 — Notas de versión

## Qué incorpora

- ORBIT Pack v2 con política `receiver-decides`, destinos por plataforma, integridad SHA-256, compatibilidad de lectura con packs v1, detección de duplicados por nombre/plataforma/región/revisión, reutilización de emuladores y protección de partidas.
- Transacción de importación: un fallo revierte metadatos y elimina únicamente el payload creado por esa importación.
- Metadatos de región, revisión y demanda de rendimiento por juego.
- Estimación cualitativa de rendimiento por juego basada en CPU, RAM y detección disponible de GPU.
- Centro de preparación de firmware/BIOS/keys aportados por el usuario para Switch, 3DS, PlayStation y PlayStation 2.
- Estado general «¿Está listo mi ORBIT?» integrado con diagnóstico, requisitos y portabilidad.
- Temas personalizados por perfil, editor visual y formato `.orbittheme`.
- ORBIT AI offline por perfil para biblioteca/estado/preferencias, sin acceso directo para reescribir o borrar ORBIT.
- Búsqueda opcional de carátulas/fondos/logos mediante SteamGridDB con API key del usuario.
- Modo seguro de arranque.
- Eliminación de ORBIT Admin, autorización remota y modo privacidad por PC.

## Compatibilidad / migración

- Conserva la estructura de datos del perfil Principal y los perfiles adicionales de v0.4.1.
- Conserva `games/`, `emulators/`, `saves/`, `media/`, `backups/` y `runtime/`.
- En el primer arranque elimina solo los restos conocidos del sistema Admin anterior: `authorization_config*.json`, módulos legacy de autorización/privacidad/firma y `data/.orbit-auth`.
- El antiguo `privacy_mode` se elimina de ajustes globales y de perfil.

## Alcance de ORBIT AI en v0.5

ORBIT AI v0.5 es un asistente local y determinista especializado en ORBIT. Puede buscar, filtrar, recomendar, consultar el estado y mantener preferencias separadas por perfil. No incluye todavía un modelo LLM local de varios GB, no se autoentrena y no modifica el código del programa.

## Archivos propietarios

ORBIT puede detectar y organizar firmware, BIOS y keys aportados legalmente por el usuario. No incluye, descarga ni enlaza automáticamente archivos propietarios de consolas.

## Validación

Antes del empaquetado se han ejecutado pruebas de perfiles, migración de privacidad, juegos/metadatos, rendimiento, firmware/keys, temas, ORBIT AI, organización, imágenes, backups/restauración, recovery, ORBIT Pack v1/v2, integridad, path traversal, rollback de importación, API HTTP, Host guard, modo seguro y ausencia de módulos Admin. También se ha ejecutado el JavaScript en Chromium real para los principales flujos visuales. El paquete final se vuelve a validar después de extraerlo.
