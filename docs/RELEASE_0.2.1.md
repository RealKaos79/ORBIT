# ORBIT v0.2.1 — Asistente, temas y modos de interfaz

## Objetivo

Hacer que configurar la biblioteca sea comprensible sin conocimientos técnicos y separar por completo el **tema visual** de la **distribución de interfaz**.

## Asistente de configuración

`⚡ Configurar` y `＋ Añadir juego` abren un asistente con accesos a:

- Juego de PC.
- ROM / juego emulado.
- Carpeta completa para escaneo.
- Emulador.
- Importación local de Steam.
- Detección de EXE/accesos directos en una carpeta.

Los formularios rápidos no sustituyen el editor avanzado; el usuario puede completar después carátulas, fondos, etiquetas, saves y argumentos.

## Temas

14 presets: Dark, Light, OLED, Neon, Cyber, Ocean, Forest, Sunset, Violet, Retro, Amber, Ice, Rose y Midnight. El color de acento sigue siendo editable.

## Modos

6 layouts independientes del tema:

- Classic.
- Top navigation.
- Compact.
- Cinematic.
- Handheld.
- Couch / Controller.

El modo Couch recoloca la navegación en una barra inferior grande y aumenta el feedback de foco para mando.

## Compatibilidad

Los ajustes nuevos (`interface_mode` y `setup_complete`) se añaden mediante migración de settings. Los datos de v0.1/v0.2.0 se conservan.

## Validación

- 56/56 tests unitarios/integración.
- `node --check app/static/app.js` correcto.
- `python -m compileall` correcto.
- Smoke visual sin errores JavaScript para los 6 modos en Chromium con fixtures locales.
- Comprobación visual de 14 tarjetas de tema, 6 tarjetas de modo y 6 opciones del asistente.
