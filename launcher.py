from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import time
import webbrowser
import hashlib
import tempfile
from logging.handlers import RotatingFileHandler
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from app.core.instance_lock import InstanceLock
from app.server import LauncherServer


LOGGER = logging.getLogger("orbit")


def _setup_logging(root: Path) -> None:
    log_dir = root / "data" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        log_dir / "orbit.log",
        maxBytes=1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )

    class SafeFormatter(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:
            text = super().format(record)
            replacements = [(str(root), "[ORBIT]"), (str(Path.home()), "[USUARIO]")]
            for original, replacement in replacements:
                if original:
                    text = text.replace(original, replacement).replace(original.replace("\\", "/"), replacement)
            text = re.sub(r"(?<!\d)(?:\d{1,3}\.){3}\d{1,3}(?!\d)", "[IP local]", text)
            # If a traceback/message still contains an absolute Windows path
            # outside ORBIT or the user's home, hide it as well.
            text = re.sub(r"(?i)\b[a-z]:\\[^\r\n|]+", "[ruta externa]", text)
            return text

    handler.setFormatter(SafeFormatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    # Avoid adding duplicate handlers when tests invoke main repeatedly.
    if not any(isinstance(h, RotatingFileHandler) and getattr(h, "baseFilename", "") == str((log_dir / "orbit.log").resolve()) for h in root_logger.handlers):
        root_logger.addHandler(handler)


def _cleanup_legacy_admin_files(root: Path) -> None:
    """Remove only the retired ORBIT Admin enrollment state from v0.4.x.

    These files never contain games, saves, profiles, media or emulator data.
    Failure to remove a read-only legacy marker must never stop personal ORBIT.
    """
    files = [
        root / "authorization_config.json",
        root / "authorization_config.example.json",
        root / "app" / "services" / "authorization.py",
        root / "app" / "services" / "privacy.py",
        root / "app" / "services" / "signing.py",
    ]
    for path in files:
        try:
            if path.exists():
                try:
                    path.chmod(0o666)
                except OSError:
                    pass
                path.unlink(missing_ok=True)
        except OSError:
            LOGGER.warning("No se pudo retirar un archivo antiguo de ORBIT Admin: %s", path.name)
    cache_dir = root / "app" / "services" / "__pycache__"
    if cache_dir.is_dir():
        for pattern in ("authorization.*.pyc", "privacy.*.pyc", "signing.*.pyc"):
            for path in cache_dir.glob(pattern):
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
    state_dir = root / "data" / ".orbit-auth"
    try:
        if state_dir.exists():
            for child in state_dir.rglob("*"):
                try:
                    child.chmod(0o666)
                except OSError:
                    pass
            shutil.rmtree(state_dir, ignore_errors=True)
    except OSError:
        LOGGER.warning("No se pudo retirar el estado antiguo de ORBIT Admin")


def _browser_profile_dir(root: Path) -> Path:
    # Chromium writes many small files to its user-data directory. Keeping
    # that profile on a USB makes startup and scrolling noticeably slower.
    # ORBIT therefore stores ONLY disposable browser runtime/cache data in
    # Windows' local temp directory; library/config/media remain on the USB.
    root_key = hashlib.sha256(str(root.resolve()).casefold().encode("utf-8", errors="ignore")).hexdigest()[:16]
    profile = Path(tempfile.gettempdir()) / "ORBIT" / "browser" / root_key / "profile"
    profile.mkdir(parents=True, exist_ok=True)
    return profile


def _browser_args(browser: Path, family: str, url: str, profile: Path, fullscreen: bool) -> list[str]:
    cache = profile.parent / "cache"
    cache.mkdir(parents=True, exist_ok=True)
    common = [
        str(browser),
        f"--user-data-dir={profile}",
        f"--disk-cache-dir={cache}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-session-crashed-bubble",
        "--disable-background-networking",
        "--disable-component-update",
        "--disable-sync",
    ]
    if fullscreen:
        if family == "edge":
            return common + [
                "--kiosk",
                url,
                "--edge-kiosk-type=fullscreen",
                "--kiosk-idle-timeout-minutes=0",
            ]
        return common + ["--kiosk", url]
    return common + [f"--app={url}", "--start-maximized"]


def _browser_app(url: str, root: Path, fullscreen: bool = True) -> subprocess.Popen | None:
    if os.name != "nt":
        return None

    candidates = [
        (Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Microsoft/Edge/Application/msedge.exe", "edge"),
        (Path(os.environ.get("PROGRAMFILES", "")) / "Microsoft/Edge/Application/msedge.exe", "edge"),
        (Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe", "chrome"),
        (Path(os.environ.get("PROGRAMFILES", "")) / "Google/Chrome/Application/chrome.exe", "chrome"),
    ]
    profile = _browser_profile_dir(root)
    for browser, family in candidates:
        if not browser.exists():
            continue
        # Edge's documented kiosk fullscreen mode is substantially more
        # reliable than --start-fullscreen combined with --app, especially
        # when another Edge instance is already running. Chrome supports
        # the corresponding --kiosk URL form.
        args = _browser_args(browser, family, url, profile, fullscreen)
        try:
            return subprocess.Popen(args)
        except OSError:
            continue
    return None


def _open_ui(url: str, root: Path, fullscreen: bool) -> None:
    if _browser_app(url, root=root, fullscreen=fullscreen) is not None:
        return
    # ORBIT is a desktop launcher. On Windows do not silently degrade into a
    # normal browser tab: that changes the product behavior and controller UX.
    if os.name == "nt":
        raise RuntimeError("ORBIT necesita Microsoft Edge o Google Chrome para abrirse en modo aplicación.")
    # Development-only fallback for non-Windows environments.
    webbrowser.open(url)


def _read_fullscreen(root: Path) -> bool:
    """Read fullscreen preference for the last active ORBIT profile.

    This path is used only when a healthy server already exists and the user
    reopens launcher.bat. Avoid importing the full application just to recover
    one preference, but honor profile-scoped settings introduced in v0.3.
    """
    try:
        raw = json.loads((root / "data" / "settings.json").read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return True
        profiles = raw.get("profiles") if isinstance(raw.get("profiles"), dict) else {}
        profile_id = str(profiles.get("active") or "default")
        if profile_id != "default":
            personal_path = root / "data" / "profiles" / profile_id / "profile_settings.json"
            try:
                personal = json.loads(personal_path.read_text(encoding="utf-8"))
                if isinstance(personal, dict) and "start_fullscreen" in personal:
                    return bool(personal.get("start_fullscreen"))
            except (OSError, json.JSONDecodeError):
                pass
        return bool(raw.get("start_fullscreen", True))
    except (OSError, json.JSONDecodeError):
        return True


def _session_path(root: Path) -> Path:
    return root / "data" / ".orbit-session.json"


def _write_session(root: Path, host: str, port: int) -> None:
    path = _session_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps({"host": host, "port": port, "pid": os.getpid()}), encoding="utf-8")
    temp.replace(path)


def _remove_owned_session(root: Path, port: int) -> None:
    path = _session_path(root)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict) and int(payload.get("port", -1)) == int(port):
            path.unlink(missing_ok=True)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        pass


def _existing_url(root: Path) -> str | None:
    path = _session_path(root)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            return None
        host = str(payload.get("host") or "")
        port = int(payload.get("port"))
        if host not in {"127.0.0.1", "localhost", "::1"} or not (1 <= port <= 65535):
            return None
        url = f"http://{host}:{port}"
        with urlopen(url + "/api/ping", timeout=0.6) as response:
            data = json.loads(response.read())
        if isinstance(data, dict) and data.get("ok") is True and data.get("name") == "ORBIT":
            return url
    except (OSError, ValueError, TypeError, json.JSONDecodeError, URLError):
        return None
    return None


def main() -> int:
    root = Path(__file__).resolve().parent
    _setup_logging(root)
    LOGGER.info("Iniciando ORBIT")
    _cleanup_legacy_admin_files(root)
    os.environ.setdefault("PORTABLE_LAUNCHER_ROOT", str(root))
    lock = InstanceLock(root / "data" / ".orbit.lock")

    if not lock.acquire():
        # The user may simply have closed the app-mode browser window while the
        # original ORBIT server is still healthy. Reopen that same instance.
        for _ in range(10):
            existing = _existing_url(root)
            if existing:
                print("ORBIT ya estaba abierto. Reabriendo la ventana.")
                _open_ui(existing, root=root, fullscreen=_read_fullscreen(root))
                return 0
            time.sleep(0.2)
        print("ORBIT ya está abierto, pero no responde. Cierra la ventana de consola anterior y vuelve a intentarlo.")
        return 2

    server: LauncherServer | None = None
    port = -1
    try:
        server = LauncherServer(root)
        host, port = server.start()
        _write_session(root, host, port)
        url = f"http://{host}:{port}"
        LOGGER.info("Servidor local ORBIT activo")
        print("ORBIT Portable Console Launcher iniciado.")

        settings = server.library.settings()
        _open_ui(url, root=root, fullscreen=bool(settings.get("start_fullscreen", True)))

        # Chromium can hand the app window to another process and exit its
        # initial process immediately. The server therefore lives until ORBIT
        # explicitly requests shutdown (or this console receives Ctrl+C).
        try:
            while server.is_running:
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass
        finally:
            server.stop()
        LOGGER.info("ORBIT cerrado correctamente")
        return 0
    except Exception:
        LOGGER.exception("Fallo fatal en ORBIT")
        raise
    finally:
        if port > 0:
            _remove_owned_session(root, port)
        lock.release()


if __name__ == "__main__":
    raise SystemExit(main())
