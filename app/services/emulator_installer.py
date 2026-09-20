from __future__ import annotations

import io
import json
import os
import re
import shutil
import ssl
import tempfile
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.paths import PortablePaths


@dataclass(frozen=True)
class EmulatorPackage:
    id: str
    name: str
    platform: str
    folder: str
    website: str | None
    github_repo: str | None = None
    executable_hints: tuple[str, ...] = ()
    auto_install: bool = False
    notes: str = ""
    orbit_platforms: tuple[str, ...] = ()


PACKAGES: tuple[EmulatorPackage, ...] = (
    EmulatorPackage("mesen", "Mesen CE", "NES / SNES / GB / GBA y más", "Mesen", "https://github.com/nesdev-org/MesenCE", "nesdev-org/MesenCE", ("Mesen.exe",), True, "Proyecto comunitario actual recomendado por el repositorio original de Mesen.", ("NES", "SNES", "Game Boy", "Game Boy Color", "Game Boy Advance")),
    EmulatorPackage("snes9x", "Snes9x", "SNES / Super Famicom", "Snes9x", "https://www.snes9x.com/", "snes9xgit/snes9x", ("snes9x-x64.exe", "snes9x.exe"), True, "", ("SNES",)),
    EmulatorPackage("project64", "Project64", "Nintendo 64", "Project64", "https://www.pj64-emu.com/", "project64/project64", ("Project64.exe",), False, "La distribución oficial estable suele usar instalador; ORBIT prepara la carpeta y abre la web oficial.", ("Nintendo 64",)),
    EmulatorPackage("sameboy", "SameBoy", "Game Boy / Game Boy Color", "SameBoy", "https://sameboy.github.io/", "LIJI32/SameBoy", ("sameboy.exe", "SameBoy.exe"), True, "", ("Game Boy", "Game Boy Color")),
    EmulatorPackage("melonds", "melonDS", "Nintendo DS / DSi", "melonDS", "https://melonds.kuribo64.net/", "melonDS-emu/melonDS", ("melonDS.exe",), True, "", ("Nintendo DS",)),
    EmulatorPackage("azahar", "Azahar", "Nintendo 3DS", "Azahar", "https://azahar-emu.org/", "azahar-emu/azahar", ("azahar.exe", "azahar-room.exe"), True, "", ("Nintendo 3DS",)),
    EmulatorPackage("dolphin", "Dolphin", "GameCube / Wii", "Dolphin", "https://dolphin-emu.org/download/", "dolphin-emu/dolphin", ("Dolphin.exe",), False, "ORBIT usa la web oficial porque los binarios estables no siempre se publican como ZIP en GitHub Releases.", ("GameCube", "Wii")),
    EmulatorPackage("duckstation", "DuckStation", "PlayStation", "DuckStation", "https://www.duckstation.org/", "stenzek/duckstation", ("duckstation-qt-x64-ReleaseLTCG.exe", "duckstation-qt-x64-Release.exe", "duckstation.exe"), False, "La web oficial gestiona los binarios actuales.", ("PlayStation",)),
    EmulatorPackage("pcsx2", "PCSX2", "PlayStation 2", "PCSX2", "https://pcsx2.net/downloads/", "PCSX2/pcsx2", ("pcsx2-qt.exe", "pcsx2.exe"), True, "", ("PlayStation 2",)),
    EmulatorPackage("ppsspp", "PPSSPP", "PSP", "PPSSPP", "https://www.ppsspp.org/downloads/", "hrydgard/ppsspp", ("PPSSPPWindows64.exe", "PPSSPPWindows.exe"), True, "", ("PSP",)),
    EmulatorPackage("flycast", "Flycast", "Dreamcast / Naomi / Atomiswave", "Flycast", "https://github.com/flyinghead/flycast/releases", "flyinghead/flycast", ("flycast.exe",), True, "", ("Dreamcast", "Arcade")),
    EmulatorPackage("kega", "Kega Fusion", "Mega Drive / Master System / Game Gear / Sega CD / 32X", "KegaFusion", None, None, ("Fusion.exe",), False, "Proyecto legado: ORBIT no instala desde mirrors no verificados.", ("Mega Drive",)),
    EmulatorPackage("mame", "MAME", "Arcade", "MAME", "https://www.mamedev.org/release.html", "mamedev/mame", ("mame.exe",), False, "MAME distribuye paquetes oficiales que pueden no ser ZIP portable.", ("Arcade",)),
    EmulatorPackage("eden", "Eden", "Nintendo Switch", "Eden", "https://eden-emu.dev/", None, ("eden.exe", "Eden.exe"), False, "Switch: configura únicamente tus propios juegos/firmware/claves obtenidos legalmente. ORBIT no los distribuye.", ("Nintendo Switch",)),
)


def package_catalog() -> list[dict[str, Any]]:
    return [
        {
            "id": x.id,
            "name": x.name,
            "platform": x.platform,
            "folder": x.folder,
            "website": x.website,
            "auto_install": x.auto_install,
            "notes": x.notes,
            "orbit_platforms": list(x.orbit_platforms),
            "installed": False,
        }
        for x in PACKAGES
    ]


class EmulatorInstaller:
    def __init__(self, paths: PortablePaths) -> None:
        self.paths = paths

    def catalog(self) -> list[dict[str, Any]]:
        rows = package_catalog()
        root = self.paths.emulators
        for row in rows:
            pkg = self._package(str(row["id"]))
            folder = root / pkg.folder
            row["installed"] = bool(self._find_executable(folder, pkg))
            row["path"] = self.paths.encode(folder)
        return rows

    def prepare_all_folders(self) -> dict[str, Any]:
        created: list[str] = []
        self.paths.emulators.mkdir(parents=True, exist_ok=True)
        for pkg in PACKAGES:
            folder = self.paths.emulators / pkg.folder
            if not folder.exists():
                folder.mkdir(parents=True, exist_ok=True)
                created.append(pkg.id)
        return {"created": created, "total": len(PACKAGES)}

    def install(self, package_id: str) -> dict[str, Any]:
        pkg = self._package(package_id)
        folder = self.paths.emulators / pkg.folder
        folder.mkdir(parents=True, exist_ok=True)
        existing = self._find_executable(folder, pkg)
        if existing:
            return {"id": pkg.id, "status": "already-installed", "executable": self.paths.encode(existing)}
        if not pkg.auto_install or not pkg.github_repo:
            return {"id": pkg.id, "status": "manual", "website": pkg.website, "folder": self.paths.encode(folder), "message": pkg.notes or "Instalación manual desde la web oficial."}
        release = self._github_release(pkg.github_repo)
        asset = self._select_windows_zip(release.get("assets") or [])
        if asset is None:
            return {"id": pkg.id, "status": "manual", "website": pkg.website, "folder": self.paths.encode(folder), "message": "La versión actual no ofrece un ZIP Windows reconocible. Usa la web oficial."}
        data = self._download(str(asset["browser_download_url"]), max_bytes=600 * 1024 * 1024)
        digest = __import__("hashlib").sha256(data).hexdigest()
        self._safe_extract_zip(data, folder)
        exe = self._find_executable(folder, pkg)
        return {
            "id": pkg.id,
            "status": "installed" if exe else "downloaded",
            "release": release.get("tag_name") or release.get("name"),
            "asset": asset.get("name"),
            "sha256": digest,
            "folder": self.paths.encode(folder),
            "executable": self.paths.encode(exe) if exe else None,
        }

    def install_all(self) -> dict[str, Any]:
        self.prepare_all_folders()
        results: list[dict[str, Any]] = []
        for pkg in PACKAGES:
            try:
                results.append(self.install(pkg.id))
            except Exception as exc:
                results.append({"id": pkg.id, "status": "error", "message": str(exc)})
        return {
            "results": results,
            "installed": sum(1 for x in results if x.get("status") in {"installed", "already-installed"}),
            "manual": sum(1 for x in results if x.get("status") == "manual"),
            "errors": sum(1 for x in results if x.get("status") == "error"),
        }

    def package(self, package_id: str) -> EmulatorPackage:
        return self._package(package_id)

    def _package(self, package_id: str) -> EmulatorPackage:
        pkg = next((x for x in PACKAGES if x.id == str(package_id)), None)
        if pkg is None:
            raise ValueError("Emulador no reconocido por ORBIT.")
        return pkg

    @staticmethod
    def _github_release(repo: str) -> dict[str, Any]:
        req = urllib.request.Request(
            f"https://api.github.com/repos/{repo}/releases/latest",
            headers={"Accept": "application/vnd.github+json", "User-Agent": "ORBIT-Portable-Launcher/0.4"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30, context=ssl.create_default_context()) as response:
                raw = response.read(4 * 1024 * 1024)
        except urllib.error.HTTPError as exc:
            raise ValueError(f"No se pudo consultar la versión oficial ({exc.code}).") from exc
        except OSError as exc:
            raise ValueError("No hay conexión con la fuente oficial del emulador.") from exc
        return json.loads(raw.decode("utf-8"))

    @staticmethod
    def _select_windows_zip(assets: list[dict[str, Any]]) -> dict[str, Any] | None:
        candidates: list[tuple[int, dict[str, Any]]] = []
        for asset in assets:
            name = str(asset.get("name") or "")
            low = name.casefold()
            if not low.endswith(".zip"):
                continue
            if any(x in low for x in ("source", "symbols", "debug", "android", "linux", "mac", "osx", "arm64", "aarch64")):
                continue
            score = 0
            if any(x in low for x in ("windows", "win64", "win-x64", "x64")):
                score += 20
            if any(x in low for x in ("portable", "qt", "release", "msvc")):
                score += 4
            candidates.append((score, asset))
        if not candidates:
            return None
        candidates.sort(key=lambda item: (item[0], int(item[1].get("size") or 0)), reverse=True)
        return candidates[0][1]

    @staticmethod
    def _download(url: str, max_bytes: int) -> bytes:
        req = urllib.request.Request(url, headers={"User-Agent": "ORBIT-Portable-Launcher/0.4"})
        try:
            with urllib.request.urlopen(req, timeout=90, context=ssl.create_default_context()) as response:
                content_length = int(response.headers.get("Content-Length") or 0)
                if content_length > max_bytes:
                    raise ValueError("La descarga supera el límite de seguridad de ORBIT.")
                out = io.BytesIO()
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
                    if out.tell() > max_bytes:
                        raise ValueError("La descarga supera el límite de seguridad de ORBIT.")
                return out.getvalue()
        except urllib.error.URLError as exc:
            raise ValueError("No se pudo descargar desde la fuente oficial.") from exc

    @staticmethod
    def _safe_extract_zip(data: bytes, destination: Path) -> None:
        destination.mkdir(parents=True, exist_ok=True)
        root = destination.resolve()
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for info in archive.infolist():
                name = info.filename.replace("\\", "/")
                if not name or name.startswith("/") or re.match(r"^[A-Za-z]:", name):
                    raise ValueError("El ZIP del emulador contiene una ruta no segura.")
                target = (root / name).resolve()
                try:
                    target.relative_to(root)
                except ValueError as exc:
                    raise ValueError("El ZIP del emulador intenta escribir fuera de su carpeta.") from exc
            archive.extractall(root)

    @staticmethod
    def _find_executable(folder: Path, pkg: EmulatorPackage) -> Path | None:
        if not folder.exists():
            return None
        hints = {x.casefold() for x in pkg.executable_hints}
        for path in folder.rglob("*.exe"):
            if path.name.casefold() in hints:
                return path
        return None
