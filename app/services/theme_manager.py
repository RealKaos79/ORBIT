from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from app.core.paths import PortablePaths
from app.core.storage import JsonStore

HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
OFFICIAL_THEME_IDS = {"dark", "light", "oled", "neon", "cyber", "ocean", "forest", "sunset", "violet", "retro", "amber", "ice", "rose", "midnight"}

DEFAULT_CUSTOM = {
    "base": "dark", "accent": "#65f4c5", "accent2": "#7aa7ff",
    "background": "#0b0f14", "panel": "#141b24", "text": "#f5f7fb", "muted": "#9aa8b6",
    "size": "medium", "shape": "soft", "spacing": "normal", "shadow": "medium", "animation": "smooth",
}


class ThemeManager:
    def __init__(self, paths: PortablePaths) -> None:
        self.paths = paths

    def _store(self, profile_id: str) -> JsonStore:
        base = self.paths.data if profile_id == "default" else self.paths.data / "profiles" / profile_id
        backup = self.paths.backups / "profiles" / profile_id / "themes"
        return JsonStore(self.paths, base_dir=base, backup_dir=backup)

    @staticmethod
    def _clean(payload: dict[str, Any], theme_id: str | None = None) -> dict[str, Any]:
        name = str(payload.get("name") or "Mi tema").strip()[:64] or "Mi tema"
        values = dict(DEFAULT_CUSTOM)
        for key in values:
            if key in payload:
                values[key] = payload[key]
        for key in ("accent", "accent2", "background", "panel", "text", "muted"):
            if not isinstance(values[key], str) or not HEX.fullmatch(values[key]):
                values[key] = DEFAULT_CUSTOM[key]
        allowed = {
            "base": {"dark", "light", "oled"}, "size": {"small", "medium", "large"},
            "shape": {"straight", "soft", "rounded", "very-rounded"},
            "spacing": {"tight", "normal", "wide"}, "shadow": {"none", "soft", "medium", "strong"},
            "animation": {"none", "fast", "smooth", "cinematic"},
        }
        for key, choices in allowed.items():
            if values[key] not in choices:
                values[key] = DEFAULT_CUSTOM[key]
        return {"id": theme_id or f"custom-{uuid.uuid4().hex[:12]}", "name": name, **values}

    def list(self, profile_id: str) -> list[dict[str, Any]]:
        value = self._store(profile_id).load("custom_themes", [])
        return value if isinstance(value, list) else []

    def save(self, profile_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        themes = self.list(profile_id)
        requested = str(payload.get("id") or "")
        if requested in OFFICIAL_THEME_IDS:
            raise ValueError("No se puede sobrescribir un tema oficial. Duplica el tema para personalizarlo.")
        existing = next((x for x in themes if str(x.get("id")) == requested), None) if requested else None
        clean = self._clean(payload, str(existing.get("id")) if existing else None)
        if existing:
            themes[themes.index(existing)] = clean
        else:
            themes.append(clean)
        self._store(profile_id).save("custom_themes", themes)
        return clean

    def delete(self, profile_id: str, theme_id: str) -> None:
        themes = self.list(profile_id)
        kept = [x for x in themes if str(x.get("id")) != theme_id]
        if len(kept) == len(themes):
            raise ValueError("Tema personalizado no encontrado.")
        self._store(profile_id).save("custom_themes", kept)

    def export(self, profile_id: str, theme_id: str) -> dict[str, Any]:
        theme = next((x for x in self.list(profile_id) if str(x.get("id")) == theme_id), None)
        if not theme:
            raise ValueError("Tema personalizado no encontrado.")
        self.paths.exports.mkdir(parents=True, exist_ok=True)
        filename = re.sub(r"[^\w .()-]+", "_", theme["name"]).strip() or "ORBIT-Theme"
        path = (self.paths.exports / f"{filename}.orbittheme").resolve()
        payload = {"format": "ORBITTHEME", "version": 1, "theme": theme}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"path": self.paths.encode(path), "filename": path.name, "theme": theme}

    def import_file(self, profile_id: str, source: str) -> dict[str, Any]:
        path = Path(source).expanduser().resolve()
        if not path.is_file() or path.suffix.casefold() != ".orbittheme":
            raise ValueError("Selecciona un archivo .orbittheme válido.")
        if path.stat().st_size > 1024 * 1024:
            raise ValueError("El archivo de tema es demasiado grande.")
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("El tema no contiene JSON válido.") from exc
        if payload.get("format") != "ORBITTHEME" or int(payload.get("version") or 0) != 1 or not isinstance(payload.get("theme"), dict):
            raise ValueError("Formato de tema no compatible.")
        raw = dict(payload["theme"])
        raw.pop("id", None)
        raw["name"] = f"{raw.get('name') or 'Tema'} (importado)"
        return self.save(profile_id, raw)
