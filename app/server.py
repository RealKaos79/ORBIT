from __future__ import annotations

import json
import os
import logging
import mimetypes
import shutil
import threading
import time
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from app.core.paths import PortablePaths
from app.core.storage import JsonStore
from app.services.dialogs import open_dialog
from app.services.library import LibraryService
from app.services.system_info import collect_system_info
from app.services.external_links import emulator_sites, open_emulator_site
from app.services.emulator_installer import EmulatorInstaller


LOGGER = logging.getLogger("orbit.server")


class LauncherServer:
    MAX_BODY_BYTES = 1024 * 1024

    def __init__(self, root: Path | None = None) -> None:
        mimetypes.add_type("image/avif", ".avif")
        mimetypes.add_type("image/webp", ".webp")
        self.paths = PortablePaths(root)
        self.store = JsonStore(self.paths)
        self.library = LibraryService(self.paths, self.store)
        self.emulator_installer = EmulatorInstaller(self.paths)
        self.safe_mode = os.getenv("ORBIT_SAFE_MODE", "").strip() == "1"
        try:
            self.version = (self.paths.root / "VERSION").read_text(encoding="utf-8").strip()
        except OSError:
            self.version = "unknown"
        self.static_dir = Path(__file__).resolve().parent / "static"
        self.httpd: ThreadingHTTPServer | None = None
        self._running = threading.Event()
        self._lifecycle_lock = threading.RLock()
        self._export_jobs: dict[str, dict] = {}
        self._export_jobs_lock = threading.RLock()
        self._import_jobs: dict[str, dict] = {}
        self._import_jobs_lock = threading.RLock()
        self._active_import = threading.Lock()

    def _export_job_snapshot(self, job_id: str) -> dict:
        with self._export_jobs_lock:
            job = self._export_jobs.get(str(job_id))
            if not job:
                raise KeyError("Exportación no encontrada")
            return dict(job)

    def _import_job_snapshot(self, job_id: str) -> dict:
        with self._import_jobs_lock:
            job = self._import_jobs.get(str(job_id))
            if not job:
                raise KeyError("Importación no encontrada.")
            return dict(job)

    def _accept_uploaded_pack(self, source, size: int) -> str:
        """Local-only browser file picker fallback when a Windows native dialog is unavailable."""
        if size <= 0 or size > 32 * 1024 ** 3:
            raise ValueError("Selecciona un .orbitpack de tamaño válido (máximo 32 GB).")
        if size + 100 * 1024 ** 2 > shutil.disk_usage(self.paths.root).free:
            raise ValueError("No hay espacio suficiente para recibir este paquete.")
        staging = self.paths.data / ".import-staging"
        staging.mkdir(parents=True, exist_ok=True)
        path = staging / (uuid.uuid4().hex + ".orbitpack")
        try:
            with path.open("xb") as dest:
                remaining = size
                while remaining:
                    chunk = source.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise ValueError("La carga del paquete se interrumpió.")
                    dest.write(chunk)
                    remaining -= len(chunk)
            return str(path.resolve())
        except Exception:
            path.unlink(missing_ok=True)
            raise

    def _accept_uploaded_avatar(self, source, size: int, profile_id: str) -> dict:
        """Browser upload fallback: validate image content in the existing library."""
        if size <= 0 or size > 15 * 1024 * 1024:
            raise ValueError("La foto de perfil debe ocupar entre 1 byte y 15 MB.")
        # Reject unknown profiles before writing anything to disk.
        self.library._find_profile(profile_id)
        staging = self.paths.data / ".avatar-staging"
        staging.mkdir(parents=True, exist_ok=True)
        path = staging / f"{uuid.uuid4().hex}.bin"
        try:
            with path.open("xb") as output:
                remaining = size
                while remaining:
                    chunk = source.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise ValueError("La transferencia de la foto se interrumpió.")
                    output.write(chunk)
                    remaining -= len(chunk)
            return self.library.set_profile_avatar(profile_id, str(path))
        finally:
            path.unlink(missing_ok=True)

    def _discard_staged_pack(self, value: str) -> None:
        """Never delete a user's original archive from a native file picker."""
        path = Path(value).resolve()
        staging = (self.paths.data / ".import-staging").resolve()
        if path.parent == staging and path.suffix.casefold() == ".orbitpack":
            try:
                path.unlink(missing_ok=True)
            except OSError:
                LOGGER.warning("No se pudo limpiar el archivo de importación temporal")

    def _start_import_job(self, payload: dict) -> str:
        if not self._active_import.acquire(blocking=False):
            raise ValueError("Ya hay una importación en curso. Espera a que termine.")
        job_id = uuid.uuid4().hex
        now = time.time()
        with self._import_jobs_lock:
            if len(self._import_jobs) >= 32:
                stale = sorted(self._import_jobs.values(), key=lambda j: j["updated_at"])[:8]
                for entry in stale:
                    self._import_jobs.pop(entry["id"], None)
            self._import_jobs[job_id] = {
                "id": job_id, "status": "queued", "phase": "verifying", "percent": 0.,
                "processed_bytes": 0, "total_bytes": 0, "eta_seconds": None, "current": None,
                "started_at": now, "updated_at": now, "result": None, "error": None,
            }

        def update(info: dict) -> None:
            with self._import_jobs_lock:
                job = self._import_jobs[job_id]
                pct = max(0., min(1., float(info.get("percent") or 0.)))
                job.update({
                    "status": "running", "phase": str(info.get("phase") or "importing"),
                    "percent": pct, "processed_bytes": int(info.get("processed_bytes") or 0),
                    "total_bytes": int(info.get("total_bytes") or 0),
                    "eta_seconds": info.get("eta_seconds"), "current": info.get("current"),
                    "updated_at": time.time(),
                })

        def worker() -> None:
            try:
                with self.library._lock:
                    result = self.library.import_orbitpack(
                        str(payload.get("path") or ""), str(payload.get("conflict") or "skip"),
                        components=payload.get("components") if isinstance(payload.get("components"), list) else None,
                        profile_strategy=str(payload.get("profile_strategy") or "merge-active"),
                        config_conflict=str(payload.get("config_conflict") or "keep-existing"),
                        progress=update,
                    )
                with self._import_jobs_lock:
                    self._import_jobs[job_id].update({"status": "done", "phase": "done", "percent": 1.,
                                                      "eta_seconds": 0., "result": result, "updated_at": time.time()})
            except Exception as exc:
                LOGGER.exception("Error importando ORBIT Pack")
                with self._import_jobs_lock:
                    self._import_jobs[job_id].update({"status": "error", "phase": "error",
                                                      "error": str(exc) or "No se pudo importar el paquete.",
                                                      "updated_at": time.time()})
            finally:
                # Only self-generated browser uploads are disposable; NEVER
                # delete a user's selected .orbitpack.
                self._discard_staged_pack(str(payload.get("path") or ""))
                self._active_import.release()

        try:
            threading.Thread(target=worker, name=f"orbit-import-{job_id[:8]}", daemon=True).start()
        except Exception:
            self._active_import.release()
            raise
        return job_id

    def _start_export_job(self, payload: dict) -> str:
        job_id = uuid.uuid4().hex
        now = time.time()
        initial = {
            "id": job_id, "status": "queued", "phase": "preparing", "percent": 0.0,
            "processed_bytes": 0, "total_bytes": 0, "eta_seconds": None, "current": None,
            "started_at": now, "updated_at": now, "result": None, "error": None,
        }
        with self._export_jobs_lock:
            if len(self._export_jobs) >= 32:
                oldest = sorted(self._export_jobs.values(), key=lambda x: float(x.get("updated_at") or 0.0))[:8]
                for item in oldest:
                    self._export_jobs.pop(str(item.get("id") or ""), None)
            self._export_jobs[job_id] = initial

        def update(info: dict) -> None:
            with self._export_jobs_lock:
                job = self._export_jobs.get(job_id)
                if not job:
                    return
                job.update({
                    "status": "running",
                    "phase": str(info.get("phase") or job.get("phase") or "packing"),
                    "percent": max(0.0, min(1.0, float(info.get("percent") or 0.0))),
                    "processed_bytes": int(info.get("processed_bytes") or 0),
                    "total_bytes": int(info.get("total_bytes") or 0),
                    "eta_seconds": info.get("eta_seconds"),
                    "current": info.get("current"),
                    "updated_at": time.time(),
                })

        def worker() -> None:
            try:
                game_ids = payload.get("game_ids") if isinstance(payload.get("game_ids"), list) else None
                result = self.library.create_orbitpack(
                    game_ids=game_ids,
                    include_game_files=payload.get("include_game_files", payload.get("include_games", True)) is not False,
                    include_emulators=payload.get("include_emulators") is not False,
                    include_media=payload.get("include_media") is not False,
                    include_saves=bool(payload.get("include_saves")),
                    name=str(payload.get("name") or "") or None,
                    include_games=payload.get("include_games") is not False,
                    include_configuration=bool(payload.get("include_configuration")),
                    include_other=bool(payload.get("include_other")),
                    full_profile=bool(payload.get("full_profile")),
                    destination=str(payload.get("destination") or "") or None,
                    progress=update,
                )
                with self._export_jobs_lock:
                    job = self._export_jobs.get(job_id)
                    if job:
                        job.update({
                            "status": "done", "phase": "done", "percent": 1.0, "eta_seconds": 0.0,
                            "updated_at": time.time(), "result": result, "error": None,
                        })
            except Exception as exc:
                LOGGER.exception("Error exportando ORBIT Pack")
                with self._export_jobs_lock:
                    job = self._export_jobs.get(job_id)
                    if job:
                        job.update({
                            "status": "error", "phase": "error", "updated_at": time.time(),
                            "error": str(exc) or "No se pudo exportar el ORBIT Pack.",
                        })

        threading.Thread(target=worker, name=f"orbit-export-{job_id[:8]}", daemon=True).start()
        return job_id

    def _register_installed_emulator(self, package_id: str, result: dict) -> list[dict]:
        executable = result.get("executable")
        if not executable:
            return []
        pkg = self.emulator_installer.package(package_id)
        registered = []
        for platform in pkg.orbit_platforms:
            try:
                registered.append(self.library.ensure_emulator(name=pkg.name, platform=platform, executable=str(executable)))
            except ValueError:
                continue
        return registered

    def start(self, host: str = "127.0.0.1", port: int = 0) -> tuple[str, int]:
        if host not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("Por seguridad ORBIT solo puede escuchar en el equipo local.")
        with self._lifecycle_lock:
            if self.is_running:
                raise RuntimeError("El servidor de ORBIT ya está iniciado.")

        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: object) -> None:
                return

            def _security_headers(self, cache_control: str = "no-store") -> None:
                self.send_header("Cache-Control", cache_control)
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                self.send_header("Cross-Origin-Resource-Policy", "same-origin")

            def _valid_host(self) -> bool:
                # Reject DNS-rebinding style requests. ORBIT is a local-only app
                # and should never answer for arbitrary Host headers.
                raw = (self.headers.get("Host") or "").strip().lower()
                if not raw:
                    return False
                hostname = raw
                if raw.startswith("["):
                    end = raw.find("]")
                    hostname = raw[1:end] if end >= 0 else raw
                elif ":" in raw:
                    hostname = raw.rsplit(":", 1)[0]
                return hostname in {"127.0.0.1", "localhost", "::1"}

            def _guard_local_host(self) -> bool:
                if self._valid_host():
                    return True
                self._json({"ok": False, "error": "Host local no válido."}, HTTPStatus.MISDIRECTED_REQUEST)
                return False

            def _json(self, payload: object, status: int = 200) -> None:
                raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self._security_headers()
                self.end_headers()
                self.wfile.write(raw)

            def _body(self) -> dict:
                content_type = (self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
                if content_type != "application/json":
                    raise ValueError("La API de ORBIT solo acepta Content-Type application/json.")
                try:
                    length = int(self.headers.get("Content-Length", "0") or 0)
                except ValueError as exc:
                    raise ValueError("Content-Length no válido.") from exc
                if length < 0 or length > server.MAX_BODY_BYTES:
                    raise ValueError("La petición es demasiado grande.")
                raw = self.rfile.read(length) if length else b"{}"
                try:
                    payload = json.loads(raw.decode("utf-8") or "{}")
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise ValueError("El cuerpo de la petición no contiene JSON válido.") from exc
                if not isinstance(payload, dict):
                    raise ValueError("El cuerpo de la petición debe ser un objeto JSON.")
                return payload

            def _error(self, exc: Exception, status: int = 400) -> None:
                self._json({"ok": False, "error": str(exc)}, status)

            def do_GET(self) -> None:
                if not self._guard_local_host():
                    return
                path = urlparse(self.path).path
                try:
                    if path == "/api/ping":
                        self._json({"ok": True, "name": "ORBIT"})
                        return
                    if path == "/api/state":
                        settings = server.library.settings()
                        if server.safe_mode:
                            settings = dict(settings)
                            settings.update({"theme": "dark", "interface_mode": "classic", "start_view": "settings", "reduce_motion": True})
                        system = collect_system_info(server.paths, include_gpu=False)
                        self._json({
                            "ok": True,
                            "games": server.library.games(),
                            "emulators": server.library.emulators(),
                            "settings": settings,
                            "stats": server.library.stats(),
                            "collections": server.library.collections(),
                            "profiles": server.library.profiles(),
                            "emulator_sites": emulator_sites(),
                            "emulator_packages": server.emulator_installer.catalog(),
                            "active_sessions": server.library.active_sessions(),
                            "system": system,
                            "custom_themes": server.library.custom_themes(),
                            "safe_mode": server.safe_mode,
                            "version": server.version,
                        })
                        return
                    if path == "/api/diagnostics":
                        system = collect_system_info(server.paths)
                        items = server.library.diagnostics()
                        self._json({"ok": True, "items": items, "system": system})
                        return
                    if path == "/api/stats":
                        self._json({"ok": True, "stats": server.library.stats()})
                        return
                    if path == "/api/history":
                        self._json({"ok": True, "history": server.library.history()})
                        return
                    if path == "/api/storage":
                        self._json({"ok": True, "storage": server.library.storage_info()})
                        return
                    if path == "/api/portable-check":
                        self._json({"ok": True, "result": server.library.prepare_for_other_pc()})
                        return
                    if path == "/api/duplicates":
                        self._json({"ok": True, "result": server.library.duplicate_report()})
                        return
                    if path == "/api/recovery":
                        self._json({"ok": True, "items": server.library.list_recovery_points()})
                        return
                    if path == "/api/collections":
                        self._json({"ok": True, "collections": server.library.collections()})
                        return
                    if path == "/api/sessions":
                        self._json({"ok": True, "sessions": server.library.active_sessions()})
                        return
                    if path == "/api/emulator-sites":
                        self._json({"ok": True, "items": emulator_sites()})
                        return
                    if path == "/api/import/steam-preview":
                        self._json({"ok": True, "items": server.library.steam_preview()})
                        return
                    if path.endswith("/backups") and path.startswith("/api/games/"):
                        game_id = path.split("/")[3]
                        self._json({"ok": True, "backups": server.library.list_game_backups(game_id)})
                        return
                    if path == "/api/readiness":
                        self._json({"ok": True, "result": server.library.readiness_report()})
                        return
                    if path == "/api/themes":
                        self._json({"ok": True, "themes": server.library.custom_themes()})
                        return
                    if path == "/api/ai/memory":
                        self._json({"ok": True, "memory": server.library.ai_memory()})
                        return
                    if path == "/api/orbitpack/export/progress":
                        query = parse_qs(urlparse(self.path).query)
                        job_id = str((query.get("job_id") or [""])[0])
                        if not job_id:
                            raise ValueError("Falta el identificador de exportación.")
                        self._json({"ok": True, "job": server._export_job_snapshot(job_id)})
                        return
                    if path == "/api/orbitpack/import/progress":
                        query = parse_qs(urlparse(self.path).query)
                        job_id = str((query.get("job_id") or [""])[0])
                        if not job_id:
                            raise ValueError("Falta el identificador de importación.")
                        self._json({"ok": True, "job": server._import_job_snapshot(job_id)})
                        return
                    if path.endswith("/performance") and path.startswith("/api/games/"):
                        game_id = path.split("/")[3]
                        self._json({"ok": True, "result": server.library.performance_for_game(game_id, collect_system_info(server.paths))})
                        return
                    if path.endswith("/requirements") and path.startswith("/api/games/"):
                        game_id = path.split("/")[3]
                        self._json({"ok": True, "result": server.library.requirements_for_game(game_id)})
                        return
                    if path.startswith("/api/"):
                        self._json({"ok": False, "error": "Endpoint no encontrado."}, HTTPStatus.NOT_FOUND)
                        return
                    if path == "/media" or path.startswith("/media/"):
                        relative = path[len("/media/"):] if path.startswith("/media/") else ""
                        target = (server.paths.media / relative).resolve()
                        if server.paths.media != target and server.paths.media not in target.parents:
                            self.send_error(HTTPStatus.FORBIDDEN)
                            return
                        self._serve_file(target, media=True)
                        return
                    self._serve_static(path)
                except (ValueError, KeyError) as exc:
                    self._error(exc, 400)
                except Exception as exc:
                    LOGGER.exception("Error atendiendo GET %s", self.path)
                    self._error(exc, 500)

            def do_POST(self) -> None:
                if not self._guard_local_host():
                    return
                path = urlparse(self.path).path
                try:
                    if path == "/api/orbitpack/upload":
                        if (self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower() != "application/octet-stream":
                            raise ValueError("El archivo debe enviarse como contenido binario.")
                        try:
                            length = int(self.headers.get("Content-Length") or "0")
                        except ValueError as exc:
                            raise ValueError("Tamaño del archivo no válido.") from exc
                        staged = server._accept_uploaded_pack(self.rfile, length)
                        self._json({"ok": True, "path": staged}, 201)
                        return
                    if path.startswith("/api/profiles/") and path.endswith("/avatar/upload"):
                        if (self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower() != "application/octet-stream":
                            raise ValueError("La imagen debe enviarse como contenido binario.")
                        try:
                            length = int(self.headers.get("Content-Length") or "0")
                        except ValueError as exc:
                            raise ValueError("Tamaño de imagen no válido.") from exc
                        profile_id = path.split("/")[3]
                        item = server._accept_uploaded_avatar(self.rfile, length, profile_id)
                        self._json({"ok": True, "profile": item}, 201)
                        return
                    payload = self._body()
                    if path.endswith("/art/search") and path.startswith("/api/games/"):
                        game_id = path.split("/")[3]
                        provider_id = payload.get("provider_game_id")
                        result = server.library.search_game_art(game_id, str(payload.get("kind") or "grid"), int(provider_id) if provider_id not in (None, "") else None)
                        self._json({"ok": True, "result": result})
                        return
                    if path.endswith("/art/apply") and path.startswith("/api/games/"):
                        game_id = path.split("/")[3]
                        game = server.library.apply_game_art(game_id, str(payload.get("kind") or "cover"), str(payload.get("url") or ""))
                        self._json({"ok": True, "game": game})
                        return
                    if path == "/api/games":
                        game = server.library.add_game(payload)
                        self._json({"ok": True, "game": game}, 201)
                        return
                    if path.endswith("/update") and path.startswith("/api/games/"):
                        game_id = path.split("/")[3]
                        game = server.library.update_game(game_id, payload)
                        self._json({"ok": True, "game": game})
                        return
                    if "/media/" in path and path.startswith("/api/games/"):
                        parts = path.split("/")
                        if len(parts) >= 6:
                            game_id, kind = parts[3], parts[5]
                            game = server.library.set_game_media(game_id, kind, str(payload.get("path") or ""))
                            self._json({"ok": True, "game": game})
                            return
                    if path.endswith("/backup") and path.startswith("/api/games/"):
                        game_id = path.split("/")[3]
                        result = server.library.backup_game_saves(game_id, str(payload.get("reason") or "manual"))
                        self._json({"ok": True, "backup": result})
                        return
                    if path.endswith("/restore") and path.startswith("/api/games/"):
                        game_id = path.split("/")[3]
                        result = server.library.restore_game_backup(game_id, str(payload.get("backup_id") or ""), bool(payload.get("confirmed")))
                        self._json({"ok": True, "result": result})
                        return
                    if path.endswith("/sync") and path.startswith("/api/games/"):
                        game_id = path.split("/")[3]
                        result = server.library.sync_game_saves(game_id, str(payload.get("direction") or ""), bool(payload.get("confirmed")))
                        self._json({"ok": True, "result": result})
                        return
                    if path.endswith("/stop") and path.startswith("/api/games/"):
                        game_id = path.split("/")[3]
                        result = server.library.stop_game(game_id, bool(payload.get("confirmed")))
                        self._json({"ok": True, "result": result})
                        return
                    if path.endswith("/metadata-guess") and path.startswith("/api/games/"):
                        game_id = path.split("/")[3]
                        self._json({"ok": True, "guess": server.library.local_metadata_guess(game_id)})
                        return
                    if path.startswith("/api/themes/"):
                        theme_id = path.split("/")[3]
                        server.library.delete_custom_theme(theme_id)
                        self._json({"ok": True})
                        return
                    if path.endswith("/cover") and path.startswith("/api/games/"):
                        game_id = path.split("/")[3]
                        if not game_id:
                            raise ValueError("Identificador de juego no válido.")
                        game = server.library.set_game_cover(game_id, str(payload.get("path") or ""))
                        self._json({"ok": True, "game": game})
                        return
                    if path.endswith("/favorite") and path.startswith("/api/games/"):
                        game_id = path.split("/")[3]
                        if not game_id:
                            raise ValueError("Identificador de juego no válido.")
                        game = server.library.toggle_favorite(game_id)
                        self._json({"ok": True, "game": game})
                        return
                    if path.endswith("/launch") and path.startswith("/api/games/"):
                        game_id = path.split("/")[3]
                        if not game_id:
                            raise ValueError("Identificador de juego no válido.")
                        result = server.library.launch(game_id)
                        self._json({"ok": True, **result})
                        return
                    if path == "/api/scan":
                        self._json({"ok": True, "result": server.library.scan()})
                        return
                    if path == "/api/game-folders":
                        item = server.library.add_game_folder(str(payload.get("path") or ""), str(payload.get("platform") or "PC"))
                        self._json({"ok": True, "folder": item}, 201)
                        return
                    if path == "/api/emulators":
                        item = server.library.add_emulator(payload)
                        self._json({"ok": True, "emulator": item}, 201)
                        return
                    if path.endswith("/update") and path.startswith("/api/emulators/"):
                        emulator_id = path.split("/")[3]
                        item = server.library.update_emulator(emulator_id, payload)
                        self._json({"ok": True, "emulator": item})
                        return
                    if path.endswith("/test") and path.startswith("/api/emulators/"):
                        emulator_id = path.split("/")[3]
                        self._json({"ok": True, "result": server.library.test_emulator(emulator_id)})
                        return
                    if path == "/api/default-emulator":
                        settings = server.library.set_default_emulator(str(payload.get("platform") or ""), payload.get("emulator_id") or None)
                        self._json({"ok": True, "settings": settings})
                        return
                    if path == "/api/collections":
                        item = server.library.save_collection(payload)
                        self._json({"ok": True, "collection": item})
                        return
                    if path == "/api/profiles":
                        item = server.library.add_profile(str(payload.get("name") or ""), str(payload.get("avatar") or "orbit"))
                        self._json({"ok": True, "profile": item}, 201)
                        return
                    if path == "/api/profiles/select":
                        profiles = server.library.select_profile(str(payload.get("id") or ""))
                        self._json({"ok": True, "profiles": profiles})
                        return
                    if path.endswith("/update") and path.startswith("/api/profiles/"):
                        profile_id = path.split("/")[3]
                        item = server.library.update_profile(profile_id, payload)
                        self._json({"ok": True, "profile": item})
                        return
                    if path.endswith("/avatar") and path.startswith("/api/profiles/"):
                        profile_id = path.split("/")[3]
                        item = server.library.set_profile_avatar(profile_id, str(payload.get("path") or ""))
                        self._json({"ok": True, "profile": item})
                        return
                    if path.endswith("/avatar-reset") and path.startswith("/api/profiles/"):
                        profile_id = path.split("/")[3]
                        item = server.library.reset_profile_avatar(profile_id, str(payload.get("avatar") or "orbit"))
                        self._json({"ok": True, "profile": item})
                        return
                    if path == "/api/emulator-sites/open":
                        result = open_emulator_site(str(payload.get("id") or ""))
                        self._json({"ok": True, "result": result})
                        return
                    if path == "/api/emulators/install/prepare":
                        self._json({"ok": True, "result": server.emulator_installer.prepare_all_folders()})
                        return
                    if path == "/api/emulators/install/all":
                        result = server.emulator_installer.install_all()
                        registered = []
                        for item in result.get("results", []):
                            if item.get("status") in {"installed", "already-installed", "downloaded"} and item.get("executable"):
                                registered.extend(server._register_installed_emulator(str(item.get("id")), item))
                        result["registered"] = len(registered)
                        self._json({"ok": True, "result": result})
                        return
                    if path.startswith("/api/emulators/install/"):
                        package_id = path.rsplit("/", 1)[-1]
                        result = server.emulator_installer.install(package_id)
                        result["registered"] = server._register_installed_emulator(package_id, result) if result.get("executable") else []
                        self._json({"ok": True, "result": result})
                        return
                    if path == "/api/orbitpack/export/start":
                        job_id = server._start_export_job(dict(payload))
                        self._json({"ok": True, "job_id": job_id}, 202)
                        return
                    if path == "/api/orbitpack/export":
                        game_ids = payload.get("game_ids") if isinstance(payload.get("game_ids"), list) else None
                        result = server.library.create_orbitpack(
                            game_ids=game_ids,
                            include_game_files=payload.get("include_game_files", payload.get("include_games", True)) is not False,
                            include_emulators=payload.get("include_emulators") is not False,
                            include_media=payload.get("include_media") is not False,
                            include_saves=bool(payload.get("include_saves")),
                            name=str(payload.get("name") or "") or None,
                            include_games=payload.get("include_games") is not False,
                            include_configuration=bool(payload.get("include_configuration")),
                            include_other=bool(payload.get("include_other")),
                            full_profile=bool(payload.get("full_profile")),
                        )
                        self._json({"ok": True, "result": result})
                        return
                    if path == "/api/orbitpack/inspect":
                        candidate = str(payload.get("path") or "")
                        try:
                            result = server.library.inspect_orbitpack(candidate)
                        except Exception:
                            server._discard_staged_pack(candidate)
                            raise
                        self._json({"ok": True, "result": result})
                        return
                    if path == "/api/orbitpack/import/start":
                        raw = payload.get("components")
                        if not isinstance(raw, list) or not raw:
                            raise ValueError("Selecciona al menos un componente.")
                        job_id = server._start_import_job(dict(payload))
                        self._json({"ok": True, "job_id": job_id}, 202)
                        return
                    if path == "/api/orbitpack/import":
                        raw_components = payload.get("components")
                        if isinstance(raw_components, str):
                            raw_components = [part.strip() for part in raw_components.split(",") if part.strip()]
                        components = raw_components if isinstance(raw_components, list) else None
                        result = server.library.import_orbitpack(
                            str(payload.get("path") or ""),
                            str(payload.get("conflict") or "skip"),
                            components=components,
                            profile_strategy=str(payload.get("profile_strategy") or "merge-active"),
                            config_conflict=str(payload.get("config_conflict") or "keep-existing"),
                        )
                        self._json({"ok": True, "result": result})
                        return
                    if path == "/api/import/folder-preview":
                        items = server.library.folder_import_preview(str(payload.get("path") or ""))
                        self._json({"ok": True, "items": items})
                        return
                    if path == "/api/import/apply":
                        items = payload.get("items") if isinstance(payload.get("items"), list) else []
                        result = server.library.import_items(items)
                        self._json({"ok": True, "result": result})
                        return
                    if path == "/api/recovery/create":
                        self._json({"ok": True, "result": server.library.create_recovery_point(str(payload.get("reason") or "manual"))})
                        return
                    if path == "/api/recovery/restore":
                        self._json({"ok": True, "result": server.library.restore_recovery_point(str(payload.get("path") or ""), bool(payload.get("confirmed")))})
                        return
                    if path == "/api/organization/platform":
                        settings = server.library.set_platform_destination(str(payload.get("platform") or ""), str(payload.get("path") or ""))
                        self._json({"ok": True, "settings": settings})
                        return
                    if path == "/api/organization/emulator":
                        settings = server.library.set_emulator_destination(str(payload.get("platform") or ""), str(payload.get("path") or ""))
                        self._json({"ok": True, "settings": settings})
                        return
                    if path == "/api/themes":
                        theme = server.library.save_custom_theme(payload)
                        self._json({"ok": True, "theme": theme}, 201)
                        return
                    if path == "/api/themes/import":
                        theme = server.library.import_custom_theme(str(payload.get("path") or ""))
                        self._json({"ok": True, "theme": theme}, 201)
                        return
                    if path == "/api/themes/export":
                        result = server.library.export_custom_theme(str(payload.get("id") or ""))
                        self._json({"ok": True, "result": result})
                        return
                    if path == "/api/ai/ask":
                        result = server.library.ask_ai(str(payload.get("query") or ""))
                        self._json({"ok": True, "result": result})
                        return
                    if path == "/api/settings":
                        settings = server.library.save_settings(payload)
                        self._json({"ok": True, "settings": settings})
                        return
                    if path == "/api/shutdown":
                        self._json({"ok": True})
                        threading.Thread(target=server.stop, daemon=True).start()
                        return
                    if path.startswith("/api/dialog/"):
                        result = open_dialog(path.split("/")[-1], suggested_name=str(payload.get("suggested_name") or "") or None)
                        self._json({"ok": True, "path": result})
                        return
                    self._json({"ok": False, "error": "Endpoint no encontrado."}, HTTPStatus.NOT_FOUND)
                except (ValueError, KeyError) as exc:
                    self._error(exc, 400)
                except Exception as exc:
                    LOGGER.exception("Error atendiendo POST %s", self.path)
                    self._error(exc, 500)

            def do_PATCH(self) -> None:
                if not self._guard_local_host():
                    return
                path = urlparse(self.path).path
                try:
                    payload = self._body()
                    if path.startswith("/api/games/"):
                        game_id = path.split("/")[3]
                        if not game_id:
                            raise ValueError("Identificador de juego no válido.")
                        game = server.library.update_game(game_id, payload)
                        self._json({"ok": True, "game": game})
                        return
                    self._json({"ok": False, "error": "Endpoint no encontrado."}, HTTPStatus.NOT_FOUND)
                except (ValueError, KeyError) as exc:
                    self._error(exc, 400)
                except Exception as exc:
                    LOGGER.exception("Error atendiendo PATCH %s", self.path)
                    self._error(exc, 500)

            def do_DELETE(self) -> None:
                if not self._guard_local_host():
                    return
                path = urlparse(self.path).path
                try:
                    if path.endswith("/cover") and path.startswith("/api/games/"):
                        game_id = path.split("/")[3]
                        if not game_id:
                            raise ValueError("Identificador de juego no válido.")
                        game = server.library.remove_game_cover(game_id)
                        self._json({"ok": True, "game": game})
                        return
                    if "/media/" in path and path.startswith("/api/games/"):
                        parts = path.split("/")
                        if len(parts) < 6:
                            raise ValueError("Ruta de imagen no válida.")
                        game_id, kind = parts[3], parts[5]
                        parsed = urlparse(self.path)
                        query = parse_qs(parsed.query)
                        index = int(query.get("index", ["-1"])[0]) if kind == "screenshot" else None
                        game = server.library.remove_game_media(game_id, kind, index)
                        self._json({"ok": True, "game": game})
                        return
                    if path.startswith("/api/games/"):
                        game_id = path.split("/")[3]
                        if not game_id:
                            raise ValueError("Identificador de juego no válido.")
                        server.library.remove_game(game_id)
                        self._json({"ok": True})
                        return
                    if path.startswith("/api/emulators/"):
                        emulator_id = path.split("/")[3]
                        if not emulator_id:
                            raise ValueError("Identificador de emulador no válido.")
                        server.library.delete_emulator(emulator_id)
                        self._json({"ok": True})
                        return
                    if path.startswith("/api/profiles/"):
                        profile_id = path.split("/")[3]
                        if not profile_id:
                            raise ValueError("Identificador de perfil no válido.")
                        parsed = urlparse(self.path)
                        query = parse_qs(parsed.query)
                        confirmed = query.get("confirmed", ["false"])[0].lower() == "true"
                        server.library.delete_profile(profile_id, confirmed=confirmed)
                        self._json({"ok": True})
                        return
                    if path.startswith("/api/collections/"):
                        collection_id = path.split("/")[3]
                        if not collection_id:
                            raise ValueError("Identificador de colección no válido.")
                        server.library.delete_collection(collection_id)
                        self._json({"ok": True})
                        return
                    self._json({"ok": False, "error": "Endpoint no encontrado."}, HTTPStatus.NOT_FOUND)
                except (ValueError, KeyError) as exc:
                    self._error(exc, 400)
                except Exception as exc:
                    LOGGER.exception("Error atendiendo DELETE %s", self.path)
                    self._error(exc, 500)

            def _serve_static(self, request_path: str) -> None:
                clean = request_path.lstrip("/") or "index.html"
                target = (server.static_dir / clean).resolve()
                if server.static_dir != target and server.static_dir not in target.parents:
                    self.send_error(HTTPStatus.FORBIDDEN)
                    return
                if not target.exists() or target.is_dir():
                    target = server.static_dir / "index.html"
                self._serve_file(target)

            def _serve_file(self, target: Path, *, media: bool = False) -> None:
                if not target.exists() or not target.is_file():
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                data = target.read_bytes()
                ctype, _ = mimetypes.guess_type(str(target))
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", ctype or "application/octet-stream")
                self.send_header("Content-Length", str(len(data)))
                self._security_headers("private, max-age=31536000, immutable" if media else "no-store")
                if target.suffix.lower() in {".html", ".js"}:
                    self.send_header(
                        "Content-Security-Policy",
                        "default-src 'self'; img-src 'self' data: https://steamgriddb.com https://*.steamgriddb.com; style-src 'self' 'unsafe-inline'; "
                        "script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
                    )
                self.end_headers()
                self.wfile.write(data)

        self.httpd = ThreadingHTTPServer((host, port), Handler)
        self.httpd.daemon_threads = True
        self._running.set()
        actual_host, actual_port = self.httpd.server_address[:2]
        thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        thread.start()
        return str(actual_host), int(actual_port)

    @property
    def is_running(self) -> bool:
        return self._running.is_set() and self.httpd is not None

    def stop(self) -> None:
        with self._lifecycle_lock:
            httpd = self.httpd
            if httpd is None:
                self._running.clear()
                return
            self._running.clear()
            self.httpd = None
        httpd.shutdown()
        httpd.server_close()
