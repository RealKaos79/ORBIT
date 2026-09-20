from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any

from .paths import PortablePaths


class JsonStore:
    """Small, dependency-free JSON persistence with atomic writes and rotating backups."""

    def __init__(self, paths: PortablePaths, base_dir: Path | None = None, backup_dir: Path | None = None) -> None:
        self.paths = paths
        self.paths.ensure_layout()
        self.base_dir = Path(base_dir) if base_dir is not None else self.paths.data
        self.backup_dir = Path(backup_dir) if backup_dir is not None else self.paths.backups / "config"
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()

    def _path(self, name: str) -> Path:
        return self.base_dir / f"{name}.json"

    def load(self, name: str, default: Any) -> Any:
        path = self._path(name)
        with self._lock:
            if not path.exists():
                return default
            try:
                with path.open("r", encoding="utf-8") as handle:
                    return json.load(handle)
            except (json.JSONDecodeError, OSError):
                recovery = self._latest_backup(name)
                if recovery:
                    try:
                        with recovery.open("r", encoding="utf-8") as handle:
                            return json.load(handle)
                    except (json.JSONDecodeError, OSError):
                        pass
                return default

    def save(self, name: str, value: Any) -> None:
        path = self._path(name)
        with self._lock:
            if path.exists():
                self._backup(name, path)
            fd, tmp_name = tempfile.mkstemp(prefix=f".{name}-", suffix=".tmp", dir=str(path.parent))
            try:
                with open(fd, "w", encoding="utf-8", closefd=True) as handle:
                    json.dump(value, handle, ensure_ascii=False, indent=2)
                    handle.flush()
                    os.fsync(handle.fileno())
                Path(tmp_name).replace(path)
                self._sync_directory(path.parent)
            finally:
                temp = Path(tmp_name)
                if temp.exists():
                    temp.unlink(missing_ok=True)
            try:
                self._prune_backups(name, keep=8)
            except OSError:
                # The main save has already succeeded. A pruning failure must not
                # make the API report that the configuration was not saved.
                pass

    def _sync_directory(self, directory: Path) -> None:
        if os.name == "nt":
            return
        try:
            fd = os.open(str(directory), os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        except OSError:
            pass

    def _backup(self, name: str, path: Path) -> None:
        backup_dir = self.backup_dir
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        shutil.copy2(path, backup_dir / f"{name}-{stamp}.json")

    def _latest_backup(self, name: str) -> Path | None:
        backup_dir = self.backup_dir
        candidates = sorted(backup_dir.glob(f"{name}-*.json"), reverse=True)
        return candidates[0] if candidates else None

    def _prune_backups(self, name: str, keep: int) -> None:
        backup_dir = self.backup_dir
        candidates = sorted(backup_dir.glob(f"{name}-*.json"), reverse=True)
        for path in candidates[keep:]:
            path.unlink(missing_ok=True)
