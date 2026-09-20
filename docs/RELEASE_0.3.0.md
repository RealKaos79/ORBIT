# ORBIT v0.3.0 — Perfiles completos

Esta versión convierte los perfiles en espacios realmente independientes dentro del mismo launcher, manteniendo compartidos los archivos físicos de juegos y emuladores para no duplicar almacenamiento.

## Cambios principales

- Biblioteca, emuladores, historial, colecciones, estadísticas y configuración personal separados por perfil.
- Partidas/backups por perfil mediante el sistema de `save_path` de ORBIT.
- Selector de perfil opcional al arrancar.
- Avatares predeterminados y foto personalizada.
- Atajos de mando para búsqueda y menú rápido.
- Ayuda, tutorial y centro de webs oficiales de emuladores.
- Selector nativo reforzado para modo fullscreen/kiosk.
- Corrección final del guardado de privacidad y confirmación de cierre por perfil.

## Verificación

- 76/76 pruebas automáticas.
- Compilación Python correcta.
- Sintaxis JavaScript correcta.
- Todos los JSON de prueba válidos.
- Migración simulada desde v0.2.2 conservando juego, carátula, historial, colecciones y preferencias existentes.
