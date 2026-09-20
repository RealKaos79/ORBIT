# ORBIT v0.2.2 — Privacidad, icono y selectores de Windows

## Cambios principales

- Nuevo icono ORBIT para favicon, app-mode de Edge/Chrome y acceso directo opcional de Windows.
- `Modo privacidad / streaming` activado por defecto.
  - Oculta la raíz del USB y rutas externas en la interfaz.
  - Los campos de rutas se muestran como contraseña mientras el modo está activo, sin alterar el valor guardado.
  - Diagnóstico y respuestas públicas del sistema ocultan rutas sensibles.
  - El log normal sustituye raíz, carpeta de usuario e IP local por marcadores seguros.
- Opción `Confirmar antes de cerrar juego/emulador`.
- Los selectores de archivo/carpeta usan una ventana propietaria invisible `TopMost` y `ShowDialog(owner)` para intentar mantenerse por delante incluso en modo pantalla completa/kiosk.
- Los errores del selector de Windows ya no vuelcan stderr/rutas locales en pantalla.
- Título de la ventana simplificado a `ORBIT` y manifest de aplicación incluido.
- Script opcional `Crear_acceso_directo_ORBIT.bat` con icono ORBIT.

## Seguridad de datos

El hotfix no contiene `data/`, `runtime/`, `media/`, `games/`, `emulators/`, `saves/` ni `backups/` y está pensado para copiarse encima de una v0.2.1 existente.
