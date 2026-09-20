# ORBIT 0.6.2 — Reparación de importación y gestión de perfiles

Actualización **sobre el mismo proyecto original**. Mantiene la interfaz, backend, formato `.orbitpack` v2, carátulas y exportador existentes.

## Causa de la importación aparentemente inactiva

El flujo anterior dependía del selector nativo y ejecutaba la importación sin progreso visible. Además, si un paquete incluía metadatos de juego sin ROM física, el importador los contaba pero descartaba la entrada, dando la impresión de que no había ocurrido nada.

## Corrección

- Selección estándar de archivos disponible desde la interfaz y alternativa del selector nativo de Windows; transferencia binaria al backend si se usa el selector estándar.
- Inspección y validación SHA-256 previa; selección independiente de juegos, emuladores, configuración, partidas, multimedia y otros datos cuando existan en el paquete; importar al perfil activo o a uno nuevo.
- Trabajador de importación en segundo plano con consulta HTTP de progreso: verificación, extracción, copia a carpetas automáticas existentes, porcentaje, archivo procesado y ETA orientativa; tareas simultáneas de importación bloqueadas para proteger los datos.
- Mantenimiento del esquema `@launcher/` y directorios por plataforma; conservadas las asociaciones con emuladores preexistentes.
- Paquetes de solo metadatos generan ficha no ejecutable en biblioteca (o enlazan el ROM receptor existente); no se finge que una ROM ausente está disponible.
- Las partidas preexistentes nunca se sobrescriben: si hay conflicto se guardan en una carpeta independiente y se muestra su ubicación.
- Previo a cambios se genera punto de recuperación; ante fallo de copia se revierte el estado y se eliminan exclusivamente los archivos nuevos.
- Reutiliza las carpetas automáticas ya existentes, sin crear un segundo sistema ni proyectos paralelos.

## Perfiles

Ajustes → Gestionar perfiles permite editar nombre, avatar predeterminado, foto local y color de identificación incluso después de crear el perfil. La foto pasa por el validador de imágenes y se guarda como ruta portable en `media/profiles/`. Si se elige otra foto, la anterior solo se elimina si ningún otro perfil la usa. Renombrar no afecta a juegos ni ajustes individuales.

## Comprobaciones

99 tests automáticos: 77 de regresión y 22 adicionales (metadatos solos, carpeta personalizada, importación selectiva, integridad, duplicados ZIP, rollback, importación HTTP real, subida de foto HTTP, reinicio, perfiles, avatares compartidos y progreso). Sintaxis JavaScript y compilación Python verificadas. Windows PowerShell y la interfaz visual no se pueden ejecutar físicamente en el entorno de pruebas Linux; el selector estándar y las rutas HTTP se ensayaron a nivel de backend real.

## Instalación

Cerrar ORBIT; recomendar copia de la carpeta; extraer este ZIP ENCIMA del ORBIT existente. Conservar íntegramente `data/`, `media/`, `games/`, `emulators/`, `saves/`, `backups/`, `runtime/`. El ZIP no incluye dichos datos.
