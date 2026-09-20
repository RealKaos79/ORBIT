from __future__ import annotations

from pathlib import Path
from typing import Any

from app.core.paths import PortablePaths


# ORBIT only checks files supplied by the user. It never downloads proprietary
# firmware, BIOS or encryption keys.
REQUIREMENTS: dict[str, list[dict[str, Any]]] = {
    "Nintendo Switch": [
        {"id": "firmware", "label": "Firmware", "kind": "folder", "default": "@launcher/system/switch/firmware"},
        {"id": "keys", "label": "Keys", "kind": "keys", "default": "@launcher/system/switch/keys"},
    ],
    "Nintendo 3DS": [
        {"id": "system_files", "label": "Archivos de sistema", "kind": "folder", "default": "@launcher/system/3ds"},
    ],
    "PlayStation": [
        {"id": "bios", "label": "BIOS", "kind": "bios", "default": "@launcher/system/ps1/bios"},
    ],
    "PlayStation 2": [
        {"id": "bios", "label": "BIOS", "kind": "bios", "default": "@launcher/system/ps2/bios"},
    ],
}


def _has_requirement(path: Path | None, kind: str) -> bool:
    if path is None or not path.exists():
        return False
    if path.is_file():
        if kind == "keys":
            return path.suffix.casefold() in {".keys", ".key", ".txt"} and path.stat().st_size > 0
        return path.stat().st_size > 0
    try:
        files = [p for p in path.rglob("*") if p.is_file()]
    except OSError:
        return False
    if kind == "keys":
        return any(p.name.casefold() in {"prod.keys", "title.keys"} or p.suffix.casefold() in {".keys", ".key"} for p in files)
    if kind == "bios":
        return any(p.stat().st_size >= 64 * 1024 for p in files)
    return bool(files)


class ReadinessService:
    def __init__(self, paths: PortablePaths) -> None:
        self.paths = paths

    def platform_status(self, platform: str, settings: dict[str, Any]) -> dict[str, Any]:
        requirements = REQUIREMENTS.get(str(platform), [])
        configured = ((settings.get("system_files") or {}).get(platform) or {}) if isinstance(settings, dict) else {}
        items: list[dict[str, Any]] = []
        for req in requirements:
            raw = configured.get(req["id"]) or req["default"]
            try:
                decoded = self.paths.decode(raw)
            except ValueError:
                decoded = None
            ok = _has_requirement(decoded, str(req["kind"]))
            items.append({
                "id": req["id"],
                "label": req["label"],
                "required": True,
                "ok": ok,
                "path": self.paths.display(raw),
                "message": "Encontrado" if ok else "No encontrado. Añade tus archivos obtenidos legalmente.",
            })
        return {
            "platform": platform,
            "required": bool(requirements),
            "ok": all(x["ok"] for x in items),
            "items": items,
            "legal_note": "ORBIT no descarga ni distribuye firmware, BIOS o keys propietarios.",
        }

    def game_status(self, game: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
        return self.platform_status(str(game.get("platform") or "PC"), settings)
