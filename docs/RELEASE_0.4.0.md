# ORBIT v0.4.0 — Switch, mando, ORBIT Pack y administración

## Biblioteca y multimedia
- Nintendo Switch como plataforma completa de biblioteca y escaneo (`.nsp`, `.xci`, `.nro`, `.nca`).
- Carátula, fondo, logo y capturas siguen gestionándose desde la ficha del juego con copias portables dentro del USB.
- Preparar para otro PC, duplicados y puntos de recuperación integrados.

## Emuladores
- Centro de emuladores actualizado con consola/plataforma y fuentes oficiales/proyecto verificadas.
- Instalación masiva: ORBIT crea una carpeta por emulador y solo intenta descarga automática cuando detecta un ZIP Windows desde una fuente oficial conocida.
- Tras instalar un emulador portable, ORBIT lo registra automáticamente en el perfil activo para las plataformas compatibles.
- Mesen se actualiza al proyecto comunitario actual Mesen CE (`nesdev-org/MesenCE`).
- Eden aparece para Nintendo Switch; ORBIT no distribuye juegos, firmware ni claves.

## Mando
- Cambio automático entre mando, ratón y teclado.
- Cursor recuperado al volver al ratón.
- Repetición/deadzone de navegación configurables.
- Tester de mando y estilos de botones PlayStation/Xbox/Nintendo/automático.
- Atajos configurables para búsqueda, menú y favorito.

## ORBIT Pack
- Exportación `.orbitpack` con biblioteca, multimedia, emuladores portables opcionales y archivos de juego solo si el usuario los incluye expresamente.
- SHA-256 de manifiesto y archivos.
- Inspección antes de importar y protección contra path traversal.
- Importación portable y resolución de conflictos.

## ORBIT administrado
- Un ORBIT Personal sigue siendo Personal por defecto.
- Una copia solo entra en modo administrado al recibir `authorization_config.json` generado por ORBIT Admin.
- Primer uso administrado requiere Internet.
- Cada arranque con Internet revalida el estado.
- Una autorización válida puede funcionar offline hasta que reciba un bloqueo.
- Suspendido/revocado/bloqueado/mantenimiento persisten offline hasta una nueva autorización firmada.
- Firma RSA: el cliente recibe solo la clave pública; la privada permanece en ORBIT Server/Admin.
- Borrar o manipular el estado local no concede autorización.
- Marcadores redundantes de enrolamiento dificultan convertir localmente una copia administrada en Personal.
- Todas las operaciones de escritura y multimedia quedan bloqueadas mientras no exista autorización.
- Modo mantenimiento permite solo comprobación/reautorización y diagnóstico limitado.

## Seguridad y estabilidad
- La distribución Personal no incluye claves ni configuración Admin.
- El instalador de emuladores valida rutas ZIP y limita tamaños.
- Puntos de recuperación usan nombres únicos y rollback previo.
- Integración ORBIT↔Server probada en ciclo pendiente/autorizado/suspendido/offline/reactivado.
