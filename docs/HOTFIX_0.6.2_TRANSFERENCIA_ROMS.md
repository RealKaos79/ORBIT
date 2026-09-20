# ORBIT 0.6.2 — Corrección puntual de transferencia de ROMs

**Esta entrega actualiza el ORBIT 0.6.2 HOTFIX IMPORTACIÓN/PERFILES existente.** No es una aplicación nueva, no incorpora datos de usuario y no cambia el diseño general.

## Causa comprobada

El selector de exportación incluía por defecto «Juegos y metadatos» pero tenía desmarcado «Archivos físicos de los juegos / ROMs». El `.orbitpack` podía contener la ficha del juego sin su ROM: al importarlo, la biblioteca mostraba un elemento sin archivo ejecutable. Además, al importar de nuevo un paquete completo, los duplicados se omitían incluso cuando la ficha existente no tenía ROM.

## Corrección acotada

- El selector de exportación marca por defecto los archivos físicos de los juegos; se puede desmarcar explícitamente para exportar únicamente metadatos.
- Exportar ROMs físicas con un archivo original ausente se detiene con el nombre del juego afectado, en lugar de presentar una exportación incompleta como correcta.
- El backend de exportación incluye ROMs por defecto también si la petición omite el parámetro (las peticiones que lo desactivan expresamente siguen siendo compatibles).
- La inspección muestra cuántas ROMs contiene el paquete y avisa si faltan archivos de juegos. Los enlaces externos de Steam que no se distribuyen como ROM no se cuentan como archivos faltantes.
- La importación copia ROMs reales a las **carpetas automáticas ya configuradas** y guarda la nueva ruta portable. No modifica la organización de ORBIT.
- Si una ficha existente es un duplicado, pero carece de ROM, puede repararse importando un paquete completo sin perder su ID ni crear una segunda ficha.
- Los archivos ya existentes con idéntico SHA-256 se reutilizan; los distintos nunca se sobrescriben. En caso de fallo a mitad se restauran metadatos y se eliminan únicamente las copias nuevas de la operación fallida.
- El progreso sigue mostrando porcentaje/ETA y ahora identifica la ROM por su nombre de archivo original.
- Se conservan las carátulas, los perfiles, el resto de contenidos seleccionables y los paquetes antiguos. El archivo original debe seguir disponible para generar un **nuevo** paquete con ROMs: no se pueden recuperar bytes ausentes de un archivo antiguo que solo contenía metadatos.

## Instalar sin perder datos

1. Cierra ORBIT totalmente.
2. Haz una copia de seguridad de la carpeta de tu instalación existente.
3. Descomprime el ZIP sobre esa **misma** carpeta y acepta reemplazar los archivos de programa.
4. No borres ni reemplaces por carpetas vacías `data/`, `media/`, `games/`, `emulators/`, `saves/`, `backups/` o `runtime/`.
5. En el ORBIT que conserva los juegos, vuelve a exportar un `.orbitpack` nuevo comprobando que **«Archivos físicos de los juegos / ROMs» está marcado**. Importa ese nuevo paquete en el ORBIT receptor.

## Limitaciones

Un `.orbitpack` anterior sin archivos ROM únicamente puede importar sus metadatos, no reconstruir datos que nunca se incluyeron. La ejecución real de emuladores y el explorador nativo deben comprobarse en un equipo Windows con los emuladores y archivos originales del usuario; las pruebas automáticas verifican copia de bytes, reinicio, asociaciones, lanzamiento local de prueba y endpoints HTTP.
