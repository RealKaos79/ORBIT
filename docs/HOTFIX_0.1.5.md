# ORBIT v0.1.5 — Pantalla completa al iniciar

## Corrección

La preferencia `start_fullscreen` ya no depende de `--start-fullscreen` sobre una ventana `--app` de Edge/Chrome.

En Windows:

- Con **Iniciar en pantalla completa = activado**, Microsoft Edge se abre usando su modo kiosk fullscreen (`--kiosk ... --edge-kiosk-type=fullscreen`). Chrome usa `--kiosk` como fallback.
- Con la opción desactivada, ORBIT conserva el modo app maximizado.
- ORBIT usa un perfil de navegador dedicado dentro de `data/browser-profile`, evitando que una instancia de Edge ya abierta absorba los argumentos de arranque.
- Al cambiar el interruptor desde Ajustes, ORBIT intenta aplicar también el Fullscreen API inmediatamente. La preferencia queda guardada para el siguiente arranque.

El perfil del navegador forma parte de los datos portables y permanece en el USB.
