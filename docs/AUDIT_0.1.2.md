# Auditoría ORBIT v0.1.2

Fecha: 2026-09-06

## Alcance

Revisión de todo el código ejecutable actual: arranque, rutas portables, almacenamiento JSON, servidor local, biblioteca, escaneo, lanzamiento, emuladores, detección del sistema, selectores nativos, JavaScript, HTML/CSS y scripts de preparación para Windows.

## Correcciones principales

1. Sustituido tkinter en Windows por selectores nativos de PowerShell/System.Windows.Forms, compatible con Python embebido.
2. Bloqueado traversal en tokens `@launcher/`.
3. Bloqueado traversal en `/media`.
4. Rutas relativas normales resueltas desde LauncherRoot, no desde el directorio de trabajo accidental.
5. Escritura JSON reforzada con flush/fsync, reemplazo atómico y backups.
6. Recuperación desde backup ante JSON principal corrupto.
7. Fallos de poda de backups ya no convierten un guardado correcto en un error.
8. Read-modify-write de biblioteca protegido con RLock de transacción.
9. Corregida devolución incorrecta al añadir una carpeta ya existente.
10. Las plataformas desconocidas ya no activan un escaneo indiscriminado.
11. Añadidos alias/canonización de plataformas.
12. Asignación automática de emulador disponible por plataforma.
13. Eliminar un emulador limpia referencias huérfanas sin tocar archivos originales.
14. ROM sin emulador disponible ya no se marca como ejecutable.
15. Los demos se retiran al crear biblioteca real y no contaminan estadísticas.
16. Preferencia de fullscreen aplicada al inicio.
17. Estáticos marcados no-store para evitar usar JS viejo tras un hotfix.
18. API limitada a loopback y validación de Host contra DNS rebinding.
19. API de escritura exige application/json y limita el cuerpo a 1 MiB.
20. Endpoints API inexistentes devuelven JSON 404 en lugar del index HTML.
21. Soporte de lanzamiento de accesos directos `.lnk` y scripts `.bat/.cmd` en Windows.
22. Estado de gamepad limpiado al desconectar el mando.
23. Botones de lanzamiento desactivados cuando un juego no está disponible.
24. Una sola instancia ORBIT por USB mediante bloqueo del sistema operativo; una segunda ejecución reabre la existente.
25. Runtime portable por arquitectura y descarga verificada mediante SHA-256.
26. Detección GPU/RAM cacheada para evitar consultas pesadas repetidas.

## Pruebas

- `python3 -m compileall -q .`: correcto.
- `node --check app/static/app.js`: correcto.
- `python3 -m unittest discover -s tests -v`: 33/33 correctas.
- Comprobación estática de IDs de la UI: no hay selectores estáticos rotos.
- Búsqueda de rutas locales del entorno de desarrollo: no se encontraron rutas incrustadas.

## Limitaciones conocidas de esta etapa

- No se puede validar aquí visualmente el diálogo nativo de Windows ni el modo app de Edge/Chrome porque el entorno de desarrollo actual no es Windows. El camino de código de Windows está cubierto por pruebas simuladas.
- El tiempo jugado depende de poder seguir el proceso lanzado. Algunos emuladores/juegos que crean otro proceso y terminan el inicial pueden producir tiempos incompletos. Esto requiere una estrategia de monitorización más avanzada en una fase posterior.
- Los accesos directos `.lnk` se pueden abrir, pero Windows no devuelve directamente el proceso final, por lo que en esta versión no se puede medir su tiempo de juego con precisión.
- La edición completa de juegos/emuladores, carátulas, backups de partidas y plugins/temas avanzados siguen siendo fases futuras, no fallos de v0.1.2.
