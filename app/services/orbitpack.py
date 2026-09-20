from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Any, Callable

from app.core.paths import PortablePaths
from app.services.secrets import scrub_sensitive

PACK_VERSION = 2
MAX_MANIFEST = 8 * 1024 * 1024
MAX_EXTRACT_BYTES = 32 * 1024 * 1024 * 1024
MAX_MEMBERS = 100000


def safe_name(value: str) -> str:
    out = "".join(ch if ch.isalnum() or ch in " ._-()[]" else "_" for ch in str(value)).strip(" .")
    return out[:120] or "item"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


class OrbitPackService:
    def __init__(self, paths: PortablePaths) -> None:
        self.paths = paths

    def create(
        self,
        manifest: dict[str, Any],
        files: list[tuple[Path, str]],
        name: str | None = None,
        *,
        destination: str | Path | None = None,
        progress: Callable[[dict[str, Any]], None] | None = None,
    ) -> Path:
        self.paths.exports.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        filename = safe_name(name or f"ORBIT-Pack-{stamp}") + ".orbitpack"
        if destination is None:
            destination_path = (self.paths.exports / filename).resolve()
            destination_path.relative_to(self.paths.exports.resolve())
        else:
            destination_path = Path(destination).expanduser().resolve()
            if destination_path.suffix.casefold() != ".orbitpack":
                destination_path = destination_path.with_suffix(".orbitpack")
            if not destination_path.parent.exists() or not destination_path.parent.is_dir():
                raise ValueError("La carpeta elegida para exportar ya no existe.")
        temp = destination_path.with_name(destination_path.name + ".tmp")
        checksums: dict[str, str] = {}
        seen_members: set[str] = set()
        valid_files: list[tuple[Path, str, int]] = []
        total_bytes = 0
        for src, arc in files:
            if not src.exists() or not src.is_file():
                if str(arc).replace("\\", "/").startswith("payload/games/"):
                    raise ValueError(f"La ROM dejó de estar disponible durante la exportación: {src.name}")
                continue
            arc = arc.replace("\\", "/").lstrip("/")
            self._validate_member(arc)
            if arc in seen_members:
                raise ValueError(f"El paquete intenta incluir dos veces el mismo archivo: {arc}")
            seen_members.add(arc)
            try:
                size = max(0, int(src.stat().st_size))
            except OSError:
                size = 0
            valid_files.append((src, arc, size))
            total_bytes += size

        started = time.monotonic()
        processed = 0

        def emit(phase: str, current: str | None = None, *, finished: bool = False) -> None:
            if progress is None:
                return
            if finished:
                percent = 1.0
            elif total_bytes > 0:
                percent = min(0.985, max(0.0, processed / total_bytes))
            else:
                percent = 0.6 if phase == "manifest" else 0.05
            elapsed = max(0.001, time.monotonic() - started)
            rate = processed / elapsed if processed > 0 else 0.0
            eta = ((total_bytes - processed) / rate) if rate > 0 and total_bytes > processed else (0.0 if finished else None)
            progress({
                "phase": phase,
                "current": current,
                "processed_bytes": processed,
                "total_bytes": total_bytes,
                "percent": percent,
                "eta_seconds": eta,
            })

        try:
            emit("packing")
            with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED, allowZip64=True) as z:
                for src, arc, _size in valid_files:
                    h = hashlib.sha256()
                    with src.open("rb") as source, z.open(arc, "w") as target:
                        while True:
                            chunk = source.read(1024 * 1024)
                            if not chunk:
                                break
                            h.update(chunk)
                            target.write(chunk)
                            processed += len(chunk)
                            emit("packing", arc)
                    checksums[arc] = h.hexdigest()
                emit("manifest")
                payload = scrub_sensitive(dict(manifest))
                payload.update({"format": "ORBITPACK", "version": PACK_VERSION, "created_at": int(time.time()), "checksums": checksums})
                raw = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
                if len(raw) > MAX_MANIFEST:
                    raise ValueError("El manifiesto del ORBIT Pack es demasiado grande.")
                z.writestr("manifest.json", raw)
                z.writestr("manifest.sha256", hashlib.sha256(raw).hexdigest())
            os.replace(temp, destination_path)
            emit("done", finished=True)
            return destination_path
        finally:
            temp.unlink(missing_ok=True)

    def inspect(self, pack_path: str | Path, verify_files: bool = True,
                progress: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
        path = Path(pack_path).expanduser().resolve()
        if not path.is_file() or path.suffix.casefold() != ".orbitpack":
            raise ValueError("Selecciona un archivo .orbitpack válido.")
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            if len(names) > MAX_MEMBERS or len(names) != len(set(names)):
                raise ValueError("El paquete contiene demasiados archivos o nombres duplicados.")
            total = sum(max(0, info.file_size) for info in z.infolist() if not info.is_dir())
            if total > MAX_EXTRACT_BYTES:
                raise ValueError("El paquete supera el tamaño máximo de extracción permitido.")
            for item in z.infolist():
                if (item.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError("El paquete contiene enlaces no permitidos.")
            for name in names:
                self._validate_member(name)
            if "manifest.json" not in names or "manifest.sha256" not in names:
                raise ValueError("El paquete no contiene un manifiesto ORBIT válido.")
            raw = z.read("manifest.json")
            if len(raw) > MAX_MANIFEST:
                raise ValueError("Manifiesto demasiado grande.")
            expected = z.read("manifest.sha256").decode("ascii", "ignore").strip()
            if hashlib.sha256(raw).hexdigest() != expected:
                raise ValueError("El manifiesto del paquete está corrupto o fue modificado.")
            manifest = json.loads(raw.decode("utf-8"))
            version = int(manifest.get("version") or 0) if isinstance(manifest, dict) else 0
            if not isinstance(manifest, dict) or manifest.get("format") != "ORBITPACK" or version not in {1, 2, PACK_VERSION}:
                raise ValueError("Versión de ORBIT Pack no compatible.")
            checksums = manifest.get("checksums") or {}
            if not isinstance(checksums, dict):
                raise ValueError("La tabla de integridad del paquete no es válida.")
            if verify_files:
                done = 0
                payload_members = {n for n in names if n not in {"manifest.json", "manifest.sha256"} and not n.endswith("/")}
                unchecked = payload_members.difference(str(k) for k in checksums)
                if unchecked:
                    raise ValueError("El paquete contiene archivos sin firma SHA-256.")
                for member, digest in checksums.items():
                    if member not in names:
                        raise ValueError(f"Falta un archivo del paquete: {member}")
                    h = hashlib.sha256()
                    with z.open(member) as f:
                        for chunk in iter(lambda: f.read(1024 * 1024), b""):
                            h.update(chunk)
                            done += len(chunk)
                            if progress:
                                progress({"phase": "verifying", "processed_bytes": done,
                                          "total_bytes": total, "current": member,
                                          "percent": min(1., done / max(1, total))})
                    if h.hexdigest() != digest:
                        raise ValueError(f"El archivo {member} no supera la comprobación de integridad.")
                if progress:
                    progress({"phase": "verifying", "processed_bytes": total,
                              "total_bytes": total, "current": None, "percent": 1.})
            return {"path": str(path), "size": path.stat().st_size, "manifest": manifest}

    def extract(self, pack_path: str | Path,
                progress: Callable[[dict[str, Any]], None] | None = None) -> tuple[tempfile.TemporaryDirectory[str], Path, dict[str, Any]]:
        def verify_event(info: dict[str, Any]) -> None:
            if progress:
                progress({**info, "percent": 0.30 * info["percent"]})

        info = self.inspect(pack_path, verify_files=True, progress=verify_event if progress else None)
        temp = tempfile.TemporaryDirectory(prefix="orbitpack-")
        root = Path(temp.name).resolve()
        try:
            with zipfile.ZipFile(Path(pack_path).resolve()) as z:
                total = sum(item.file_size for item in z.infolist() if not item.is_dir())
                done = 0
                for member in z.infolist():
                    self._validate_member(member.filename)
                    target = (root / member.filename).resolve()
                    target.relative_to(root)
                    if member.is_dir():
                        target.mkdir(parents=True, exist_ok=True)
                        continue
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with z.open(member) as source, target.open("wb") as output:
                        while True:
                            chunk = source.read(1024 * 1024)
                            if not chunk:
                                break
                            output.write(chunk)
                            done += len(chunk)
                            if progress:
                                progress({"phase": "extracting", "processed_bytes": done + total,
                                          "total_bytes": 2 * total, "current": member.filename,
                                          "percent": 0.30 + 0.30 * done / max(1, total)})
                if progress:
                    progress({"phase": "extracting", "processed_bytes": 2 * total,
                              "total_bytes": 2 * total, "current": None, "percent": 0.60})
            return temp, root, info["manifest"]
        except Exception:
            temp.cleanup()
            raise

    @staticmethod
    def _validate_member(name: str) -> None:
        normalized = str(name).replace("\\", "/")
        if normalized.startswith("/") or normalized.startswith("../") or "/../" in normalized or ":" in normalized.split("/")[0]:
            raise ValueError("El paquete contiene una ruta no segura.")
