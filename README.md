# 🛰️ ORBIT Portable Console Launcher

> **Your games. Your setup. Your orbit.**

ORBIT es un launcher de juegos **portable para Windows**, diseñado para convertir tu biblioteca de juegos y emuladores en una experiencia similar a una consola.

Está pensado especialmente para funcionar desde un **USB**, manteniendo juegos, configuración, carátulas, perfiles y otros datos dentro de la propia instalación.

---

## ✨ Características

### 🎮 Biblioteca de juegos

* Biblioteca visual con carátulas.
* Favoritos y juegos recientes.
* Búsqueda, filtros y ordenación.
* Estados de juego: pendiente, jugando y completado.
* Juegos ocultos.
* Colecciones personalizadas.
* Colecciones inteligentes.
* Juego aleatorio.
* Edición completa de los datos de cada juego.
* Estadísticas, historial y sesiones de juego.
* Seguimiento del tiempo jugado cuando el proceso puede monitorizarse.

### 🕹️ Juegos de PC y emulación

ORBIT permite gestionar tanto juegos de PC como juegos ejecutados mediante emuladores.

Puedes añadir:

* Ejecutables `.exe`.
* ROMs.
* Carpetas completas de juegos.
* Juegos instalados localmente desde Steam.
* Juegos detectados automáticamente mediante carpetas y accesos directos.

Los emuladores pueden configurarse por plataforma y utilizar argumentos como:

```text
{rom}
```

También es posible establecer emuladores predeterminados y comprobar sus ejecutables.

> ORBIT no incluye ROMs, juegos, BIOS, firmware ni keys propietarios.

---

## 🖥️ Interfaz estilo consola

ORBIT está diseñado para poder utilizarse cómodamente desde un escritorio, un televisor o una pantalla portátil.

### 🎨 Temas

Incluye múltiples temas visuales:

* Oscuro
* Claro
* OLED
* Neon
* Cyber
* Océano
* Bosque
* Atardecer
* Violeta
* Retro
* Ámbar
* Hielo
* Rose
* Medianoche

Además, puedes personalizar el color principal, la escala de la interfaz y las animaciones.

### 📐 Modos de interfaz

Los temas y los modos de distribución son independientes, por lo que puedes combinarlos.

Incluye:

* **Clásico**
* **Barra superior**
* **Compacto**
* **Cinemático**
* **Portátil**
* **Sofá / Mando**

El modo Sofá / Mando está pensado especialmente para jugar desde una televisión utilizando un mando.

---

## 🎮 Control con mando

ORBIT permite navegar utilizando:

* Teclado
* Ratón
* Gamepad

Con mando:

* Cruceta / stick → navegar
* A → seleccionar
* B → volver

También incluye navegación espacial, scroll con mando, puntero mediante joystick derecho y detección de mandos de estilo **PlayStation, Xbox y Nintendo**.

Los perfiles de mando permiten configurar remapeo y deadzone.

---

## 💾 Diseñado para USB

Una de las características principales de ORBIT es su funcionamiento portable.

La biblioteca utiliza rutas internas como:

```text
@launcher/games/MiJuego/game.exe
```

En lugar de depender de letras de unidad como:

```text
D:
E:
F:
```

Por ello, si conectas el USB en otro ordenador y cambia la letra de la unidad, ORBIT puede seguir encontrando los archivos que están dentro del propio USB.

---

## 🚀 Instalación portable

### 1. Copia ORBIT al USB

Copia toda la carpeta de ORBIT a tu unidad USB. (También se puede usar sin necesidad de usar USB, pero los pasos serán exactamente iguales)

### 2. Prepara el USB

Ejecuta:

```text
Preparar_USB.bat
```

El script prepara un runtime portable de Python dentro de:

```text
runtime/
```

Esto solo es necesario preparar una vez.

### 3. Ejecuta ORBIT

Después puedes iniciar:

```text
launcher.bat
```

El launcher puede funcionar incluso en ordenadores que no tengan Python instalado si el runtime portable ya está preparado.

También puede utilizar una instalación de Python 3 existente durante el desarrollo.

---

## 📂 Estructura portable

Una instalación puede tener una estructura similar a:

```text
ORBIT/
├── app/
├── data/
├── games/
├── emulators/
├── media/
│   └── covers/
├── saves/
├── backups/
├── plugins/
├── themes/
├── runtime/
├── launcher.bat
└── Preparar_USB.bat
```

### Principales carpetas

| Carpeta         | Contenido                                         |
| --------------- | ------------------------------------------------- |
| `app/`          | Código del launcher                               |
| `data/`         | Biblioteca, configuración, emuladores e historial |
| `games/`        | Juegos almacenados en el USB                      |
| `emulators/`    | Emuladores portables                              |
| `media/covers/` | Carátulas                                         |
| `saves/`        | Partidas centralizadas                            |
| `backups/`      | Copias de seguridad                               |
| `plugins/`      | Preparada para plugins                            |
| `themes/`       | Temas                                             |
| `runtime/`      | Python portable                                   |

---

## 📦 ORBIT Pack

ORBIT incluye un sistema de paquetes `.orbitpack` para transferir contenido entre instalaciones.

Permite trabajar con:

* Configuración.
* Perfiles.
* Juegos.
* ROMs.
* Partidas.
* Asociaciones entre juegos y emuladores.
* Rutas de destino.
* Componentes seleccionados.

El sistema incluye:

* SHA-256.
* Detección de duplicados.
* Importación selectiva.
* Fusión de perfiles.
* Rollback si una importación falla.
* Protección contra sobrescrituras silenciosas.
* Progreso durante la importación.
* Tiempo restante estimado.

Las ROMs y partidas existentes no se sobrescriben silenciosamente.

---

## 🖼️ Carátulas y multimedia

ORBIT permite utilizar diferentes tipos de imágenes para personalizar los juegos.

Se admiten formatos como:

```text
PNG
JPG / JPEG / JFIF
WEBP
GIF
AVIF
BMP
ICO
```

Las imágenes se almacenan dentro de ORBIT para mantener la instalación portable.

También puedes utilizar:

* Carátulas.
* Fondos.
* Logos.
* Capturas de pantalla.

Las imágenes originales seleccionadas no se modifican ni se eliminan.

### 🌐 SteamGridDB

ORBIT puede utilizar **SteamGridDB** para buscar carátulas online mediante la API personal del usuario.

La conexión es opcional y ORBIT puede utilizarse sin Internet.

Las credenciales se almacenan fuera de los archivos JSON y no se incluyen en las exportaciones.

---

## 🤖 ORBIT AI

ORBIT incluye un sistema de asistencia basado en IA que puede utilizarse para interactuar con la biblioteca.

Incluye:

* Comprensión de lenguaje natural.
* Búsqueda dentro de la biblioteca.
* Consulta del estado de los juegos.
* Recomendaciones.
* Memoria de preferencias.
* LLM local opcional.
* Búsqueda online opcional e independiente.

La IA no convierte Internet en una dependencia obligatoria de ORBIT.

---

## 🛡️ Modo seguro

ORBIT incluye:

```text
ORBIT_Modo_Seguro.bat
```

Este modo inicia ORBIT con:

* Tema oscuro.
* Interfaz clásica.
* Animaciones reducidas.
* Ajustes como pantalla inicial.

No modifica permanentemente la configuración guardada.

---

## ⚙️ Configuración y almacenamiento

ORBIT utiliza almacenamiento local basado en JSON.

La configuración utiliza:

* Escrituras atómicas.
* Copias de seguridad rotativas.
* Rutas portables.
* Recuperación de configuración.

Los juegos eliminados desde la biblioteca **no eliminan automáticamente el archivo original**.

---

## 🔐 Privacidad y funcionamiento local

La interfaz de ORBIT se sirve localmente mediante:

```text
127.0.0.1
```

El servidor solo escucha en el equipo local.

ORBIT mantiene una única instancia activa por USB y valida las peticiones realizadas a su servidor local.

Los datos reales de la aplicación permanecen en el almacenamiento de ORBIT.

---

## 🧪 Pruebas

Para ejecutar las pruebas automáticas:

```bash
python -m unittest discover -s tests -v
```

También puedes comprobar la sintaxis de JavaScript con:

```bash
node --check app/static/app.js
```

---

## 🛠️ Tecnología

ORBIT está construido principalmente con:

* **Python**
* **HTML**
* **CSS**
* **JavaScript**

La aplicación utiliza la biblioteca estándar de Python y las capacidades del navegador para su interfaz.

---

## 🤝 Contribuir

¿Quieres mejorar ORBIT?

Puedes contribuir mediante el repositorio oficial:

* 🐛 **Issues** → errores, problemas y sugerencias.
* 💡 **Issues** → nuevas ideas y propuestas.
* 🔧 **Pull Requests** → modificaciones y mejoras del código.

Antes de realizar cambios importantes, es recomendable abrir un Issue para hablar sobre la propuesta.

### 📩 Contacto

Si tienes alguna pregunta, encuentras un problema o quieres proponer una mejora:

**[Abrir un Issue](../../issues)**

Para solicitudes relacionadas con redistribución o proyectos derivados, utiliza los canales de contacto del repositorio.

---

## ⚠️ Juegos, ROMs y archivos propietarios

ORBIT es únicamente un launcher y gestor de bibliotecas.

El proyecto **no proporciona ni distribuye**:

* ROMs.
* Juegos comerciales.
* BIOS.
* Firmware propietario.
* Keys.

El usuario es responsable de utilizar sus propios archivos y de cumplir la legislación aplicable.

---

## 📜 Licencia

ORBIT utiliza una **licencia personalizada**.

Consulta el archivo [`LICENSE`](LICENSE) para conocer las condiciones completas de uso, modificación, contribución y redistribución.

Las modificaciones pueden proponerse mediante el repositorio oficial, pero la redistribución de copias modificadas fuera del repositorio oficial requiere autorización según las condiciones de la licencia.

---

## ⭐ Apoya ORBIT

Si ORBIT te resulta útil:

⭐ Dale una estrella al repositorio
🐛 Reporta errores
💡 Propón mejoras
🔧 Contribuye mediante Pull Requests
📢 Comparte el proyecto

---

# 🛰️ ORBIT

**Your games. Your setup. Your orbit.**
