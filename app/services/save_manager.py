from __future__ import annotations

import json
import os
import shutil
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from threading import RLock
from typing import Any

from app.core.paths import PortablePaths


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SaveManager:
    """Portable save backup/sync manager.

    Destructive restore/sync-to-PC operations always create a safety snapshot first.
    The original game files are never touched; this service only operates on a
    game's explicitly configured save_path and portable_save_path.
    """

    def __init__(self, paths: PortablePaths) -> None:
        self.paths = paths
        self._lock = RLock()
        self.backup_root = self.paths.backups / "saves"
        self.backup_root.mkdir(parents=True, exist_ok=True)
        self.profile_state_file = self.paths.data / "profile_save_state.json"

    def _safe_profile_id(self, profile_id: str | None) -> str:
        text = str(profile_id or "default")
        safe = "".join(ch for ch in text if ch.isalnum() or ch in "-_")
        return safe or "default"

    def _game_backup_dir(self, game_id: str, profile_id: str = "default") -> Path:
        safe = "".join(ch for ch in str(game_id) if ch.isalnum() or ch in "-_" )
        if not safe:
            raise ValueError("Identificador de juego no válido.")
        pid = self._safe_profile_id(profile_id)
        path = self.backup_root / safe if pid == "default" else self.backup_root / "profiles" / pid / safe
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _resolved_save(self, game: dict[str, Any]) -> Path:
        value = game.get("save_path")
        path = self.paths.decode(value) if value else None
        if path is None:
            raise ValueError("Configura primero la carpeta o archivo de partidas de este juego.")
        return path

    def portable_target(self, game: dict[str, Any], profile_id: str = "default") -> Path:
        value = game.get("portable_save_path")
        if value:
            path = self.paths.decode(value)
            if path is not None:
                return path
        pid = self._safe_profile_id(profile_id)
        if pid == "default":
            return self.paths.saves / str(game.get("id") or "unknown")
        return self.paths.saves / "profiles" / pid / str(game.get("id") or "unknown")

    def _zip_source(self, source: Path, archive: Path, metadata: dict[str, Any]) -> None:
        archive.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".orbit-save-", suffix=".zip", dir=str(archive.parent))
        os.close(fd)
        tmp_path = Path(tmp)
        try:
            with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as zf:
                zf.writestr("ORBIT_BACKUP.json", json.dumps(metadata, ensure_ascii=False, indent=2))
                if source.is_file():
                    zf.write(source, f"data/{source.name}")
                else:
                    for path in source.rglob("*"):
                        if path.is_file():
                            rel = path.relative_to(source).as_posix()
                            zf.write(path, f"data/{rel}")
            os.replace(tmp_path, archive)
        finally:
            tmp_path.unlink(missing_ok=True)

    def create_backup(self, game: dict[str, Any], reason: str = "manual", profile_id: str = "default") -> dict[str, Any]:
        with self._lock:
            source = self._resolved_save(game)
            if not source.exists():
                raise ValueError("La ruta de partidas configurada no existe todavía.")
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            backup_id = f"{stamp}-{uuid.uuid4().hex[:8]}"
            archive = self._game_backup_dir(str(game.get("id")), profile_id) / f"{backup_id}.zip"
            metadata = {
                "version": 1,
                "backup_id": backup_id,
                "game_id": game.get("id"),
                "game_name": game.get("name"),
                "profile_id": self._safe_profile_id(profile_id),
                "created_at": utc_now(),
                "reason": reason,
                "source_type": "file" if source.is_file() else "directory",
                "source_name": source.name,
            }
            self._zip_source(source, archive, metadata)
            return {
                **metadata,
                "size_bytes": archive.stat().st_size,
                "archive": self.paths.encode(archive),
            }

    def list_backups(self, game_id: str, profile_id: str = "default") -> list[dict[str, Any]]:
        with self._lock:
            directory = self._game_backup_dir(game_id, profile_id)
            result: list[dict[str, Any]] = []
            for archive in sorted(directory.glob("*.zip"), reverse=True):
                try:
                    with zipfile.ZipFile(archive, "r") as zf:
                        meta = json.loads(zf.read("ORBIT_BACKUP.json").decode("utf-8"))
                    if not isinstance(meta, dict):
                        continue
                    result.append({
                        **meta,
                        "size_bytes": archive.stat().st_size,
                        "archive": self.paths.encode(archive),
                    })
                except (OSError, ValueError, KeyError, zipfile.BadZipFile, json.JSONDecodeError):
                    result.append({
                        "backup_id": archive.stem,
                        "created_at": None,
                        "reason": "corrupt",
                        "size_bytes": archive.stat().st_size if archive.exists() else 0,
                        "archive": self.paths.encode(archive),
                        "corrupt": True,
                    })
            return result

    def _safe_extract(self, archive: Path, destination: Path) -> Path:
        destination.mkdir(parents=True, exist_ok=True)
        data_root = destination / "data"
        with zipfile.ZipFile(archive, "r") as zf:
            for info in zf.infolist():
                posix = PurePosixPath(info.filename)
                if posix.is_absolute() or ".." in posix.parts:
                    raise ValueError("El backup contiene una ruta insegura.")
                target = (destination / Path(*posix.parts)).resolve()
                try:
                    target.relative_to(destination.resolve())
                except ValueError as exc:
                    raise ValueError("El backup intenta escribir fuera de su carpeta temporal.") from exc
            zf.extractall(destination)
        if not data_root.exists():
            raise ValueError("El backup no contiene datos restaurables.")
        return data_root

    def restore_backup(self, game: dict[str, Any], backup_id: str, confirmed: bool = False, profile_id: str = "default") -> dict[str, Any]:
        if not confirmed:
            raise ValueError("La restauración necesita confirmación explícita.")
        with self._lock:
            target = self._resolved_save(game)
            backups = self.list_backups(str(game.get("id")), profile_id)
            item = next((b for b in backups if b.get("backup_id") == backup_id and not b.get("corrupt")), None)
            if item is None:
                raise KeyError("Backup no encontrado")
            archive = self.paths.decode(item.get("archive"))
            if not archive or not archive.exists():
                raise KeyError("Archivo de backup no encontrado")

            safety = None
            if target.exists():
                safety = self.create_backup(game, reason="pre-restore", profile_id=profile_id)

            temp_parent = target.parent if target.parent.exists() else self.paths.data
            temp_root = Path(tempfile.mkdtemp(prefix=".orbit-restore-", dir=str(temp_parent)))
            old = target.with_name(f".{target.name}.orbit-old-{uuid.uuid4().hex[:8]}")
            moved_old = False
            try:
                extracted = self._safe_extract(archive, temp_root)
                source_type = str(item.get("source_type") or "directory")
                if source_type == "file":
                    candidates = [p for p in extracted.iterdir() if p.is_file()]
                    if len(candidates) != 1:
                        raise ValueError("El backup de archivo no tiene el formato esperado.")
                    incoming = candidates[0]
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if target.exists():
                        os.replace(target, old)
                        moved_old = True
                    os.replace(incoming, target)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if target.exists():
                        os.replace(target, old)
                        moved_old = True
                    os.replace(extracted, target)
                if moved_old:
                    if old.is_dir():
                        shutil.rmtree(old, ignore_errors=True)
                    else:
                        old.unlink(missing_ok=True)
                return {"restored": True, "backup": item, "safety_backup": safety}
            except Exception:
                if moved_old and old.exists() and not target.exists():
                    os.replace(old, target)
                raise
            finally:
                shutil.rmtree(temp_root, ignore_errors=True)

    def _copy_path(self, source: Path, target: Path) -> None:
        if not source.exists():
            raise ValueError(f"No existe la ruta de origen: {source}")
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_file():
            if target.exists() and target.is_dir():
                target = target / source.name
            tmp = target.with_name(f".{target.name}.orbit-copy-{uuid.uuid4().hex[:8]}")
            shutil.copy2(source, tmp)
            os.replace(tmp, target)
            return
        tmp = target.with_name(f".{target.name}.orbit-copy-{uuid.uuid4().hex[:8]}")
        if tmp.exists():
            shutil.rmtree(tmp, ignore_errors=True)
        shutil.copytree(source, tmp)
        if target.exists():
            old = target.with_name(f".{target.name}.orbit-old-{uuid.uuid4().hex[:8]}")
            os.replace(target, old)
            try:
                os.replace(tmp, target)
            except Exception:
                os.replace(old, target)
                raise
            if old.is_dir():
                shutil.rmtree(old, ignore_errors=True)
            else:
                old.unlink(missing_ok=True)
        else:
            os.replace(tmp, target)

    def _save_key(self, path: Path) -> str:
        try:
            value = str(path.resolve())
        except OSError:
            value = str(path.absolute())
        return value.casefold() if os.name == "nt" else value

    def _load_profile_state(self) -> dict[str, Any]:
        try:
            if self.profile_state_file.exists():
                value = json.loads(self.profile_state_file.read_text(encoding="utf-8"))
                return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            pass
        return {}

    def _save_profile_state(self, value: dict[str, Any]) -> None:
        self.profile_state_file.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".profile-save-state-", suffix=".tmp", dir=str(self.profile_state_file.parent))
        try:
            with open(fd, "w", encoding="utf-8", closefd=True) as handle:
                json.dump(value, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, self.profile_state_file)
        finally:
            Path(tmp).unlink(missing_ok=True)

    def prepare_profile_session(self, game: dict[str, Any], profile_id: str) -> dict[str, Any]:
        """Activate this profile's save copy in the game's real save location.

        This is only possible when save_path is configured. On the first use ORBIT
        adopts the existing PC save into the active profile. On later profile
        switches it preserves the previous owner's copy before swapping.
        """
        with self._lock:
            pc = self._resolved_save(game)
            usb = self.portable_target(game, profile_id)
            state = self._load_profile_state()
            key = self._save_key(pc)
            previous = state.get(key) if isinstance(state.get(key), dict) else None
            current_pid = self._safe_profile_id(profile_id)
            if previous and previous.get("profile_id") != current_pid and pc.exists():
                previous_path = self.paths.decode(previous.get("portable")) if previous.get("portable") else None
                if previous_path is not None:
                    self._copy_path(pc, previous_path)
            if not previous and pc.exists() and not usb.exists():
                self._copy_path(pc, usb)
            elif previous and previous.get("profile_id") != current_pid and usb.exists():
                self._copy_path(usb, pc)
            elif previous and previous.get("profile_id") != current_pid and not usb.exists():
                # New profile: start with no inherited save. Keep the prior copy safe,
                # then remove the live path so the game creates fresh data.
                if pc.exists():
                    if pc.is_dir():
                        shutil.rmtree(pc)
                    else:
                        pc.unlink(missing_ok=True)
            state[key] = {
                "profile_id": current_pid,
                "game_id": str(game.get("id") or "unknown"),
                "portable": self.paths.encode(usb),
                "updated_at": utc_now(),
            }
            self._save_profile_state(state)
            return {"activated": True, "profile_id": current_pid, "portable": self.paths.encode(usb)}

    def capture_profile_session(self, game: dict[str, Any], profile_id: str) -> dict[str, Any]:
        with self._lock:
            pc = self._resolved_save(game)
            usb = self.portable_target(game, profile_id)
            if not pc.exists():
                return {"captured": False, "reason": "missing"}
            self._copy_path(pc, usb)
            state = self._load_profile_state()
            key = self._save_key(pc)
            state[key] = {
                "profile_id": self._safe_profile_id(profile_id),
                "game_id": str(game.get("id") or "unknown"),
                "portable": self.paths.encode(usb),
                "updated_at": utc_now(),
            }
            self._save_profile_state(state)
            return {"captured": True, "portable": self.paths.encode(usb)}

    def sync(self, game: dict[str, Any], direction: str, confirmed: bool = False, profile_id: str = "default") -> dict[str, Any]:
        with self._lock:
            pc = self._resolved_save(game)
            usb = self.portable_target(game, profile_id)
            if direction == "pc_to_usb":
                self._copy_path(pc, usb)
                return {"direction": direction, "source": str(pc), "target": self.paths.encode(usb)}
            if direction == "usb_to_pc":
                if not confirmed:
                    raise ValueError("Copiar del USB al PC necesita confirmación explícita.")
                safety = self.create_backup(game, reason="pre-sync-usb-to-pc", profile_id=profile_id) if pc.exists() else None
                self._copy_path(usb, pc)
                return {"direction": direction, "source": self.paths.encode(usb), "target": str(pc), "safety_backup": safety}
            raise ValueError("Dirección de sincronización no válida.")
