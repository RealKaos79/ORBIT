# ORBIT 0.6.2 — Hotfix carátulas persistentes y exportación selectiva

Esta actualización se aplica directamente sobre ORBIT 0.6.2. No reemplaza la arquitectura, la interfaz ni los datos del usuario.

## Causa del fallo de carátulas

El flujo anterior mezclaba varias validaciones parciales: extensión del archivo, cabecera HTTP/MIME y una lista limitada de firmas. SteamGridDB puede servir una imagen válida desde una URL sin extensión útil o con una cabecera MIME genérica/diferente. La vista previa del navegador podía decodificarla, pero el backend la rechazaba al intentar guardarla. Además, referencias heredadas podían seguir apuntando a archivos externos o a ficheros cuyo sufijo no coincidía con el contenido real.

## Corrección

- Nuevo `app/services/image_pipeline.py` como única ruta de entrada para imágenes.
- El formato se identifica por los bytes reales, no por el nombre del archivo ni por `Content-Type`.
- Se valida una estructura mínima antes de escribir.
- Se escribe de forma atómica y con extensión canónica.
- Formatos seguros para navegador se conservan sin recomprimirlos.
- TIFF se reconoce y se convierte a PNG cuando hay decodificador (Pillow durante desarrollo o fallback nativo de Windows/System.Drawing en la instalación portable).
- SteamGridDB usa exactamente el mismo pipeline que las carátulas locales.
- El fichero temporal descargado nunca se convierte en la referencia definitiva del juego: ORBIT crea primero su copia gestionada en `media/covers/`.

## Conservación y migración

Al iniciar, ORBIT revisa las referencias de carátula/fondo/logo de todos los perfiles:

- Una imagen ya gestionada y correcta se deja intacta, incluso su `mtime`.
- Una imagen externa válida se copia dentro de ORBIT y el original no se borra.
- Si el contenido real no coincide con el sufijo heredado, se crea una copia gestionada con la extensión correcta.
- Si una referencia antigua ya no existe, ORBIT busca una copia gestionada compatible por nombre heredado o ID del juego antes de rendirse.
- Un archivo compartido por dos juegos no se elimina al cambiar la carátula de solo uno.

## Formatos

Directos: PNG, JPG/JPEG/JPE/JFIF, WEBP, GIF, AVIF, BMP e ICO.

Conversión: TIFF/TIF → PNG cuando el equipo dispone de decodificador local.

El selector incluye además “Todos los archivos”; por ello un JPEG llamado `.bin`, por ejemplo, sigue pudiendo aceptarse si su contenido es realmente JPEG.

## Exportación selectiva `.orbitpack`

Ajustes → Importar/Exportar permite elegir:

- Juegos y metadatos.
- Archivos físicos/ROMs de los juegos seleccionados.
- Emuladores.
- Configuración.
- Partidas.
- Carátulas/multimedia.
- Otros datos compatibles.
- Perfil completo.

Cada juego real tiene su casilla individual, más **Seleccionar todo** y **Deseleccionar todo**. Una selección parcial desactiva automáticamente “Perfil completo” para que la interfaz no prometa una cosa y el backend exporte otra.

`game_ids=None` mantiene la compatibilidad histórica (todos los juegos); una lista explícita, incluso vacía, significa selección exacta. El formato `.orbitpack` continúa siendo v2 y la importación de paquetes existentes no cambia.

## Validación

- 76/77 pruebas automáticas.
- Compilación Python correcta.
- Sintaxis JavaScript validada con Node.
- Imágenes completas/decodificables usadas en la suite para PNG, JPEG, WEBP, GIF, BMP y AVIF.
- Prueba de extremo a extremo con imágenes reales: guardar → servir por HTTP → reiniciar servicio → verificar referencia/bytes → volver a servir.
- Chromium decodificó los bytes almacenados de PNG/JPEG/WEBP/GIF/BMP/AVIF/ICO y del TIFF convertido a PNG.
- Pruebas de migración externa, sufijo heredado incorrecto y archivo compartido entre juegos.
- Pruebas de `.orbitpack` por selección individual, media-only, saves-only, config-only y perfil completo.
