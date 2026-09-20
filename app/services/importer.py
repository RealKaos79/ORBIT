from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from app.core.paths import PortablePaths


_QUOTED = re.compile(r'^\s*"(?P<key>[^"]+)"\s+"(?P<value>[^"]*)"\s*$')


def _parse_simple_vdf(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            match = _QUOTED.match(line)
            if match:
                result[match.group("key")] = match.group("value")
    except OSError:
        pass
    return result


class LocalImporter:
    def __init__(self, paths: PortablePaths) -> None:
        self.paths = paths

    def steam_roots(self) -> list[Path]:
        roots: list[Path] = []
        if os.name == "nt":
            try:
                import winreg
                for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
                    for key_name in (r"Software\Valve\Steam", r"Software\WOW6432Node\Valve\Steam"):
                        try:
                            with winreg.OpenKey(hive, key_name) as key:
                                for value_name in ("SteamPath", "InstallPath"):
                                    try:
                                        raw, _ = winreg.QueryValueEx(key, value_name)
                                        if raw:
                                            roots.append(Path(str(raw)))
                                    except OSError:
                                        pass
                        except OSError:
                            pass
            except ImportError:
                pass
            for env in ("PROGRAMFILES(X86)", "PROGRAMFILES"):
                base = os.environ.get(env)
                if base:
                    roots.append(Path(base) / "Steam")
        # Tests/dev can point at a fake Steam root.
        if os.environ.get("ORBIT_STEAM_ROOT"):
            roots.append(Path(os.environ["ORBIT_STEAM_ROOT"]))
        unique: list[Path] = []
        seen: set[str] = set()
        for root in roots:
            try:
                resolved = root.expanduser().resolve()
            except OSError:
                continue
            key = str(resolved).casefold()
            if key not in seen and resolved.exists():
                unique.append(resolved)
                seen.add(key)
        return unique

    def _steam_libraries(self, root: Path) -> list[Path]:
        libs = [root]
        vdf = root / "steamapps" / "libraryfolders.vdf"
        if vdf.exists():
            text = vdf.read_text(encoding="utf-8", errors="replace")
            for raw in re.findall(r'"path"\s+"([^"]+)"', text):
                raw = raw.replace("\\\\", "\\")
                path = Path(raw)
                if path.exists():
                    libs.append(path)
        unique: list[Path] = []
        seen: set[str] = set()
        for path in libs:
            key = str(path.resolve()).casefold()
            if key not in seen:
                unique.append(path.resolve())
                seen.add(key)
        return unique

    def steam_preview(self) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        appids: set[str] = set()
        for root in self.steam_roots():
            for library in self._steam_libraries(root):
                steamapps = library / "steamapps"
                if not steamapps.exists():
                    continue
                for manifest in steamapps.glob("appmanifest_*.acf"):
                    data = _parse_simple_vdf(manifest)
                    appid = data.get("appid") or manifest.stem.replace("appmanifest_", "")
                    name = data.get("name")
                    installdir = data.get("installdir")
                    if not appid or not name or appid in appids:
                        continue
                    install_path = steamapps / "common" / installdir if installdir else None
                    found.append({
                        "steam_app_id": appid,
                        "name": name,
                        "platform": "PC",
                        "path": str(install_path) if install_path else None,
                        "launch_uri": f"steam://rungameid/{appid}",
                        "source": "steam",
                        "available": bool(install_path and install_path.exists()),
                    })
                    appids.add(appid)
        return sorted(found, key=lambda item: item["name"].casefold())

    def folder_preview(self, folder: str) -> list[dict[str, Any]]:
        root = self.paths.decode(folder)
        if not root or not root.exists() or not root.is_dir():
            raise ValueError("La carpeta indicada no existe.")
        result: list[dict[str, Any]] = []
        for path in sorted(root.iterdir(), key=lambda p: p.name.casefold()):
            if path.is_file() and path.suffix.casefold() in {".lnk", ".exe", ".bat", ".cmd"}:
                result.append({
                    "name": path.stem,
                    "platform": "PC",
                    "executable": str(path),
                    "path": str(path),
                    "source": "folder-import",
                    "available": True,
                })
        return result
