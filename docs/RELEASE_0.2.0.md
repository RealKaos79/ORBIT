# ORBIT v0.2.0

## Qué incluye

ORBIT v0.2.0 amplía la v0.1.6 manteniendo la portabilidad y compatibilidad con la biblioteca existente.

### Biblioteca
- Edición completa de juegos.
- Estados pendiente, jugando y completado.
- Etiquetas, favoritos, ocultos, colecciones y filtros inteligentes.
- Juego aleatorio.
- Carátula, fondo, logo y capturas.

### Emulación e importación
- Emuladores editables, comprobación y predeterminado por plataforma.
- Argumentos por juego.
- Importación local de Steam y carpetas con ejecutables/accesos directos.

### Partidas
- Backup manual.
- Backup automático antes/después de jugar.
- Restauración con confirmación y copia de seguridad previa.
- Sincronización PC → USB y USB → PC.

### Consola y personalización
- Perfiles de usuario básicos.
- Remapeo básico de mando y deadzone.
- Tema oscuro, claro y OLED.
- Color principal, escala UI y reducción de animaciones.
- Navegación por mando, teclado y ratón.

### Diagnóstico
- Sesiones activas y cierre confirmado.
- Estadísticas e historial.
- Uso de almacenamiento bajo demanda.
- Migración automática desde datos v0.1.x.

## Seguridad
- Quitar un juego nunca borra el archivo original.
- Restaurar o sincronizar hacia el PC exige confirmación.
- Las restauraciones generan un backup de seguridad cuando corresponde.
- Las rutas portables continúan usando @launcher/.
- El servidor local solo escucha en loopback y valida las peticiones de escritura.

## Integraciones externas
RetroAchievements, Discord Rich Presence, actualizaciones online y ejecución de plugins quedan preparadas en la arquitectura, pero no se activan sin configuración explícita y una fuente externa válida.

## Validación
Antes del empaquetado se ejecutan:
- `python -m unittest discover -s tests -v`
- compilación de módulos Python
- `node --check app/static/app.js`
- validación del contenido de los ZIP para no incluir datos del usuario en el hotfix.
