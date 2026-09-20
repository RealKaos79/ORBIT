# ORBIT v0.1.3 — Hotfix de carátulas personalizadas

## Objetivo

Permitir gestionar manualmente la carátula de cada juego desde la interfaz sin editar JSON ni copiar archivos a mano.

## Uso

1. Abre un juego desde Inicio o Biblioteca.
2. En **Detalles del juego**, pulsa **Añadir carátula**.
3. Elige una imagen PNG, JPG/JPEG o WEBP.
4. ORBIT crea una copia portable dentro de `media/covers/`.
5. Para sustituirla, pulsa **Cambiar carátula**.
6. Para retirarla, pulsa **Quitar carátula**.

## Seguridad y portabilidad

- Tamaño máximo: 25 MB.
- Se verifica que el archivo tenga una firma compatible con PNG, JPEG o WEBP.
- La imagen original no se modifica ni se elimina.
- Solo las copias gestionadas dentro de `media/covers/` pueden ser eliminadas por esta función.
- La ruta guardada usa `@launcher/media/covers/...`, de modo que no depende de la letra del USB.

## Pruebas

- Copia portable de carátula.
- Conservación de la imagen original.
- Sustitución de PNG por JPG y limpieza de la copia anterior.
- Eliminación segura de la copia gestionada.
- Protección de carátulas externas/legacy.
- Rechazo de archivos falsos renombrados como imagen.
- Endpoint API para añadir, servir y eliminar carátulas.
- Suite completa: 40/40 pruebas correctas.
