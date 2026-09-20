from __future__ import annotations

import os
import json
import zipfile
import re
import shlex
import shutil
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Callable

from app.core.paths import PortablePaths
from app.core.storage import JsonStore
from app.services.importer import LocalImporter
from app.services.save_manager import SaveManager
from app.services.storage_info import storage_breakdown
from app.services.orbitpack import OrbitPackService, safe_name, sha256_file
from app.services.readiness import ReadinessService
from app.services.performance import estimate_game_performance
from app.services.theme_manager import ThemeManager, OFFICIAL_THEME_IDS
from app.services.ai_assistant import OrbitAssistant
from app.services.cover_search import CoverSearchService
from app.services.image_pipeline import MAX_IMAGE_BYTES, SUPPORTED_EXTENSIONS, store_image_file, validate_image_bytes, read_image_bytes
from app.services.secrets import SecretStore, scrub_sensitive

DEFAULT_EXTENSIONS = {
    "PC": {".exe", ".bat", ".cmd", ".com", ".lnk"},
    "NES": {".nes"},
    "SNES": {".smc", ".sfc"},
    "Nintendo 64": {".n64", ".z64", ".v64"},
    "Game Boy": {".gb"},
    "Game Boy Color": {".gbc"},
    "Game Boy Advance": {".gba"},
    "Nintendo DS": {".nds"},
    "Nintendo 3DS": {".3ds", ".cci", ".cxi"},
    "Nintendo Switch": {".nsp", ".xci", ".nro", ".nca"},
    "GameCube": {".iso", ".gcm", ".rvz"},
    "Wii": {".iso", ".wbfs", ".rvz"},
    "PlayStation": {".cue", ".chd", ".pbp"},
    "PlayStation 2": {".iso", ".chd"},
    "PSP": {".iso", ".cso", ".pbp"},
    "Dreamcast": {".cdi", ".gdi", ".chd"},
    "Mega Drive": {".md", ".gen", ".bin"},
    "Arcade": {".zip", ".7z"},
}


COVER_EXTENSIONS = set(SUPPORTED_EXTENSIONS)
MAX_COVER_BYTES = MAX_IMAGE_BYTES

PROFILE_SETTING_KEYS = {
    "theme", "interface_mode", "setup_complete", "accent", "ui_scale",
    "reduce_motion", "confirm_stop_game", "start_fullscreen",
    "start_view", "home_rows", "game_folders", "paths", "scanner", "saves",
    "controller", "parental", "default_emulators", "integrations",
    "organization", "system_files", "ai", "cover_search",
}
DEFAULT_PROFILE_AVATARS = {"orbit", "astronaut", "robot", "cat", "fox", "arcade", "planet", "star"}


def _valid_cover_signature(path: Path) -> bool:
    """Content-based image validation kept for legacy call sites."""
    try:
        validate_image_bytes(read_image_bytes(path, max_bytes=MAX_COVER_BYTES), max_bytes=MAX_COVER_BYTES)
        return True
    except ValueError:
        return False


PLATFORM_ALIASES = {
    "pc": "PC",
    "windows": "PC",
    "nes": "NES",
    "snes": "SNES",
    "super nintendo": "SNES",
    "n64": "Nintendo 64",
    "nintendo64": "Nintendo 64",
    "gb": "Game Boy",
    "gbc": "Game Boy Color",
    "gba": "Game Boy Advance",
    "nds": "Nintendo DS",
    "ds": "Nintendo DS",
    "3ds": "Nintendo 3DS",
    "switch": "Nintendo Switch",
    "nintendo switch": "Nintendo Switch",
    "nsw": "Nintendo Switch",
    "gamecube": "GameCube",
    "gc": "GameCube",
    "wii": "Wii",
    "ps1": "PlayStation",
    "psx": "PlayStation",
    "playstation 1": "PlayStation",
    "ps2": "PlayStation 2",
    "playstation2": "PlayStation 2",
    "psp": "PSP",
    "dreamcast": "Dreamcast",
    "megadrive": "Mega Drive",
    "mega drive": "Mega Drive",
    "genesis": "Mega Drive",
    "arcade": "Arcade",
    "mame": "Arcade",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_platform(value: Any, default: str = "PC") -> str:
    text = str(value or default).strip()
    if not text:
        text = default
    canonical = next((name for name in DEFAULT_EXTENSIONS if name.casefold() == text.casefold()), None)
    return canonical or PLATFORM_ALIASES.get(text.casefold(), text)


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


class LibraryService:
    def __init__(self, paths: PortablePaths, store: JsonStore) -> None:
        self.paths = paths
        self.store = store
        # JsonStore protects individual I/O operations. This lock protects whole
        # read-modify-write transactions across HTTP and process-watcher threads.
        self._lock = RLock()
        self.saves = SaveManager(paths)
        self.importer = LocalImporter(paths)
        self.orbitpacks = OrbitPackService(paths)
        self.readiness = ReadinessService(paths)
        self.themes = ThemeManager(paths)
        self.assistant = OrbitAssistant(paths)
        self.cover_search = CoverSearchService(paths)
        self.secrets = SecretStore(paths)
        self._processes: dict[str, subprocess.Popen[Any]] = {}  # key = profile_id:game_id
        self._process_lock = RLock()
        self._migrate_cover_search_secrets()
        self._ensure_defaults()
        self._migrate_existing_media_references()

    def default_settings(self) -> dict[str, Any]:
        return {
            "theme": "dark",
            "interface_mode": "classic",
            "setup_complete": False,
            "accent": "#65f4c5",
            "ui_scale": 1.0,
            "reduce_motion": False,
            "confirm_stop_game": True,
            "start_fullscreen": True,
            "start_view": "home",
            "home_rows": ["continue", "favorites", "recent", "platforms", "unplayed"],
            "game_folders": [],
            "paths": {
                "games": "@launcher/games",
                "emulators": "@launcher/emulators",
                "saves": "@launcher/saves",
                "covers": "@launcher/media/covers",
                "backgrounds": "@launcher/media/backgrounds",
                "logos": "@launcher/media/logos",
                "backups": "@launcher/backups",
            },
            "scanner": {"max_depth": 8},
            "saves": {
                "auto_backup_before_launch": False,
                "auto_backup_after_exit": False,
                "keep_backups": 12,
                "profile_isolation": True,
            },
            "controller": {
                "active_profile": "default",
                "shortcuts": {"search_enabled": True, "menu_enabled": True, "favorite_enabled": True},
                "navigation": {"auto_input_mode": True, "hide_cursor_on_gamepad": True, "show_input_indicator": True, "repeat_delay_ms": 360, "repeat_interval_ms": 110, "button_style": "auto"},
                "profiles": [{
                    "id": "default", "name": "Predeterminado",
                    "mapping": {"accept": 0, "back": 1, "menu": 2, "search": 3, "favorite": 4},
                    "deadzone": 0.55,
                }],
            },
            "profiles": {
                "active": "default",
                "select_on_start": True,
                "items": [{"id": "default", "name": "Principal", "avatar": "orbit", "created_at": utc_now()}],
            },
            "integrations": {
                "discord": {"enabled": False},
                "retroachievements": {"enabled": False, "username": ""},
                "updates": {"enabled": False, "manifest_url": ""},
            },
            "parental": {"enabled": False, "hide_settings": False},
            "organization": {
                "platform_paths": {},
                "emulator_paths": {},
                "default_game_root": "@launcher/games",
                "default_emulator_root": "@launcher/emulators",
            },
            "system_files": {},
            "ai": {
                "enabled": True,
                "engine": "offline-integrated",
                "local_model": {"enabled": False, "provider": "ollama", "endpoint": "http://127.0.0.1:11434", "model": "", "timeout_seconds": 8},
                "online_search": {"enabled": False, "provider": "wikipedia", "language": "es"},
            },
            "cover_search": {"provider": "steamgriddb", "api_key_configured": False},
        }

    def _migrate_cover_search_secrets(self) -> None:
        """Move legacy SteamGridDB keys out of JSON and scrub old JSON backups."""
        settings_path = self.paths.data / "settings.json"
        try:
            raw = json.loads(settings_path.read_text(encoding="utf-8")) if settings_path.is_file() else {}
        except (OSError, json.JSONDecodeError):
            raw = {}
        if isinstance(raw, dict):
            cfg = raw.get("cover_search") if isinstance(raw.get("cover_search"), dict) else {}
            token = str(cfg.get("api_key") or "").strip()
            if token:
                self.secrets.set_steamgriddb("default", token)
            clean = scrub_sensitive(raw)
            if clean != raw:
                settings_path.parent.mkdir(parents=True, exist_ok=True)
                settings_path.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
            profiles = raw.get("profiles") if isinstance(raw.get("profiles"), dict) else {}
            for item in profiles.get("items") or []:
                pid = str(item.get("id") or "") if isinstance(item, dict) else ""
                if not pid or pid == "default":
                    continue
                personal_path = self.paths.data / "profiles" / pid / "profile_settings.json"
                try:
                    personal = json.loads(personal_path.read_text(encoding="utf-8")) if personal_path.is_file() else {}
                except (OSError, json.JSONDecodeError):
                    personal = {}
                if isinstance(personal, dict):
                    pcfg = personal.get("cover_search") if isinstance(personal.get("cover_search"), dict) else {}
                    ptoken = str(pcfg.get("api_key") or "").strip()
                    if ptoken:
                        self.secrets.set_steamgriddb(pid, ptoken)
                    clean_personal = scrub_sensitive(personal)
                    if clean_personal != personal:
                        personal_path.write_text(json.dumps(clean_personal, ensure_ascii=False, indent=2), encoding="utf-8")
        # v0.5 JsonStore backups could contain the key. Scrub JSON only; secret
        # files themselves live under data/.secrets and are never copied to backups.
        if self.paths.backups.exists():
            for candidate in self.paths.backups.rglob("*.json"):
                try:
                    SecretStore.scrub_json_file(candidate)
                except OSError:
                    pass

    def _steamgrid_key(self, profile_id: str | None = None) -> str:
        return self.secrets.get_steamgriddb(str(profile_id or self._active_profile_id()))

    def _global_settings(self) -> dict[str, Any]:
        raw = self.store.load("settings", {})
        if not isinstance(raw, dict):
            raw = {}
        merged = _deep_merge(self.default_settings(), raw)
        # v0.5 retired the old per-PC privacy feature. Ignore legacy keys even
        # when an older settings.json is copied over during an update.
        merged.pop("privacy_mode", None)
        profiles = merged.setdefault("profiles", self.default_settings()["profiles"])
        items = profiles.setdefault("items", [])
        if not items:
            items.append({"id": "default", "name": "Principal", "avatar": "orbit", "created_at": utc_now()})
        for item in items:
            item.setdefault("avatar", "orbit")
        if not any(str(x.get("id")) == str(profiles.get("active")) for x in items):
            profiles["active"] = str(items[0].get("id") or "default")
        self._normalize_controller(merged)
        return merged

    def _active_profile_id(self) -> str:
        profiles = self._global_settings().get("profiles", {})
        return str(profiles.get("active") or "default")

    def _profile_store(self, profile_id: str | None = None) -> JsonStore:
        pid = str(profile_id or self._active_profile_id())
        if pid == "default":
            return self.store
        base = self.paths.data / "profiles" / pid
        backup = self.paths.backups / "profiles" / pid / "config"
        return JsonStore(self.paths, base_dir=base, backup_dir=backup)

    def _profile_load(self, name: str, default: Any, profile_id: str | None = None) -> Any:
        return self._profile_store(profile_id).load(name, default)

    def _profile_save(self, name: str, value: Any, profile_id: str | None = None) -> None:
        self._profile_store(profile_id).save(name, value)

    def _ensure_profile_data(self, profile_id: str, with_demos: bool = True) -> None:
        store = self._profile_store(profile_id)
        base = self.paths.data if profile_id == "default" else self.paths.data / "profiles" / profile_id
        if not (base / "games.json").exists():
            store.save("games", self.demo_games() if with_demos else [])
        if not (base / "history.json").exists():
            store.save("history", [])
        if not (base / "collections.json").exists():
            store.save("collections", [])
        if not (base / "emulators.json").exists():
            store.save("emulators", [])
        if profile_id != "default" and not (base / "profile_settings.json").exists():
            d = self.default_settings()
            store.save("profile_settings", {key: d[key] for key in PROFILE_SETTING_KEYS if key in d})

    def _all_profile_ids(self) -> list[str]:
        items = self._global_settings().get("profiles", {}).get("items", [])
        return [str(x.get("id")) for x in items if x.get("id")] or ["default"]

    def _ensure_defaults(self) -> None:
        with self._lock:
            # The legacy/default profile deliberately keeps using data/*.json so
            # existing ORBIT installations migrate without moving or deleting files.
            if not (self.paths.data / "games.json").exists():
                self.store.save("games", self.demo_games())
            if not (self.paths.data / "emulators.json").exists():
                self.store.save("emulators", [])
            if not (self.paths.data / "settings.json").exists():
                self.store.save("settings", self.default_settings())
            else:
                current = self.store.load("settings", {})
                if not isinstance(current, dict):
                    current = {}
                merged = _deep_merge(self.default_settings(), current)
                merged.pop("privacy_mode", None)
                profiles = merged.setdefault("profiles", self.default_settings()["profiles"])
                profiles.setdefault("select_on_start", True)
                items = profiles.setdefault("items", [])
                if not items:
                    items.append({"id": "default", "name": "Principal", "avatar": "orbit", "created_at": utc_now()})
                for item in items:
                    item.setdefault("avatar", "orbit")
                if merged != current:
                    self.store.save("settings", merged)
            if not (self.paths.data / "history.json").exists():
                self.store.save("history", [])
            if not (self.paths.data / "collections.json").exists():
                self.store.save("collections", [])
            # Ensure data exists for every already-created non-default profile.
            for profile_id in self._all_profile_ids():
                if profile_id != "default":
                    self._ensure_profile_data(profile_id, with_demos=True)
                    personal = self._profile_load("profile_settings", {}, profile_id)
                    if isinstance(personal, dict) and "privacy_mode" in personal:
                        personal.pop("privacy_mode", None)
                        self._profile_save("profile_settings", personal, profile_id)

    def _media_path_referenced_elsewhere(self, games: list[dict[str, Any]], path: Path, *, exclude_game_id: str | None = None) -> bool:
        """Return True when another game still points at the same media file.

        Older ORBIT versions could leave shared/absolute cover references. A cover
        replacement must never delete a file still used by another game.
        """
        try:
            wanted = path.resolve()
        except OSError:
            wanted = path.absolute()
        for item in games:
            if exclude_game_id is not None and str(item.get("id")) == str(exclude_game_id):
                continue
            values = [item.get("cover"), item.get("background"), item.get("logo"), *(item.get("screenshots") or [])]
            for value in values:
                other = self.paths.decode(value) if value else None
                if not other:
                    continue
                try:
                    if other.resolve() == wanted:
                        return True
                except OSError:
                    if other.absolute() == wanted:
                        return True
        return False

    def _legacy_media_candidate(self, value: Any, directory: Path, game_id: str) -> Path | None:
        """Recover a moved/renamed legacy media file without guessing user files."""
        if not value:
            return None
        decoded = self.paths.decode(value)
        if decoded and decoded.is_file():
            return decoded
        names: list[str] = []
        text = str(value)
        try:
            names.append(Path(text.replace("\\", "/")).stem)
        except Exception:
            pass
        names.append(str(game_id))
        for stem in dict.fromkeys(x for x in names if x):
            for candidate in directory.glob(f"{stem}.*"):
                if candidate.is_file() and _valid_cover_signature(candidate):
                    return candidate
        return None

    def _migrate_existing_media_references(self) -> None:
        """Preserve and normalise covers from older ORBIT builds.

        - Existing managed files with a correct extension are left untouched.
        - External/legacy files are copied into ORBIT, never deleted.
        - Files whose suffix disagrees with their real content are copied using
          the detected canonical suffix, preventing wrong HTTP Content-Type after
          a restart.
        - Missing legacy references are repaired only when a matching managed
          file already exists.
        """
        with self._lock:
            for profile_id in self._all_profile_ids():
                raw = self._profile_load("games", [], profile_id)
                if not isinstance(raw, list):
                    continue
                changed = False
                for game in raw:
                    if not isinstance(game, dict) or game.get("demo"):
                        continue
                    game_id = str(game.get("id") or "")
                    if not game_id:
                        continue
                    for kind, directory in (("cover", self.paths.covers), ("background", self.paths.backgrounds), ("logo", self.paths.logos)):
                        value = game.get(kind)
                        if not value:
                            continue
                        source = self._legacy_media_candidate(value, directory, game_id)
                        if source is None:
                            # Preserve unresolved metadata; do not silently erase it.
                            continue
                        try:
                            raw_bytes = read_image_bytes(source, max_bytes=MAX_COVER_BYTES)
                            fmt = validate_image_bytes(raw_bytes, max_bytes=MAX_COVER_BYTES)
                        except ValueError:
                            continue
                        try:
                            inside_directory = directory.resolve() == source.resolve().parent or directory.resolve() in source.resolve().parents
                        except OSError:
                            inside_directory = False
                        canonical_suffix = fmt.extension if fmt.browser_safe else ".png"
                        canonical_managed = inside_directory and source.suffix.casefold() == canonical_suffix
                        if canonical_managed:
                            encoded = self.paths.encode(source)
                            if game.get(kind) != encoded:
                                game[kind] = encoded
                                game[f"{kind}_version"] = time.time_ns()
                                changed = True
                            continue
                        try:
                            target = store_image_file(source, directory / game_id, max_bytes=MAX_COVER_BYTES)
                        except ValueError:
                            continue
                        encoded = self.paths.encode(target)
                        if game.get(kind) != encoded:
                            game[kind] = encoded
                            game[f"{kind}_version"] = time.time_ns()
                            changed = True
                    shots = list(game.get("screenshots") or [])
                    migrated_shots: list[str] = []
                    shots_changed = False
                    for index, value in enumerate(shots):
                        source = self.paths.decode(value) if value else None
                        if not source or not source.is_file():
                            migrated_shots.append(value)
                            continue
                        try:
                            raw_bytes = read_image_bytes(source, max_bytes=MAX_COVER_BYTES)
                            fmt = validate_image_bytes(raw_bytes, max_bytes=MAX_COVER_BYTES)
                        except ValueError:
                            migrated_shots.append(value)
                            continue
                        canonical_suffix = fmt.extension if fmt.browser_safe else ".png"
                        try:
                            managed = self.paths.screenshots.resolve() in source.resolve().parents and source.suffix.casefold() == canonical_suffix
                        except OSError:
                            managed = False
                        if managed:
                            encoded = self.paths.encode(source)
                        else:
                            try:
                                target = store_image_file(source, self.paths.screenshots / f"{game_id}-{index}", max_bytes=MAX_COVER_BYTES)
                                encoded = self.paths.encode(target)
                            except ValueError:
                                encoded = value
                        migrated_shots.append(encoded)
                        shots_changed = shots_changed or encoded != value
                    if shots_changed:
                        game["screenshots"] = migrated_shots
                        game["screenshot_version"] = time.time_ns()
                        changed = True
                if changed:
                    self._profile_save("games", raw, profile_id)

    def _migrate_game(self, game: dict[str, Any]) -> bool:
        defaults: dict[str, Any] = {
            "background": None,
            "logo": None,
            "screenshots": [],
            "genre": "",
            "year": "",
            "developer": "",
            "players": "",
            "tags": [],
            "status": "playing" if game.get("last_played") else "backlog",
            "hidden": False,
            "completed": False,
            "notes": "",
            "arguments": "",
            "save_path": None,
            "portable_save_path": None,
            "source": game.get("source") or "manual",
            "steam_app_id": game.get("steam_app_id"),
            "launch_uri": game.get("launch_uri"),
            "last_session_seconds": 0,
            "region": "",
            "revision": "",
            "performance_demand": None,
        }
        changed = False
        for key, value in defaults.items():
            if key not in game:
                game[key] = value
                changed = True
        if not isinstance(game.get("tags"), list):
            game["tags"] = []
            changed = True
        if not isinstance(game.get("screenshots"), list):
            game["screenshots"] = []
            changed = True
        if game.get("completed") and game.get("status") != "completed":
            game["status"] = "completed"
            changed = True
        return changed

    def demo_games(self) -> list[dict[str, Any]]:
        items = [
            ("Nebula Drift", "PC", "Carreras espaciales", "ND"),
            ("Mosswood Legends", "SNES", "Aventura fantástica", "ML"),
            ("Pixel Rally 98", "PlayStation", "Velocidad arcade", "PR"),
            ("Sky Harbor", "Dreamcast", "Exploración aérea", "SH"),
            ("Dungeon Pocket", "Game Boy Advance", "RPG portátil", "DP"),
            ("Star Circuit", "Nintendo 64", "Competición futurista", "SC"),
            ("Solar Tactics", "Nintendo DS", "Estrategia por turnos", "ST"),
            ("Arcadia Nights", "PC", "Aventura narrativa", "AN"),
        ]
        games = []
        for index, (name, platform, description, initials) in enumerate(items):
            games.append({
                "id": f"demo-{index + 1}",
                "name": name,
                "platform": platform,
                "path": None,
                "executable": None,
                "cover": None,
                "description": description,
                "favorite": index in (1, 4),
                "last_played": None,
                "play_time_seconds": 0,
                "launch_count": 0,
                "emulator_id": None,
                "available": False,
                "demo": True,
                "accent": initials,
                "added_at": utc_now(),
            })
        return games

    def _remove_demos_if_real(self, games: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], bool]:
        if any(not game.get("demo") for game in games) and any(game.get("demo") for game in games):
            return [game for game in games if not game.get("demo")], True
        return games, False

    def games(self) -> list[dict[str, Any]]:
        with self._lock:
            games = self._profile_load("games", [])
            if not isinstance(games, list):
                games = []
            games, changed = self._remove_demos_if_real(games)
            for game in games:
                if self._migrate_game(game):
                    changed = True
                available = self._game_available(game)
                if game.get("available") != available:
                    game["available"] = available
                    changed = True
            if changed:
                self._profile_save("games", games)
            return games

    def _normalize_controller(self, settings: dict[str, Any]) -> bool:
        changed = False
        controller = settings.setdefault("controller", {})
        shortcuts = controller.setdefault("shortcuts", {})
        navigation = controller.setdefault("navigation", {})
        for key, default in {"auto_input_mode": True, "hide_cursor_on_gamepad": True, "show_input_indicator": True, "repeat_delay_ms": 360, "repeat_interval_ms": 110, "button_style": "auto"}.items():
            if key not in navigation:
                navigation[key] = default
                changed = True
        try:
            navigation["repeat_delay_ms"] = max(180, min(900, int(navigation.get("repeat_delay_ms", 360))))
            navigation["repeat_interval_ms"] = max(70, min(350, int(navigation.get("repeat_interval_ms", 110))))
        except (TypeError, ValueError):
            navigation["repeat_delay_ms"], navigation["repeat_interval_ms"] = 360, 110
            changed = True
        if str(navigation.get("button_style")) not in {"auto", "playstation", "xbox", "nintendo"}:
            navigation["button_style"] = "auto"
            changed = True
        for key, default in {"search_enabled": True, "menu_enabled": True, "favorite_enabled": True}.items():
            if key not in shortcuts:
                shortcuts[key] = default
                changed = True
        profiles = controller.setdefault("profiles", [])
        if not profiles:
            profiles.append({
                "id": "default", "name": "Predeterminado",
                "mapping": {"accept": 0, "back": 1, "menu": 2, "search": 3, "favorite": 4},
                "deadzone": 0.55,
            })
            controller["active_profile"] = "default"
            changed = True
        for profile in profiles:
            mapping = profile.setdefault("mapping", {})
            mapping.setdefault("accept", 0)
            mapping.setdefault("back", 1)
            # Migrate ORBIT's old default shortcuts (Start=menu, Y=favorite) to
            # Square/X=menu, Triangle/Y=search and L1/LB=favorite. Custom mappings
            # remain untouched when they no longer match the legacy defaults.
            if "search" not in mapping:
                mapping["search"] = 3
                changed = True
                if mapping.get("favorite") == 3:
                    mapping["favorite"] = 4
                if mapping.get("menu") == 9:
                    mapping["menu"] = 2
            mapping.setdefault("menu", 2)
            mapping.setdefault("favorite", 4)
            try:
                profile["deadzone"] = max(0.2, min(0.9, float(profile.get("deadzone", 0.55))))
            except (TypeError, ValueError):
                profile["deadzone"] = 0.55
                changed = True
        active = str(controller.get("active_profile") or profiles[0].get("id") or "default")
        if not any(str(x.get("id")) == active for x in profiles):
            controller["active_profile"] = str(profiles[0].get("id") or "default")
            changed = True
        return changed

    def _profile_settings_for(self, profile_id: str) -> dict[str, Any]:
        global_settings = self._global_settings()
        if str(profile_id) == "default":
            return global_settings
        personal = self._profile_load("profile_settings", {}, str(profile_id))
        if not isinstance(personal, dict):
            personal = {}
        merged = _deep_merge(global_settings, {k: v for k, v in personal.items() if k in PROFILE_SETTING_KEYS})
        merged["profiles"] = global_settings.get("profiles", {})
        return merged

    def settings(self) -> dict[str, Any]:
        with self._lock:
            global_settings = self._global_settings()
            pid = str(global_settings.get("profiles", {}).get("active") or "default")
            if pid == "default":
                merged = global_settings
            else:
                personal = self._profile_load("profile_settings", {}, pid)
                if not isinstance(personal, dict):
                    personal = {}
                merged = _deep_merge(global_settings, {k: v for k, v in personal.items() if k in PROFILE_SETTING_KEYS})
            # The profile registry is launcher-global; user experience/security preferences remain profile-scoped.
            merged["profiles"] = global_settings.get("profiles", {})
            self._normalize_controller(merged)
            cover_cfg = dict(merged.get("cover_search") or {})
            cover_cfg.pop("api_key", None)
            cover_cfg["api_key_configured"] = bool(self._steamgrid_key(pid))
            merged["cover_search"] = cover_cfg
            return merged

    def save_settings(self, patch: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(patch, dict):
            raise ValueError("La configuración recibida no es válida.")
        patch = dict(patch)
        patch.pop("privacy_mode", None)
        with self._lock:
            global_settings = self._global_settings()
            pid = str(global_settings.get("profiles", {}).get("active") or "default")
            cover_patch = patch.get("cover_search")
            if isinstance(cover_patch, dict):
                clean_cover = dict(cover_patch)
                if "api_key" in clean_cover:
                    self.secrets.set_steamgriddb(pid, str(clean_cover.pop("api_key") or ""))
                clean_cover.pop("api_key_configured", None)
                patch["cover_search"] = scrub_sensitive(clean_cover)
            personal_patch = {k: v for k, v in patch.items() if k in PROFILE_SETTING_KEYS}
            global_patch = {k: v for k, v in patch.items() if k not in PROFILE_SETTING_KEYS}
            if pid == "default":
                global_patch.update(personal_patch)
            elif personal_patch:
                current_personal = self._profile_load("profile_settings", {}, pid)
                if not isinstance(current_personal, dict):
                    current_personal = {}
                self._profile_save("profile_settings", _deep_merge(current_personal, personal_patch), pid)
            settings = _deep_merge(global_settings, global_patch)
            scanner = settings.setdefault("scanner", {})
            try:
                scanner["max_depth"] = max(0, min(32, int(scanner.get("max_depth", 8))))
            except (TypeError, ValueError):
                scanner["max_depth"] = 8
            # Validate personal settings through the combined view below, but keep globals safe too.
            self.store.save("settings", settings)
            combined = self.settings()
            try:
                combined["ui_scale"] = max(0.8, min(1.4, float(combined.get("ui_scale", 1.0))))
            except (TypeError, ValueError):
                combined["ui_scale"] = 1.0
            accent = str(combined.get("accent") or "#65f4c5")
            if len(accent) != 7 or not accent.startswith("#") or any(ch not in "0123456789abcdefABCDEF" for ch in accent[1:]):
                combined["accent"] = "#65f4c5"
            allowed_themes = set(OFFICIAL_THEME_IDS) | {str(x.get("id")) for x in self.themes.list(pid)}
            if combined.get("theme") not in allowed_themes:
                combined["theme"] = "dark"
            allowed_modes = {"classic", "topnav", "compact", "cinematic", "handheld", "couch"}
            if combined.get("interface_mode") not in allowed_modes:
                combined["interface_mode"] = "classic"
            combined["setup_complete"] = bool(combined.get("setup_complete", False))
            combined["confirm_stop_game"] = bool(combined.get("confirm_stop_game", True))
            # Save normalized personal values in the correct scope.
            if pid == "default":
                norm = self._global_settings()
                for key in PROFILE_SETTING_KEYS:
                    if key in combined:
                        norm[key] = scrub_sensitive(combined[key])
                if isinstance(norm.get("cover_search"), dict):
                    norm["cover_search"].pop("api_key_configured", None)
                self.store.save("settings", scrub_sensitive(norm))
            else:
                personal = self._profile_load("profile_settings", {}, pid)
                if not isinstance(personal, dict):
                    personal = {}
                for key in PROFILE_SETTING_KEYS:
                    if key in combined:
                        personal[key] = scrub_sensitive(combined[key])
                if isinstance(personal.get("cover_search"), dict):
                    personal["cover_search"].pop("api_key_configured", None)
                self._profile_save("profile_settings", scrub_sensitive(personal), pid)
            return self.settings()

    def _clean_tags(self, value: Any) -> list[str]:
        if isinstance(value, str):
            raw = [part.strip() for part in value.replace(";", ",").split(",")]
        elif isinstance(value, list):
            raw = [str(part).strip() for part in value]
        else:
            raw = []
        result: list[str] = []
        seen: set[str] = set()
        for tag in raw:
            if not tag:
                continue
            tag = tag[:40]
            key = tag.casefold()
            if key not in seen:
                result.append(tag)
                seen.add(key)
            if len(result) >= 20:
                break
        return result

    def emulators(self) -> list[dict[str, Any]]:
        with self._lock:
            items = self._profile_load("emulators", [])
            if not isinstance(items, list):
                items = []
            changed = False
            for item in items:
                exe = self.paths.decode(item.get("executable"))
                available = bool(exe and exe.exists() and exe.is_file())
                if item.get("available") != available:
                    item["available"] = available
                    changed = True
            if changed:
                self._profile_save("emulators", items)
            return items

    def _default_emulator_id(self, platform: str) -> str | None:
        canonical = normalize_platform(platform, default="Otra")
        configured = self.settings().get("default_emulators", {}).get(canonical)
        if configured:
            emulator = next((e for e in self.emulators() if e.get("id") == configured), None)
            if emulator and emulator.get("available"):
                return str(configured)
        for emulator in self.emulators():
            if normalize_platform(emulator.get("platform"), default="Otra") == canonical and emulator.get("available"):
                return str(emulator.get("id"))
        return None

    def add_emulator(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            executable = self.paths.encode(payload.get("executable"))
            if not executable:
                raise ValueError("Debes indicar el ejecutable del emulador.")
            name = str(payload.get("name") or "Emulador").strip() or "Emulador"
            platform_name = normalize_platform(payload.get("platform"), default="Otra")
            decoded = self.paths.decode(executable)
            item = {
                "id": uuid.uuid4().hex,
                "name": name,
                "platform": platform_name,
                "executable": executable,
                "arguments": str(payload.get("arguments") or '"{rom}"'),
                "working_directory": self.paths.encode(payload.get("working_directory")) if payload.get("working_directory") else None,
                "available": bool(decoded and decoded.exists() and decoded.is_file()),
            }
            items = self._profile_load("emulators", [])
            if not isinstance(items, list):
                items = []
            items.append(item)
            self._profile_save("emulators", items)

            # If this is the first usable emulator for the platform, connect
            # existing unassigned ROMs automatically. Never override an
            # emulator the user already selected.
            if item["available"] and platform_name != "PC":
                games = self._profile_load("games", [])
                if isinstance(games, list):
                    games_changed = False
                    for game in games:
                        if (
                            not game.get("demo")
                            and not game.get("emulator_id")
                            and normalize_platform(game.get("platform"), default="Otra") == platform_name
                        ):
                            game["emulator_id"] = item["id"]
                            game["available"] = self._game_available(game)
                            games_changed = True
                    if games_changed:
                        self._profile_save("games", games)
            return item

    def ensure_emulator(self, *, name: str, platform: str, executable: str, arguments: str = '"{rom}"') -> dict[str, Any]:
        """Register an installed portable emulator without duplicating entries.

        The executable may be shared by several platform entries (e.g. Dolphin
        for GameCube and Wii). Each profile keeps its own emulator metadata.
        """
        canonical = normalize_platform(platform, default="Otra")
        encoded = self.paths.encode(executable)
        if not encoded:
            raise ValueError("No se pudo registrar el ejecutable del emulador.")
        with self._lock:
            items = self._profile_load("emulators", [])
            if not isinstance(items, list):
                items = []
            for item in items:
                if (
                    normalize_platform(item.get("platform"), default="Otra") == canonical
                    and str(item.get("executable") or "") == str(encoded)
                ):
                    return item
        return self.add_emulator({"name": name, "platform": canonical, "executable": executable, "arguments": arguments})

    def delete_emulator(self, emulator_id: str) -> None:
        with self._lock:
            raw = self._profile_load("emulators", [])
            items = raw if isinstance(raw, list) else []
            if not any(x.get("id") == emulator_id for x in items):
                raise KeyError("Emulador no encontrado")
            items = [x for x in items if x.get("id") != emulator_id]
            self._profile_save("emulators", items)

            # Clear dangling references so a replacement emulator can be
            # assigned later by platform. This only changes library metadata.
            games = self._profile_load("games", [])
            if isinstance(games, list):
                changed = False
                for game in games:
                    if game.get("emulator_id") == emulator_id:
                        game["emulator_id"] = None
                        game["available"] = self._game_available(game)
                        changed = True
                if changed:
                    self._profile_save("games", games)

    def update_emulator(self, emulator_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            items = self._profile_load("emulators", [])
            if not isinstance(items, list):
                items = []
            emulator = next((e for e in items if e.get("id") == emulator_id), None)
            if emulator is None:
                raise KeyError("Emulador no encontrado")
            if "name" in patch:
                emulator["name"] = str(patch.get("name") or "Emulador").strip() or "Emulador"
            if "platform" in patch:
                emulator["platform"] = normalize_platform(patch.get("platform"), default="Otra")
            if "executable" in patch:
                emulator["executable"] = self.paths.encode(patch.get("executable")) if patch.get("executable") else None
            if "arguments" in patch:
                emulator["arguments"] = str(patch.get("arguments") or '"{rom}"')
            if "working_directory" in patch:
                emulator["working_directory"] = self.paths.encode(patch.get("working_directory")) if patch.get("working_directory") else None
            exe = self.paths.decode(emulator.get("executable"))
            emulator["available"] = bool(exe and exe.exists() and exe.is_file())
            self._profile_save("emulators", items)
            return emulator

    def set_default_emulator(self, platform: str, emulator_id: str | None) -> dict[str, Any]:
        canonical = normalize_platform(platform, default="Otra")
        if emulator_id:
            emulator = next((e for e in self.emulators() if e.get("id") == emulator_id), None)
            if emulator is None:
                raise KeyError("Emulador no encontrado")
            if normalize_platform(emulator.get("platform"), default="Otra") != canonical:
                raise ValueError("El emulador no corresponde a esa plataforma.")
        settings = self.settings()
        defaults = dict(settings.get("default_emulators", {}))
        if emulator_id:
            defaults[canonical] = emulator_id
        else:
            defaults.pop(canonical, None)
        return self.save_settings({"default_emulators": defaults})

    def test_emulator(self, emulator_id: str) -> dict[str, Any]:
        emulator = next((e for e in self.emulators() if e.get("id") == emulator_id), None)
        if emulator is None:
            raise KeyError("Emulador no encontrado")
        exe = self.paths.decode(emulator.get("executable"))
        if not exe or not exe.exists() or not exe.is_file():
            return {"ok": False, "detail": "No se encuentra el ejecutable."}
        return {"ok": True, "detail": str(exe), "platform": emulator.get("platform")}

    def add_game(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            game_path = self.paths.encode(payload.get("path")) if payload.get("path") else None
            executable = self.paths.encode(payload.get("executable")) if payload.get("executable") else None
            if not game_path and not executable:
                raise ValueError("Debes indicar la ruta del juego o su ejecutable.")

            platform_name = normalize_platform(payload.get("platform"), default="PC")
            source_path = self.paths.decode(executable or game_path)
            name = str(payload.get("name") or (source_path.stem if source_path else "Juego")).strip() or "Juego"
            emulator_id = payload.get("emulator_id") or None
            if emulator_id and not any(e.get("id") == emulator_id for e in self.emulators()):
                raise ValueError("El emulador seleccionado ya no existe.")
            if not emulator_id and platform_name != "PC":
                emulator_id = self._default_emulator_id(platform_name)

            game = {
                "id": uuid.uuid4().hex,
                "name": name,
                "platform": platform_name,
                "path": game_path,
                "executable": executable,
                "cover": None,
                "background": None,
                "logo": None,
                "screenshots": [],
                "description": str(payload.get("description") or ""),
                "genre": str(payload.get("genre") or ""),
                "year": str(payload.get("year") or ""),
                "developer": str(payload.get("developer") or ""),
                "region": str(payload.get("region") or ""),
                "revision": str(payload.get("revision") or ""),
                "performance_demand": int(payload.get("performance_demand")) if str(payload.get("performance_demand") or "").isdigit() else None,
                "players": str(payload.get("players") or ""),
                "tags": self._clean_tags(payload.get("tags")),
                "status": str(payload.get("status") or "backlog"),
                "hidden": bool(payload.get("hidden", False)),
                "completed": str(payload.get("status") or "backlog") == "completed",
                "notes": str(payload.get("notes") or ""),
                "arguments": str(payload.get("arguments") or ""),
                "save_path": self.paths.encode(payload.get("save_path")) if payload.get("save_path") else None,
                "portable_save_path": self.paths.encode(payload.get("portable_save_path")) if payload.get("portable_save_path") else None,
                "favorite": False,
                "last_played": None,
                "play_time_seconds": 0,
                "last_session_seconds": 0,
                "launch_count": 0,
                "emulator_id": emulator_id,
                "available": False,
                "demo": False,
                "accent": "GO",
                "source": str(payload.get("source") or "manual"),
                "steam_app_id": payload.get("steam_app_id") or None,
                "launch_uri": payload.get("launch_uri") or None,
                "added_at": utc_now(),
            }
            game["available"] = self._game_available(game)
            games = self._profile_load("games", [])
            if not isinstance(games, list):
                games = []
            games = [g for g in games if not g.get("demo")]
            games.append(game)
            self._profile_save("games", games)
            return game

    def update_game(self, game_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            games = self._profile_load("games", [])
            if not isinstance(games, list):
                games = []
            for game in games:
                if game.get("id") != game_id:
                    continue
                self._migrate_game(game)
                if "name" in patch:
                    game["name"] = str(patch["name"] or "").strip() or game.get("name") or "Juego"
                if "platform" in patch:
                    game["platform"] = normalize_platform(patch["platform"], default="PC")
                for key in ("description", "genre", "year", "developer", "players", "notes", "arguments", "region", "revision"):
                    if key in patch:
                        game[key] = str(patch[key] or "")
                if "favorite" in patch:
                    game["favorite"] = bool(patch["favorite"])
                if "hidden" in patch:
                    game["hidden"] = bool(patch["hidden"])
                if "status" in patch:
                    status = str(patch["status"] or "backlog")
                    if status not in {"backlog", "playing", "completed"}:
                        status = "backlog"
                    game["status"] = status
                    game["completed"] = status == "completed"
                if "tags" in patch:
                    game["tags"] = self._clean_tags(patch["tags"])
                if "performance_demand" in patch:
                    raw = patch.get("performance_demand")
                    if raw in (None, ""):
                        game["performance_demand"] = None
                    else:
                        try:
                            game["performance_demand"] = max(1, min(5, int(raw)))
                        except (TypeError, ValueError):
                            raise ValueError("La demanda de rendimiento debe estar entre 1 y 5.")
                if "emulator_id" in patch:
                    emulator_id = patch["emulator_id"] or None
                    if emulator_id and not any(e.get("id") == emulator_id for e in self.emulators()):
                        raise ValueError("El emulador seleccionado ya no existe.")
                    game["emulator_id"] = emulator_id
                for key in ("path", "executable", "save_path", "portable_save_path"):
                    if key in patch:
                        game[key] = self.paths.encode(patch[key]) if patch[key] else None
                game["available"] = self._game_available(game)
                self._profile_save("games", games)
                return game
            raise KeyError("Juego no encontrado")

    def set_game_cover(self, game_id: str, source: str) -> dict[str, Any]:
        """Validate by content, normalise, persist and attach a cover safely.

        The user's original file is never modified. A managed canonical copy is
        created under media/covers, so the cover survives restart/drive changes.
        """
        with self._lock:
            source_path = self.paths.decode(source)
            if not source_path or not source_path.exists() or not source_path.is_file():
                raise ValueError("La imagen seleccionada no existe.")

            games = self._profile_load("games", [])
            if not isinstance(games, list):
                games = []
            game = next((g for g in games if g.get("id") == game_id), None)
            if game is None:
                raise KeyError("Juego no encontrado")
            if game.get("demo"):
                raise ValueError("Las carátulas personalizadas se aplican a juegos reales de tu biblioteca.")

            self.paths.covers.mkdir(parents=True, exist_ok=True)
            old_cover = game.get("cover")
            old_path = self.paths.decode(old_cover) if old_cover else None
            # The image pipeline detects the real bytes, not the filename, and
            # chooses a canonical extension (or converts when a decoder exists).
            destination = store_image_file(source_path, self.paths.covers / str(game_id), max_bytes=MAX_COVER_BYTES).resolve()
            destination.relative_to(self.paths.covers.resolve())

            game["cover"] = self.paths.encode(destination)
            game["cover_version"] = time.time_ns()
            self._profile_save("games", games)

            # Delete an obsolete managed copy only when no other game references
            # it. This protects legacy/shared cover references.
            if old_path and old_path != destination and not self._media_path_referenced_elsewhere(games, old_path, exclude_game_id=game_id):
                try:
                    old_resolved = old_path.resolve()
                    old_resolved.relative_to(self.paths.covers.resolve())
                    if old_resolved.is_file():
                        old_resolved.unlink(missing_ok=True)
                except (OSError, ValueError):
                    pass
            return game

    def remove_game_cover(self, game_id: str) -> dict[str, Any]:
        """Detach a cover and delete only ORBIT's managed copy, never the original."""
        with self._lock:
            games = self._profile_load("games", [])
            if not isinstance(games, list):
                games = []
            game = next((g for g in games if g.get("id") == game_id), None)
            if game is None:
                raise KeyError("Juego no encontrado")
            old_cover = game.get("cover")
            old_path = self.paths.decode(old_cover) if old_cover else None
            game["cover"] = None
            game["cover_version"] = time.time_ns()
            self._profile_save("games", games)

            if old_path and not self._media_path_referenced_elsewhere(games, old_path, exclude_game_id=game_id):
                try:
                    resolved = old_path.resolve()
                    resolved.relative_to(self.paths.covers.resolve())
                    if resolved.is_file():
                        resolved.unlink(missing_ok=True)
                except (OSError, ValueError):
                    pass
            return game

    def _media_dir_for_kind(self, kind: str) -> Path:
        mapping = {
            "cover": self.paths.covers,
            "background": self.paths.backgrounds,
            "logo": self.paths.logos,
            "screenshot": self.paths.screenshots,
        }
        if kind not in mapping:
            raise ValueError("Tipo de imagen no válido.")
        return mapping[kind]

    def set_game_media(self, game_id: str, kind: str, source: str) -> dict[str, Any]:
        """Attach media using the same content-based pipeline as covers."""
        if kind == "cover":
            return self.set_game_cover(game_id, source)
        with self._lock:
            source_path = self.paths.decode(source)
            if not source_path or not source_path.exists() or not source_path.is_file():
                raise ValueError("La imagen seleccionada no existe.")
            games = self._profile_load("games", [])
            if not isinstance(games, list):
                games = []
            game = next((g for g in games if g.get("id") == game_id), None)
            if game is None:
                raise KeyError("Juego no encontrado")
            self._migrate_game(game)
            if game.get("demo"):
                raise ValueError("Solo puedes añadir imágenes a juegos reales.")

            directory = self._media_dir_for_kind(kind)
            directory.mkdir(parents=True, exist_ok=True)
            if kind == "screenshot":
                stem = directory / f"{game_id}-{uuid.uuid4().hex[:12]}"
                old_path = None
            else:
                stem = directory / str(game_id)
                old_value = game.get(kind)
                old_path = self.paths.decode(old_value) if old_value else None
            destination = store_image_file(source_path, stem, max_bytes=MAX_COVER_BYTES).resolve()
            destination.relative_to(directory.resolve())
            encoded = self.paths.encode(destination)
            if kind == "screenshot":
                screenshots = list(game.get("screenshots") or [])
                screenshots.append(encoded)
                dropped = screenshots[:-24]
                game["screenshots"] = screenshots[-24:]
            else:
                dropped = []
                game[kind] = encoded
            game[f"{kind}_version"] = time.time_ns()
            self._profile_save("games", games)

            for old_value in dropped:
                old_shot = self.paths.decode(old_value) if old_value else None
                if not old_shot or self._media_path_referenced_elsewhere(games, old_shot):
                    continue
                try:
                    old_shot.resolve().relative_to(directory.resolve())
                    old_shot.unlink(missing_ok=True)
                except (OSError, ValueError):
                    pass
            if old_path and old_path != destination and not self._media_path_referenced_elsewhere(games, old_path, exclude_game_id=game_id):
                try:
                    old_path.resolve().relative_to(directory.resolve())
                    old_path.unlink(missing_ok=True)
                except (OSError, ValueError):
                    pass
            return game

    def remove_game_media(self, game_id: str, kind: str, index: int | None = None) -> dict[str, Any]:
        if kind == "cover":
            return self.remove_game_cover(game_id)
        with self._lock:
            directory = self._media_dir_for_kind(kind)
            games = self._profile_load("games", [])
            if not isinstance(games, list):
                games = []
            game = next((g for g in games if g.get("id") == game_id), None)
            if game is None:
                raise KeyError("Juego no encontrado")
            self._migrate_game(game)
            if kind == "screenshot":
                shots = list(game.get("screenshots") or [])
                if index is None or index < 0 or index >= len(shots):
                    raise ValueError("Captura no válida.")
                value = shots.pop(index)
                game["screenshots"] = shots
            else:
                value = game.get(kind)
                game[kind] = None
            self._profile_save("games", games)
            if value:
                path = self.paths.decode(value)
                if path and not self._media_path_referenced_elsewhere(games, path, exclude_game_id=game_id):
                    try:
                        path.resolve().relative_to(directory.resolve())
                        path.unlink(missing_ok=True)
                    except (OSError, ValueError):
                        pass
            return game

    def remove_game(self, game_id: str) -> None:
        # Removes only the library entry. It never deletes the original game file.
        with self._lock:
            games = [g for g in self._profile_load("games", []) if g.get("id") != game_id]
            self._profile_save("games", games)

    def toggle_favorite(self, game_id: str) -> dict[str, Any]:
        with self._lock:
            games = self._profile_load("games", [])
            for game in games:
                if game.get("id") == game_id:
                    game["favorite"] = not bool(game.get("favorite"))
                    self._profile_save("games", games)
                    return game
            raise KeyError("Juego no encontrado")

    def add_game_folder(self, folder: str, platform: str) -> dict[str, Any]:
        with self._lock:
            path = self.paths.decode(folder)
            if not path or not path.exists() or not path.is_dir():
                raise ValueError("La carpeta indicada no existe.")
            platform_name = normalize_platform(platform, default="PC")
            if platform_name not in DEFAULT_EXTENSIONS:
                supported = ", ".join(DEFAULT_EXTENSIONS)
                raise ValueError(f"Plataforma no reconocida para escaneo. Usa una de estas: {supported}.")

            settings = self.settings()
            folders = settings.setdefault("game_folders", [])
            encoded = self.paths.encode(path)
            for existing in folders:
                if existing.get("path") == encoded:
                    if existing.get("platform") != platform_name:
                        raise ValueError(f"Esta carpeta ya está configurada como {existing.get('platform')}.")
                    return existing

            item = {"id": uuid.uuid4().hex, "path": encoded, "platform": platform_name}
            folders.append(item)
            self.save_settings({"game_folders": folders})
            return item

    def scan(self) -> dict[str, int]:
        with self._lock:
            settings = self.settings()
            folders = settings.get("game_folders", [])
            games = self._profile_load("games", [])
            if not isinstance(games, list):
                games = []
            existing_by_path = {g.get("path"): g for g in games if g.get("path")}
            found_paths: set[str] = set()
            added = 0
            refreshed = 0
            try:
                max_depth = max(0, min(32, int(settings.get("scanner", {}).get("max_depth", 8))))
            except (TypeError, ValueError):
                max_depth = 8

            for folder in folders:
                root = self.paths.decode(folder.get("path"))
                platform_name = normalize_platform(folder.get("platform"), default="PC")
                if not root or not root.exists() or not root.is_dir():
                    continue
                allowed = DEFAULT_EXTENSIONS.get(platform_name)
                if not allowed:
                    continue
                default_emulator_id = None if platform_name == "PC" else self._default_emulator_id(platform_name)
                root_depth = len(root.parts)
                for current, dirs, files in os.walk(root):
                    current_path = Path(current)
                    if len(current_path.parts) - root_depth >= max_depth:
                        dirs[:] = []
                    for filename in files:
                        candidate = current_path / filename
                        if candidate.suffix.lower() not in allowed:
                            continue
                        encoded = self.paths.encode(candidate)
                        if not encoded:
                            continue
                        found_paths.add(encoded)
                        if encoded in existing_by_path:
                            game = existing_by_path[encoded]
                            game["available"] = True
                            if not game.get("emulator_id") and default_emulator_id:
                                game["emulator_id"] = default_emulator_id
                            refreshed += 1
                        else:
                            game = {
                                "id": uuid.uuid4().hex,
                                "name": candidate.stem,
                                "platform": platform_name,
                                "path": encoded,
                                "executable": encoded if platform_name == "PC" else None,
                                "cover": None,
                                "description": "",
                                "favorite": False,
                                "last_played": None,
                                "play_time_seconds": 0,
                                "launch_count": 0,
                                "emulator_id": default_emulator_id,
                                "available": True,
                                "demo": False,
                                "accent": "NEW",
                                "added_at": utc_now(),
                            }
                            games.append(game)
                            existing_by_path[encoded] = game
                            added += 1

            missing = 0
            for game in games:
                if game.get("demo"):
                    continue
                if game.get("path") and game.get("path") not in found_paths:
                    decoded = self.paths.decode(game.get("path"))
                    current = bool(decoded and decoded.exists() and decoded.is_file())
                    if game.get("available") and not current:
                        missing += 1
                    game["available"] = current and self._game_available(game)

            if added:
                games = [g for g in games if not g.get("demo")]
            self._profile_save("games", games)
            return {"added": added, "refreshed": refreshed, "missing": missing, "total": len(games)}

    def collections(self) -> list[dict[str, Any]]:
        with self._lock:
            raw = self._profile_load("collections", [])
            return raw if isinstance(raw, list) else []

    def save_collection(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            items = self.collections()
            collection_id = str(payload.get("id") or uuid.uuid4().hex)
            name = str(payload.get("name") or "Colección").strip() or "Colección"
            game_ids = payload.get("game_ids") if isinstance(payload.get("game_ids"), list) else []
            valid_ids = {str(g.get("id")) for g in self.games() if not g.get("demo")}
            cleaned = []
            seen = set()
            for game_id in game_ids:
                text = str(game_id)
                if text in valid_ids and text not in seen:
                    cleaned.append(text)
                    seen.add(text)
            existing = next((x for x in items if x.get("id") == collection_id), None)
            if existing:
                existing.update({"name": name, "game_ids": cleaned, "updated_at": utc_now()})
                item = existing
            else:
                item = {"id": collection_id, "name": name, "game_ids": cleaned, "created_at": utc_now(), "updated_at": utc_now()}
                items.append(item)
            self._profile_save("collections", items)
            return item

    def delete_collection(self, collection_id: str) -> None:
        with self._lock:
            items = self.collections()
            if not any(x.get("id") == collection_id for x in items):
                raise KeyError("Colección no encontrada")
            self._profile_save("collections", [x for x in items if x.get("id") != collection_id])

    def profiles(self) -> dict[str, Any]:
        profiles = self._global_settings().get("profiles")
        return profiles if isinstance(profiles, dict) else {"active": "default", "select_on_start": True, "items": []}

    def _find_profile(self, profile_id: str) -> dict[str, Any]:
        item = next((x for x in self.profiles().get("items", []) if str(x.get("id")) == str(profile_id)), None)
        if item is None:
            raise KeyError("Perfil no encontrado")
        return item

    def add_profile(self, name: str, avatar: str = "orbit") -> dict[str, Any]:
        with self._lock:
            settings = self._global_settings()
            profiles = settings.setdefault("profiles", {"active": "default", "select_on_start": True, "items": []})
            items = profiles.setdefault("items", [])
            clean = str(name or "Perfil").strip()[:40] or "Perfil"
            avatar_id = str(avatar or "orbit").strip().lower()
            if avatar_id not in DEFAULT_PROFILE_AVATARS:
                avatar_id = "orbit"
            item = {"id": uuid.uuid4().hex, "name": clean, "avatar": avatar_id,
                    "color": "#65f4c5", "created_at": utc_now()}
            items.append(item)
            self.store.save("settings", settings)
            self._ensure_profile_data(str(item["id"]), with_demos=True)
            return item

    def update_profile(self, profile_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            settings = self._global_settings()
            profiles = settings.setdefault("profiles", {"active": "default", "select_on_start": True, "items": []})
            item = next((x for x in profiles.get("items", []) if str(x.get("id")) == str(profile_id)), None)
            if item is None:
                raise KeyError("Perfil no encontrado")
            if "name" in patch:
                item["name"] = str(patch.get("name") or item.get("name") or "Perfil").strip()[:40] or "Perfil"
            previous = str(item.get("avatar") or "")
            if "avatar" in patch:
                avatar = str(patch.get("avatar") or "orbit").strip().lower()
                if avatar not in DEFAULT_PROFILE_AVATARS:
                    raise ValueError("Avatar predeterminado no válido.")
                item["avatar"] = avatar
            if "color" in patch:
                color = str(patch["color"] or "").strip()
                if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
                    raise ValueError("Selecciona un color de perfil válido.")
                item["color"] = color.lower()
            self.store.save("settings", settings)
            if previous != item.get("avatar") and previous.startswith("@launcher/media/profiles/"):
                # Legacy profile registries can reference one shared image from
                # several profiles: never delete another profile's avatar.
                used_elsewhere = any(str(x.get("avatar") or "") == previous
                                     for x in profiles.get("items", []) if str(x.get("id")) != str(profile_id))
                old = self.paths.decode(previous)
                if not used_elsewhere and old and old.is_file():
                    old.unlink(missing_ok=True)
            return item

    def set_profile_avatar(self, profile_id: str, source_path: str) -> dict[str, Any]:
        with self._lock:
            item = self._find_profile(profile_id)
            source = Path(source_path).expanduser()
            if not source.exists() or not source.is_file():
                raise ValueError("No se encuentra la imagen seleccionada.")
            if source.stat().st_size > 15 * 1024 * 1024:
                raise ValueError("La foto de perfil no puede superar 15 MB.")
            target_dir = self.paths.root / "media" / "profiles"
            target_dir.mkdir(parents=True, exist_ok=True)
            # Validate by actual bytes and create the new image before touching
            # any existing avatar; a failed conversion leaves the old one intact.
            target = store_image_file(source, target_dir / f"{profile_id}-{uuid.uuid4().hex[:8]}", max_bytes=15 * 1024 * 1024)
            previous = str(item.get("avatar") or "")
            settings = self._global_settings()
            stored = next((x for x in settings.get("profiles", {}).get("items", []) if str(x.get("id")) == str(profile_id)), None)
            if stored is None:
                raise KeyError("Perfil no encontrado")
            stored["avatar"] = self.paths.encode(target)
            try:
                self.store.save("settings", settings)
            except Exception:
                target.unlink(missing_ok=True)
                raise
            if previous.startswith("@launcher/media/profiles/"):
                used_elsewhere = any(str(x.get("avatar") or "") == previous
                                     for x in settings.get("profiles", {}).get("items", [])
                                     if str(x.get("id")) != str(profile_id))
                old = self.paths.decode(previous)
                if not used_elsewhere and old and old != target and old.is_file():
                    old.unlink(missing_ok=True)
            return stored

    def reset_profile_avatar(self, profile_id: str, avatar: str = "orbit") -> dict[str, Any]:
        with self._lock:
            return self.update_profile(profile_id, {"avatar": avatar})

    def select_profile(self, profile_id: str) -> dict[str, Any]:
        with self._process_lock:
            active = [proc for proc in self._processes.values() if proc.poll() is None]
        if active:
            raise ValueError("Cierra los juegos o emuladores activos antes de cambiar de perfil para proteger las partidas.")
        with self._lock:
            settings = self._global_settings()
            profiles = settings.setdefault("profiles", {"active": "default", "select_on_start": True, "items": []})
            if not any(str(x.get("id")) == str(profile_id) for x in profiles.get("items", [])):
                raise KeyError("Perfil no encontrado")
            self._ensure_profile_data(str(profile_id), with_demos=True)
            profiles["active"] = str(profile_id)
            self.store.save("settings", settings)
            return profiles

    def delete_profile(self, profile_id: str, confirmed: bool = False) -> None:
        with self._process_lock:
            prefix = f"{profile_id}:"
            if any(key.startswith(prefix) and proc.poll() is None for key, proc in self._processes.items()):
                raise ValueError("Cierra los juegos de este perfil antes de eliminarlo.")
        if not confirmed:
            raise ValueError("Eliminar un perfil necesita confirmación explícita.")
        if str(profile_id) == "default":
            raise ValueError("El perfil Principal no se puede eliminar.")
        with self._lock:
            settings = self._global_settings()
            profiles = settings.setdefault("profiles", {"active": "default", "select_on_start": True, "items": []})
            items = profiles.setdefault("items", [])
            if not any(str(x.get("id")) == str(profile_id) for x in items):
                raise KeyError("Perfil no encontrado")
            # Profile deletion removes ORBIT metadata and portable copies for that
            # profile only. Shared physical game/emulator files and external saves are untouched.
            profiles["items"] = [x for x in items if str(x.get("id")) != str(profile_id)]
            if str(profiles.get("active")) == str(profile_id):
                profiles["active"] = "default"
            self.store.save("settings", settings)
            profile_data = self.paths.data / "profiles" / str(profile_id)
            profile_saves = self.paths.saves / "profiles" / str(profile_id)
            profile_backups = self.paths.backups / "profiles" / str(profile_id)
            saves_backups = self.paths.backups / "saves" / "profiles" / str(profile_id)
            for folder in (profile_data, profile_saves, profile_backups, saves_backups):
                if folder.exists():
                    shutil.rmtree(folder, ignore_errors=True)
            avatar_dir = self.paths.root / "media" / "profiles"
            for avatar_file in avatar_dir.glob(f"{profile_id}.*") if avatar_dir.exists() else []:
                avatar_file.unlink(missing_ok=True)

    def _prepare_profile_save_for_manual_operation(self, game: dict[str, Any]) -> str:
        """Ensure manual save operations target the active profile's live save.

        With profile isolation enabled, the game's configured save_path is a shared
        live location used by the game/emulator. Before backup/restore/sync we must
        swap in the active profile exactly as we do before launching a game.
        """
        profile_id = self._active_profile_id()
        settings = self._profile_settings_for(profile_id)
        isolation = bool(settings.get("saves", {}).get("profile_isolation", True))
        if isolation and game.get("save_path"):
            self.saves.prepare_profile_session(game, profile_id)
        return profile_id

    def backup_game_saves(self, game_id: str, reason: str = "manual") -> dict[str, Any]:
        game = next((g for g in self.games() if g.get("id") == game_id), None)
        if game is None:
            raise KeyError("Juego no encontrado")
        profile_id = self._prepare_profile_save_for_manual_operation(game)
        return self.saves.create_backup(game, reason=reason, profile_id=profile_id)

    def list_game_backups(self, game_id: str) -> list[dict[str, Any]]:
        if not any(g.get("id") == game_id for g in self.games()):
            raise KeyError("Juego no encontrado")
        return self.saves.list_backups(game_id, profile_id=self._active_profile_id())

    def restore_game_backup(self, game_id: str, backup_id: str, confirmed: bool = False) -> dict[str, Any]:
        game = next((g for g in self.games() if g.get("id") == game_id), None)
        if game is None:
            raise KeyError("Juego no encontrado")
        profile_id = self._prepare_profile_save_for_manual_operation(game)
        return self.saves.restore_backup(game, backup_id, confirmed=confirmed, profile_id=profile_id)

    def sync_game_saves(self, game_id: str, direction: str, confirmed: bool = False) -> dict[str, Any]:
        game = next((g for g in self.games() if g.get("id") == game_id), None)
        if game is None:
            raise KeyError("Juego no encontrado")
        profile_id = self._prepare_profile_save_for_manual_operation(game)
        return self.saves.sync(game, direction, confirmed=confirmed, profile_id=profile_id)

    def storage_info(self) -> dict[str, Any]:
        return storage_breakdown(self.paths)

    def steam_preview(self) -> list[dict[str, Any]]:
        return self.importer.steam_preview()

    def folder_import_preview(self, folder: str) -> list[dict[str, Any]]:
        return self.importer.folder_preview(folder)

    def import_items(self, items: list[dict[str, Any]]) -> dict[str, int]:
        with self._lock:
            if not isinstance(items, list):
                raise ValueError("La lista de importación no es válida.")
            games = self._profile_load("games", [])
            if not isinstance(games, list):
                games = []
            games = [g for g in games if not g.get("demo")]
            existing_keys = {
                (str(g.get("steam_app_id") or ""), str(g.get("path") or g.get("executable") or ""))
                for g in games
            }
            added = 0
            skipped = 0
            for raw in items[:5000]:
                if not isinstance(raw, dict):
                    skipped += 1
                    continue
                platform_name = normalize_platform(raw.get("platform"), default="PC")
                path_value = self.paths.encode(raw.get("path")) if raw.get("path") else None
                exe_value = self.paths.encode(raw.get("executable")) if raw.get("executable") else None
                steam_app_id = str(raw.get("steam_app_id") or "") or None
                key = (steam_app_id or "", str(path_value or exe_value or ""))
                if key in existing_keys:
                    skipped += 1
                    continue
                if not (path_value or exe_value or raw.get("launch_uri")):
                    skipped += 1
                    continue
                game = {
                    "id": uuid.uuid4().hex,
                    "name": str(raw.get("name") or "Juego importado").strip() or "Juego importado",
                    "platform": platform_name,
                    "path": path_value,
                    "executable": exe_value,
                    "cover": None,
                    "background": None,
                    "logo": None,
                    "screenshots": [],
                    "description": "",
                    "genre": "",
                    "year": "",
                    "developer": "",
                    "players": "",
                    "tags": [],
                    "status": "backlog",
                    "hidden": False,
                    "completed": False,
                    "notes": "",
                    "arguments": "",
                    "save_path": None,
                    "portable_save_path": None,
                    "favorite": False,
                    "last_played": None,
                    "play_time_seconds": 0,
                    "last_session_seconds": 0,
                    "region": str(raw.get("region") or ""),
                    "revision": str(raw.get("revision") or ""),
                    "performance_demand": int(raw.get("performance_demand")) if str(raw.get("performance_demand") or "").isdigit() else None,
                    "launch_count": 0,
                    "emulator_id": None if platform_name == "PC" else self._default_emulator_id(platform_name),
                    "available": bool(raw.get("available", True)),
                    "demo": False,
                    "accent": "NEW",
                    "source": str(raw.get("source") or "import"),
                    "steam_app_id": steam_app_id,
                    "launch_uri": raw.get("launch_uri") or None,
                    "added_at": utc_now(),
                }
                game["available"] = self._game_available(game)
                games.append(game)
                existing_keys.add(key)
                added += 1
            self._profile_save("games", games)
            return {"added": added, "skipped": skipped}

    def _process_key(self, profile_id: str, game_id: str) -> str:
        return f"{profile_id}:{game_id}"

    def active_sessions(self) -> list[dict[str, Any]]:
        profile_id = self._active_profile_id()
        prefix = f"{profile_id}:"
        with self._process_lock:
            alive: list[tuple[str, subprocess.Popen[Any]]] = []
            for key, process in list(self._processes.items()):
                if process.poll() is not None:
                    self._processes.pop(key, None)
                elif key.startswith(prefix):
                    alive.append((key[len(prefix):], process))
        games_by_id = {str(g.get("id")): g for g in self.games()}
        return [
            {"game_id": game_id, "name": games_by_id.get(game_id, {}).get("name", game_id), "pid": process.pid, "profile_id": profile_id}
            for game_id, process in alive
        ]

    def stop_game(self, game_id: str, confirmed: bool = False) -> dict[str, Any]:
        if not confirmed:
            raise ValueError("Cerrar un juego necesita confirmación explícita.")
        key = self._process_key(self._active_profile_id(), game_id)
        with self._process_lock:
            process = self._processes.get(key)
            if process is None or process.poll() is not None:
                raise ValueError("ORBIT no está monitorizando un proceso activo para ese juego en este perfil.")
            process.terminate()
            return {"stopping": True, "pid": process.pid}

    def local_metadata_guess(self, game_id: str) -> dict[str, Any]:
        """Conservative local metadata helper; never invents web metadata."""
        game = next((g for g in self.games() if g.get("id") == game_id), None)
        if game is None:
            raise KeyError("Juego no encontrado")
        target = self.paths.decode(game.get("path") or game.get("executable"))
        guess: dict[str, Any] = {"name": game.get("name")}
        if target:
            stem = target.stem.replace("_", " ").replace(".", " ")
            stem = " ".join(stem.split())
            if stem:
                guess["name"] = stem
            parent = target.parent if target.is_file() else target
            for suffix in COVER_EXTENSIONS:
                for candidate in (parent / f"{target.stem}{suffix}", parent / f"cover{suffix}", parent / f"folder{suffix}"):
                    if candidate.exists() and candidate.is_file() and _valid_cover_signature(candidate):
                        guess["cover_candidate"] = str(candidate)
                        break
                if guess.get("cover_candidate"):
                    break
        return guess

    def _split_emulator_args(self, arg_text: str) -> list[str]:
        args = shlex.split(arg_text, posix=(os.name != "nt"))
        if os.name == "nt":
            args = [a[1:-1] if len(a) >= 2 and a[0] == a[-1] and a[0] in ('"', "'") else a for a in args]
        return args

    def launch(self, game_id: str) -> dict[str, Any]:
        with self._lock:
            games = self._profile_load("games", [])
            if not isinstance(games, list):
                games = []
            game = next((g for g in games if g.get("id") == game_id), None)
            if not game:
                raise KeyError("Juego no encontrado")
            self._migrate_game(game)
            if game.get("demo"):
                raise ValueError("Este es un juego de demostración. Añade un juego real para ejecutarlo.")

            profile_id = self._active_profile_id()
            process_key = self._process_key(profile_id, game_id)
            with self._process_lock:
                existing_process = self._processes.get(process_key)
                if existing_process is not None and existing_process.poll() is None:
                    raise ValueError("Este juego ya está ejecutándose desde ORBIT en este perfil.")
                if existing_process is not None:
                    self._processes.pop(process_key, None)

            save_settings = self.settings().get("saves", {})
            if game.get("save_path") and save_settings.get("profile_isolation", True):
                self.saves.prepare_profile_session(game, profile_id)
            if game.get("save_path") and save_settings.get("auto_backup_before_launch"):
                try:
                    self.saves.create_backup(game, reason="auto-pre-launch", profile_id=profile_id)
                except ValueError:
                    pass

            command: list[str]
            cwd: str | None = None
            process: subprocess.Popen[Any] | None = None
            launch_uri = str(game.get("launch_uri") or "").strip()
            if launch_uri:
                if os.name != "nt":
                    raise ValueError("Los enlaces de lanzamiento de esta importación están disponibles en Windows.")
                os.startfile(launch_uri)  # type: ignore[attr-defined]
            elif game.get("emulator_id"):
                emulator = next((e for e in self.emulators() if e.get("id") == game.get("emulator_id")), None)
                if not emulator:
                    raise ValueError("El emulador configurado ya no existe.")
                emulator_exe = self.paths.decode(emulator.get("executable"))
                rom = self.paths.decode(game.get("path"))
                if not emulator_exe or not emulator_exe.exists() or not emulator_exe.is_file():
                    raise ValueError("No se encuentra el ejecutable del emulador.")
                if not rom or not rom.exists() or not rom.is_file():
                    raise ValueError("No se encuentra el archivo del juego.")
                arg_text = str(game.get("arguments") or emulator.get("arguments") or '"{rom}"').replace("{rom}", str(rom))
                args = self._split_emulator_args(arg_text)
                command = [str(emulator_exe), *args]
                workdir = self.paths.decode(emulator.get("working_directory"))
                cwd = str(workdir) if workdir and workdir.exists() and workdir.is_dir() else str(emulator_exe.parent)
                process = subprocess.Popen(command, cwd=cwd)
            else:
                target = self.paths.decode(game.get("executable") or game.get("path"))
                if not target or not target.exists() or not target.is_file():
                    raise ValueError("No se encuentra el ejecutable o archivo del juego.")
                if os.name == "nt" and target.suffix.lower() not in DEFAULT_EXTENSIONS["PC"]:
                    raise ValueError("Este archivo necesita un emulador o un ejecutable de PC compatible.")
                extra_args = self._split_emulator_args(str(game.get("arguments") or "")) if game.get("arguments") else []
                command = [str(target), *extra_args]
                cwd = str(target.parent)
                target_suffix = target.suffix.lower()
                if os.name == "nt" and target_suffix == ".lnk":
                    os.startfile(str(target))  # type: ignore[attr-defined]
                elif os.name == "nt" and target_suffix in {".bat", ".cmd"}:
                    process = subprocess.Popen(["cmd.exe", "/d", "/s", "/c", "call", str(target), *extra_args], cwd=cwd)
                else:
                    process = subprocess.Popen(command, cwd=cwd)

            started = time.monotonic()
            game["last_played"] = utc_now()
            game["launch_count"] = int(game.get("launch_count", 0)) + 1
            if game.get("status") == "backlog":
                game["status"] = "playing"
            game["available"] = self._game_available(game)
            self._profile_save("games", games)
            self._record_history(game, "started", profile_id=profile_id)

            if process is not None:
                with self._process_lock:
                    self._processes[process_key] = process
                threading.Thread(target=self._watch_process, args=(process, game_id, started, profile_id), daemon=True).start()
            return {"pid": process.pid if process is not None else None, "game": game}

    def _watch_process(self, process: subprocess.Popen[Any], game_id: str, started: float, profile_id: str) -> None:
        process_key = self._process_key(profile_id, game_id)
        try:
            process.wait()
            seconds = max(0, int(time.monotonic() - started))
            with self._lock:
                games = self._profile_load("games", [], profile_id)
                if not isinstance(games, list):
                    games = []
                game = next((g for g in games if g.get("id") == game_id), None)
                if game:
                    self._migrate_game(game)
                    game["play_time_seconds"] = int(game.get("play_time_seconds", 0)) + seconds
                    game["last_session_seconds"] = seconds
                    self._profile_save("games", games, profile_id)
                    self._record_history(game, "finished", seconds, profile_id=profile_id)
                    save_settings = self.settings() if self._active_profile_id() == profile_id else self._profile_settings_for(profile_id)
                    if game.get("save_path") and save_settings.get("saves", {}).get("profile_isolation", True):
                        try:
                            self.saves.capture_profile_session(game, profile_id)
                        except ValueError:
                            pass
                    if game.get("save_path") and save_settings.get("saves", {}).get("auto_backup_after_exit"):
                        try:
                            self.saves.create_backup(game, reason="auto-after-exit", profile_id=profile_id)
                        except ValueError:
                            pass
        except Exception:
            return
        finally:
            with self._process_lock:
                current = self._processes.get(process_key)
                if current is process:
                    self._processes.pop(process_key, None)

    def _record_history(self, game: dict[str, Any], event: str, seconds: int = 0, profile_id: str | None = None) -> None:
        with self._lock:
            history = self._profile_load("history", [], profile_id)
            if not isinstance(history, list):
                history = []
            history.append({
                "id": uuid.uuid4().hex,
                "game_id": game.get("id"),
                "game_name": game.get("name"),
                "event": event,
                "seconds": seconds,
                "at": utc_now(),
            })
            self._profile_save("history", history[-500:], profile_id)

    def history(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            raw = self._profile_load("history", [])
            if not isinstance(raw, list):
                return []
            return list(reversed(raw[-max(1, min(500, int(limit))):]))

    def stats(self) -> dict[str, Any]:
        with self._lock:
            real = [g for g in self.games() if not g.get("demo")]
            total_seconds = sum(int(g.get("play_time_seconds", 0)) for g in real)
            by_platform: dict[str, int] = {}
            for game in real:
                name = str(game.get("platform") or "Otra")
                by_platform[name] = by_platform.get(name, 0) + 1
            most_played = sorted(real, key=lambda x: int(x.get("play_time_seconds", 0)), reverse=True)[:8]
            recent = sorted([g for g in real if g.get("last_played")], key=lambda x: str(x.get("last_played")), reverse=True)[:8]
            history = self._profile_load("history", [])
            if not isinstance(history, list):
                history = []
            finished = [x for x in history if x.get("event") == "finished"]
            longest = max((int(x.get("seconds", 0)) for x in finished), default=0)
            active_days = sorted({str(x.get("at") or "")[:10] for x in history if x.get("at")}, reverse=True)[:90]
            return {
                "total_seconds": total_seconds,
                "games": len(real),
                "favorites": sum(1 for g in real if g.get("favorite")),
                "completed": sum(1 for g in real if g.get("status") == "completed" or g.get("completed")),
                "unplayed": sum(1 for g in real if int(g.get("launch_count", 0)) == 0),
                "sessions": len(finished),
                "longest_session_seconds": longest,
                "active_days": active_days,
                "by_platform": by_platform,
                "most_played": most_played,
                "recent": recent,
            }

    def diagnostics(self) -> list[dict[str, str]]:
        with self._lock:
            issues: list[dict[str, str]] = []
            for label, path in (
                ("Datos", self.paths.data),
                ("Carátulas", self.paths.covers),
                ("Backups", self.paths.backups),
            ):
                status = "ok" if path.exists() and os.access(path, os.W_OK) else "error"
                issues.append({"name": label, "status": status, "detail": str(path)})

            important = (
                ("Launcher", self.paths.root / "launcher.py"),
                ("Interfaz", self.paths.root / "app" / "static" / "index.html"),
                ("JavaScript", self.paths.root / "app" / "static" / "app.js"),
            )
            for label, path in important:
                issues.append({
                    "name": f"Archivo: {label}",
                    "status": "ok" if path.exists() and path.is_file() else "error",
                    "detail": str(path),
                })

            for emulator in self.emulators():
                issues.append({
                    "name": f"Emulador: {emulator.get('name')}",
                    "status": "ok" if emulator.get("available") else "warning",
                    "detail": emulator.get("executable") or "Sin ejecutable",
                })

            real_games = [g for g in self.games() if not g.get("demo")]
            unavailable = [g for g in real_games if not g.get("available")]
            issues.append({
                "name": "Juegos no disponibles",
                "status": "ok" if not unavailable else "warning",
                "detail": "Ninguno" if not unavailable else f"{len(unavailable)} juego(s) no se encuentran en su ruta o no tienen emulador disponible.",
            })

            missing_save_paths = []
            for game in real_games:
                configured = game.get("save_path")
                if not configured:
                    continue
                resolved = self.paths.decode(configured)
                if resolved is None or not resolved.exists():
                    missing_save_paths.append(game)
            issues.append({
                "name": "Rutas de partidas",
                "status": "ok" if not missing_save_paths else "warning",
                "detail": "Todas las rutas configuradas existen." if not missing_save_paths else f"{len(missing_save_paths)} juego(s) tienen una ruta de partidas configurada que no existe todavía.",
            })

            game_ids = {str(g.get("id")) for g in real_games}
            stale_refs = 0
            for collection in self.collections():
                for game_id in collection.get("game_ids", []):
                    if str(game_id) not in game_ids:
                        stale_refs += 1
            issues.append({
                "name": "Colecciones",
                "status": "ok" if stale_refs == 0 else "warning",
                "detail": "Sin referencias rotas." if stale_refs == 0 else f"{stale_refs} referencia(s) apuntan a juegos que ya no están en la biblioteca.",
            })

            for label, path in (("Fondos", self.paths.backgrounds), ("Logos", self.paths.logos), ("Capturas", self.paths.screenshots), ("Partidas portables", self.paths.saves)):
                issues.append({
                    "name": label,
                    "status": "ok" if path.exists() and os.access(path, os.W_OK) else "warning",
                    "detail": str(path),
                })
            return issues

    def prepare_for_other_pc(self) -> dict[str, Any]:
        """Check whether the active profile is portable enough for another PC."""
        with self._lock:
            games=[g for g in self.games() if not g.get("demo")]
            emulators=self.emulators()
            blockers=[]; warnings=[]; external=[]
            for game in games:
                target=game.get("executable") or game.get("path")
                decoded=self.paths.decode(target) if target else None
                if target and not str(target).startswith("@launcher/"):
                    external.append({"type":"game","name":game.get("name"),"path":str(target)})
                if not decoded or not decoded.exists():
                    blockers.append(f"Juego no disponible: {game.get('name')}")
                if normalize_platform(game.get("platform"), default="PC") != "PC" and not game.get("emulator_id"):
                    warnings.append(f"Sin emulador asignado: {game.get('name')}")
            for emu in emulators:
                target=emu.get("executable")
                decoded=self.paths.decode(target) if target else None
                if target and not str(target).startswith("@launcher/"):
                    external.append({"type":"emulator","name":emu.get("name"),"path":str(target)})
                if not decoded or not decoded.exists():
                    blockers.append(f"Emulador no disponible: {emu.get('name')}")
            if external:
                warnings.append(f"{len(external)} ruta(s) dependen del PC actual y pueden no existir en otro equipo.")
            usage=shutil.disk_usage(self.paths.root)
            if usage.free < 2*1024**3:
                warnings.append("Quedan menos de 2 GB libres en la unidad de ORBIT.")
            return {
                "ready": not blockers,
                "blockers": blockers,
                "warnings": warnings,
                "external_paths": external,
                "games": len(games),
                "emulators": len(emulators),
                "free_bytes": usage.free,
            }

    def duplicate_report(self) -> dict[str, Any]:
        with self._lock:
            games=[g for g in self.games() if not g.get("demo")]
            by_path={}; by_name={}
            for g in games:
                path=self.paths.decode(g.get("path") or g.get("executable"))
                if path:
                    key=str(path.resolve()).casefold(); by_path.setdefault(key,[]).append(g)
                key=(normalize_platform(g.get("platform"),default="PC"),str(g.get("name") or "").strip().casefold())
                by_name.setdefault(key,[]).append(g)
            groups=[]
            seen=set()
            for reason,mapping in (("Misma ruta",by_path),("Mismo nombre/plataforma",by_name)):
                for _,items in mapping.items():
                    ids=tuple(sorted(str(x.get("id")) for x in items))
                    if len(items)>1 and ids not in seen:
                        seen.add(ids); groups.append({"reason":reason,"games":[{"id":x.get("id"),"name":x.get("name"),"platform":x.get("platform")} for x in items]})
            return {"groups":groups,"count":len(groups)}

    def create_recovery_point(self, reason: str = "manual") -> dict[str, Any]:
        """Create a configuration-only recovery point; never copies or deletes game files."""
        with self._lock:
            self.paths.recovery.mkdir(parents=True,exist_ok=True)
            stamp=time.strftime("%Y%m%d-%H%M%S")
            pid=self._active_profile_id(); filename=f"ORBIT-Recovery-{safe_name(pid)}-{stamp}-{uuid.uuid4().hex[:8]}.zip"
            destination=(self.paths.recovery/filename).resolve(); destination.relative_to(self.paths.recovery.resolve())
            base=self.paths.data if pid=="default" else self.paths.data/"profiles"/pid
            allowed=["games.json","emulators.json","history.json","collections.json","profile_settings.json","ai_memory.json","custom_themes.json"]
            with zipfile.ZipFile(destination,"w",compression=zipfile.ZIP_DEFLATED) as z:
                meta={"format":"ORBIT-RECOVERY","profile_id":pid,"reason":str(reason)[:120],"created_at":int(time.time()),"version":2}
                z.writestr("recovery.json",json.dumps(meta,ensure_ascii=False,indent=2))
                for name in allowed:
                    src=base/name
                    if not src.is_file():
                        continue
                    try:
                        payload=json.loads(src.read_text(encoding="utf-8"))
                    except (OSError,json.JSONDecodeError):
                        continue
                    z.writestr(f"profile/{name}",json.dumps(scrub_sensitive(payload),ensure_ascii=False,indent=2))
                # Global settings is sanitized: credentials live only in data/.secrets
                # and are deliberately excluded from recovery archives.
                global_settings=self.paths.data/"settings.json"
                if global_settings.is_file():
                    try:
                        payload=json.loads(global_settings.read_text(encoding="utf-8"))
                        z.writestr("global/settings.json",json.dumps(scrub_sensitive(payload),ensure_ascii=False,indent=2))
                    except (OSError,json.JSONDecodeError):
                        pass
            return {"filename":filename,"path":self.paths.encode(destination),"size":destination.stat().st_size,"reason":reason}

    def list_recovery_points(self) -> list[dict[str, Any]]:
        self.paths.recovery.mkdir(parents=True,exist_ok=True)
        out=[]
        for path in sorted(self.paths.recovery.glob("ORBIT-Recovery-*.zip"),key=lambda p:p.stat().st_mtime,reverse=True):
            out.append({"filename":path.name,"path":self.paths.encode(path),"size":path.stat().st_size,"modified_at":datetime.fromtimestamp(path.stat().st_mtime,timezone.utc).isoformat()})
        return out[:50]

    def restore_recovery_point(self, recovery_path: str, confirmed: bool = False) -> dict[str, Any]:
        if not confirmed: raise ValueError("La restauración requiere confirmación.")
        decoded=self.paths.decode(recovery_path)
        if not decoded or not decoded.is_file(): raise ValueError("Punto de recuperación no encontrado.")
        decoded.resolve().relative_to(self.paths.recovery.resolve())
        # Create a rollback of the current state before replacing configuration.
        rollback=self.create_recovery_point("antes-de-restaurar")
        with self._lock, zipfile.ZipFile(decoded) as z:
            names=set(z.namelist())
            if "recovery.json" not in names: raise ValueError("Punto de recuperación no válido.")
            meta=json.loads(z.read("recovery.json"));
            if meta.get("format")!="ORBIT-RECOVERY": raise ValueError("Formato de recuperación no válido.")
            pid=str(meta.get("profile_id") or "default")
            # Recovery is intentionally restricted to the profile it was created for.
            if pid!=self._active_profile_id(): raise ValueError("Este punto pertenece a otro perfil.")
            base=self.paths.data if pid=="default" else self.paths.data/"profiles"/pid
            base.mkdir(parents=True,exist_ok=True)
            for name in ("games.json","emulators.json","history.json","collections.json","profile_settings.json","ai_memory.json","custom_themes.json"):
                member=f"profile/{name}"
                if member in names:
                    raw=z.read(member); json.loads(raw.decode("utf-8")); (base/name).write_bytes(raw)
            if "global/settings.json" in names:
                raw=z.read("global/settings.json"); json.loads(raw.decode("utf-8")); (self.paths.data/"settings.json").write_bytes(raw)
        return {"restored":decoded.name,"rollback":rollback}

    def _platform_destination(self, platform: str) -> Path:
        settings = self.settings()
        organization = settings.get("organization") or {}
        mapping = organization.get("platform_paths") or {}
        raw = mapping.get(platform)
        if raw:
            target = self.paths.decode(raw)
        else:
            target = self.paths.games / safe_name(platform)
        if target is None:
            target = self.paths.games / safe_name(platform)
        # v0.5 only lets automatic imports write inside ORBIT. External/multi-drive
        # organization can be added later with an explicit trust flow.
        try:
            target.resolve().relative_to(self.paths.root.resolve())
        except ValueError as exc:
            raise ValueError("La carpeta automática de importación debe estar dentro de ORBIT.") from exc
        target.mkdir(parents=True, exist_ok=True)
        return target

    def _emulator_destination(self, platform: str, name: str) -> Path:
        settings = self.settings()
        organization = settings.get("organization") or {}
        mapping = organization.get("emulator_paths") or {}
        raw = mapping.get(platform)
        if raw:
            target = self.paths.decode(raw)
        else:
            target = self.paths.emulators / safe_name(name)
        if target is None:
            target = self.paths.emulators / safe_name(name)
        try:
            target.resolve().relative_to(self.paths.root.resolve())
        except ValueError as exc:
            raise ValueError("La carpeta automática de emuladores debe estar dentro de ORBIT.") from exc
        target.mkdir(parents=True, exist_ok=True)
        return target

    def set_platform_destination(self, platform: str, path: str) -> dict[str, Any]:
        platform = normalize_platform(platform, default="PC")
        decoded = self.paths.decode(path)
        if decoded is None:
            raise ValueError("Selecciona una carpeta válida.")
        try:
            decoded.resolve().relative_to(self.paths.root.resolve())
        except ValueError as exc:
            raise ValueError("Por seguridad la carpeta automática debe estar dentro de ORBIT.") from exc
        decoded.mkdir(parents=True, exist_ok=True)
        settings = self.settings()
        org = dict(settings.get("organization") or {})
        mapping = dict(org.get("platform_paths") or {})
        mapping[platform] = self.paths.encode(decoded)
        org["platform_paths"] = mapping
        return self.save_settings({"organization": org})

    def set_emulator_destination(self, platform: str, path: str) -> dict[str, Any]:
        platform = normalize_platform(platform, default="Otra")
        decoded = self.paths.decode(path)
        if decoded is None:
            raise ValueError("Selecciona una carpeta válida.")
        try:
            decoded.resolve().relative_to(self.paths.root.resolve())
        except ValueError as exc:
            raise ValueError("Por seguridad la carpeta automática debe estar dentro de ORBIT.") from exc
        decoded.mkdir(parents=True, exist_ok=True)
        settings = self.settings()
        org = dict(settings.get("organization") or {})
        mapping = dict(org.get("emulator_paths") or {})
        mapping[platform] = self.paths.encode(decoded)
        org["emulator_paths"] = mapping
        return self.save_settings({"organization": org})

    def performance_for_game(self, game_id: str, system: dict[str, Any]) -> dict[str, Any]:
        game = next((g for g in self.games() if str(g.get("id")) == str(game_id)), None)
        if not game:
            raise KeyError("Juego no encontrado")
        return estimate_game_performance(game, system)

    def requirements_for_game(self, game_id: str) -> dict[str, Any]:
        game = next((g for g in self.games() if str(g.get("id")) == str(game_id)), None)
        if not game:
            raise KeyError("Juego no encontrado")
        return self.readiness.game_status(game, self.settings())

    def readiness_report(self) -> dict[str, Any]:
        problems: list[dict[str, Any]] = []
        for item in self.diagnostics():
            if str(item.get("status")) not in {"ok", "success"}:
                problems.append({"type": "diagnostic", **item})
        platforms = sorted({str(g.get("platform") or "PC") for g in self.games() if not g.get("demo")})
        requirements = []
        for platform in platforms:
            status = self.readiness.platform_status(platform, self.settings())
            if status.get("required"):
                requirements.append(status)
                for req in status.get("items") or []:
                    if not req.get("ok"):
                        problems.append({"type": "system-file", "platform": platform, "label": req.get("label"), "message": req.get("message")})
        portable = self.prepare_for_other_pc()
        for item in portable.get("issues") or []:
            problems.append({"type": "portability", **item})
        return {
            "ok": not problems,
            "problems": problems,
            "requirements": requirements,
            "portable": portable,
            "summary": "Todo correcto" if not problems else f"{len(problems)} punto(s) necesitan atención",
        }

    def custom_themes(self) -> list[dict[str, Any]]:
        return self.themes.list(self._active_profile_id())

    def save_custom_theme(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.themes.save(self._active_profile_id(), payload)

    def delete_custom_theme(self, theme_id: str) -> None:
        self.themes.delete(self._active_profile_id(), theme_id)
        if self.settings().get("theme") == theme_id:
            self.save_settings({"theme": "dark"})

    def export_custom_theme(self, theme_id: str) -> dict[str, Any]:
        return self.themes.export(self._active_profile_id(), theme_id)

    def import_custom_theme(self, source: str) -> dict[str, Any]:
        return self.themes.import_file(self._active_profile_id(), source)

    def ai_memory(self) -> dict[str, Any]:
        return self.assistant.memory(self._active_profile_id())

    def ask_ai(self, query: str) -> dict[str, Any]:
        settings = self.settings()
        if not (settings.get("ai") or {}).get("enabled", True):
            raise ValueError("ORBIT AI está desactivado en este perfil.")
        readiness = self.readiness_report()
        return self.assistant.ask(
            self._active_profile_id(), query, games=self.games(), emulators=self.emulators(),
            readiness=readiness, settings=settings,
        )

    def search_game_art(self, game_id: str, kind: str = "grid", provider_game_id: int | None = None) -> dict[str, Any]:
        game = next((g for g in self.games() if str(g.get("id")) == str(game_id)), None)
        if not game:
            raise KeyError("Juego no encontrado")
        key = self._steamgrid_key()
        if provider_game_id is not None:
            return self.cover_search.assets_for_game(provider_game_id, key, kind=kind)
        query = f"{game.get('name') or ''} {game.get('platform') or ''}".strip()
        return self.cover_search.search(query, key, kind=kind)

    def apply_game_art(self, game_id: str, kind: str, url: str) -> dict[str, Any]:
        game = next((g for g in self.games() if str(g.get("id")) == str(game_id)), None)
        if not game:
            raise KeyError("Juego no encontrado")
        if kind not in {"cover", "background", "logo"}:
            raise ValueError("Tipo de imagen no válido.")
        target_dir = self._media_dir_for_kind(kind)
        base = target_dir / f"online-{safe_name(str(game_id))}-{uuid.uuid4().hex[:8]}"
        downloaded = self.cover_search.download(url, base)
        try:
            return self.set_game_media(game_id, kind, str(downloaded))
        finally:
            downloaded.unlink(missing_ok=True)

    def _portable_config_for_export(self, profile_id: str) -> dict[str, Any]:
        settings = self._profile_settings_for(profile_id)
        config = {key: settings.get(key) for key in PROFILE_SETTING_KEYS if key in settings}
        config = scrub_sensitive(config)
        defaults = self.default_settings()

        # Never export source-PC absolute locations as receiver configuration.
        paths_cfg = dict(config.get("paths") or {})
        for key, value in list(paths_cfg.items()):
            if not str(value or "").startswith("@launcher/"):
                paths_cfg[key] = (defaults.get("paths") or {}).get(key)
        config["paths"] = {k: v for k, v in paths_cfg.items() if v}

        folders = []
        for item in config.get("game_folders") or []:
            if isinstance(item, dict) and str(item.get("path") or "").startswith("@launcher/"):
                folders.append(dict(item))
        config["game_folders"] = folders

        organization = dict(config.get("organization") or {})
        for map_key in ("platform_paths", "emulator_paths"):
            mapping = dict(organization.get(map_key) or {})
            organization[map_key] = {str(k): str(v) for k, v in mapping.items() if str(v or "").startswith("@launcher/")}
        for root_key, fallback in (("default_game_root", "@launcher/games"), ("default_emulator_root", "@launcher/emulators")):
            value = str(organization.get(root_key) or "")
            organization[root_key] = value if value.startswith("@launcher/") else fallback
        config["organization"] = organization

        system_files: dict[str, Any] = {}
        for platform, values in (config.get("system_files") or {}).items():
            if not isinstance(values, dict):
                continue
            clean_values = {str(k): str(v) for k, v in values.items() if str(v or "").startswith("@launcher/")}
            if clean_values:
                system_files[str(platform)] = clean_values
        config["system_files"] = system_files
        if isinstance(config.get("cover_search"), dict):
            config["cover_search"].pop("api_key_configured", None)
        return scrub_sensitive(config)

    def _portable_config_for_import(self, incoming: Any, emulator_ids: dict[str, str] | None = None) -> dict[str, Any]:
        raw = scrub_sensitive(incoming if isinstance(incoming, dict) else {})
        config = {key: raw.get(key) for key in PROFILE_SETTING_KEYS if key in raw}
        defaults = self.default_settings()
        paths_cfg = dict(config.get("paths") or {})
        for key, fallback in (defaults.get("paths") or {}).items():
            value = str(paths_cfg.get(key) or fallback)
            if not value.startswith("@launcher/"):
                value = str(fallback)
            try:
                self.paths.decode(value)
            except ValueError:
                value = str(fallback)
            paths_cfg[key] = value
        config["paths"] = paths_cfg

        folders = []
        for item in config.get("game_folders") or []:
            if not isinstance(item, dict):
                continue
            value = str(item.get("path") or "")
            if not value.startswith("@launcher/"):
                continue
            try:
                self.paths.decode(value)
            except ValueError:
                continue
            folders.append({"path": value, "platform": normalize_platform(item.get("platform"), default="PC")})
        config["game_folders"] = folders

        organization = dict(config.get("organization") or {})
        platform_paths: dict[str, str] = {}
        for platform, value in (organization.get("platform_paths") or {}).items():
            text = str(value or "")
            platform_name = normalize_platform(platform, default="Otra")
            if text.startswith("@launcher/"):
                try:
                    self.paths.decode(text)
                    platform_paths[platform_name] = text
                except ValueError:
                    pass
            else:
                platform_paths[platform_name] = f"@launcher/games/{safe_name(platform_name)}"
        emulator_paths: dict[str, str] = {}
        for platform, value in (organization.get("emulator_paths") or {}).items():
            text = str(value or "")
            platform_name = normalize_platform(platform, default="Otra")
            if text.startswith("@launcher/"):
                try:
                    self.paths.decode(text)
                    emulator_paths[platform_name] = text
                except ValueError:
                    pass
            else:
                emulator_paths[platform_name] = "@launcher/emulators"
        config["organization"] = {
            "platform_paths": platform_paths,
            "emulator_paths": emulator_paths,
            "default_game_root": "@launcher/games",
            "default_emulator_root": "@launcher/emulators",
        }

        system_files: dict[str, Any] = {}
        for platform, values in (config.get("system_files") or {}).items():
            if not isinstance(values, dict):
                continue
            clean_values: dict[str, str] = {}
            for key, value in values.items():
                text = str(value or "")
                if text.startswith("@launcher/"):
                    try:
                        self.paths.decode(text)
                        clean_values[str(key)] = text
                    except ValueError:
                        pass
            if clean_values:
                system_files[str(platform)] = clean_values
        config["system_files"] = system_files

        if isinstance(config.get("default_emulators"), dict):
            mapping: dict[str, str] = {}
            for platform, source_id in config["default_emulators"].items():
                target_id = (emulator_ids or {}).get(str(source_id))
                if target_id:
                    mapping[normalize_platform(platform, default="Otra")] = target_id
            config["default_emulators"] = mapping
        if isinstance(config.get("cover_search"), dict):
            config["cover_search"].pop("api_key_configured", None)
        return scrub_sensitive(config)

    @staticmethod
    def _pack_components(manifest: dict[str, Any]) -> dict[str, bool]:
        raw = manifest.get("components") if isinstance(manifest.get("components"), dict) else {}
        if raw:
            return {key: bool(raw.get(key)) for key in ("games", "emulators", "configuration", "saves", "media", "other")}
        options = manifest.get("options") if isinstance(manifest.get("options"), dict) else {}
        # v1/v2 packs always carried game metadata; infer the remaining parts.
        return {
            "games": bool(manifest.get("games")),
            "emulators": bool(manifest.get("emulators")),
            "configuration": bool(manifest.get("configuration")),
            "saves": bool(options.get("include_saves")),
            "media": options.get("include_media") is not False and any((g.get("pack_media") or {}) for g in manifest.get("games") or []),
            "other": bool(manifest.get("other")),
        }

    def _pack_duplicate_game(self, packed: dict[str, Any], current: list[dict[str, Any]]) -> dict[str, Any] | None:
        steam_id = str(packed.get("steam_app_id") or "").strip()
        if steam_id:
            hit = next((g for g in current if not g.get("demo") and str(g.get("steam_app_id") or "") == steam_id), None)
            if hit:
                return hit
        launch_uri = str(packed.get("launch_uri") or "").strip().casefold()
        if launch_uri:
            hit = next((g for g in current if not g.get("demo") and str(g.get("launch_uri") or "").strip().casefold() == launch_uri), None)
            if hit:
                return hit
        name = str(packed.get("name") or "").strip().casefold()
        platform = normalize_platform(packed.get("platform"), default="PC")
        region = str(packed.get("region") or "").strip().casefold()
        revision = str(packed.get("revision") or "").strip().casefold()
        return next((
            g for g in current if not g.get("demo")
            and str(g.get("name") or "").strip().casefold() == name
            and normalize_platform(g.get("platform"), default="PC") == platform
            and str(g.get("region") or "").strip().casefold() == region
            and str(g.get("revision") or "").strip().casefold() == revision
        ), None)

    def _unique_profile_import_name(self, base_name: str) -> str:
        existing = {str(x.get("name") or "").strip().casefold() for x in self.profiles().get("items", [])}
        base = str(base_name or "Perfil importado").strip()[:40] or "Perfil importado"
        candidate = base
        index = 2
        while candidate.casefold() in existing:
            suffix = f" ({index})"
            candidate = (base[: max(1, 40 - len(suffix))] + suffix).strip()
            index += 1
        return candidate

    def create_orbitpack(
        self,
        game_ids: list[str] | None = None,
        include_game_files: bool = True,
        include_emulators: bool = True,
        include_media: bool = True,
        include_saves: bool = False,
        name: str | None = None,
        *,
        include_games: bool = True,
        include_configuration: bool = False,
        include_other: bool = False,
        full_profile: bool = False,
        destination: str | Path | None = None,
        progress: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        """Create an extended ORBIT Pack v2 while keeping v0.5 call compatibility."""
        if progress:
            progress({"phase": "preparing", "percent": 0.01, "processed_bytes": 0, "total_bytes": 0, "eta_seconds": None, "current": None})
        with self._lock:
            if full_profile:
                include_games = include_game_files = include_emulators = include_media = include_saves = include_configuration = include_other = True
                game_ids = None
            profile_id = self._active_profile_id()
            all_games = [g for g in self.games() if not g.get("demo")]
            # Backward compatibility: omitted game_ids means all games. An
            # explicit list, including an empty list, is an exact selection.
            selected_ids = None if game_ids is None else {str(x) for x in game_ids}
            games = list(all_games) if selected_ids is None else [g for g in all_games if str(g.get("id")) in selected_ids]
            need_game_index = include_games or include_media or include_saves
            indexed_games = games if need_game_index else []
            emulators = self.emulators()
            # Emulator descriptors are needed for a game export so the receiver
            # can reuse an existing emulator. Media-only / saves-only exports
            # must not include unrelated emulator metadata.
            referenced = {str(g.get("emulator_id")) for g in games if include_games and g.get("emulator_id")}
            explicit_emulator_ids = {str(e.get("id")) for e in emulators} if include_emulators else set()
            emulator_ids_to_manifest = referenced | explicit_emulator_ids
            files: list[tuple[Path, str]] = []
            manifest_games: list[dict[str, Any]] = []
            manifest_emulators: list[dict[str, Any]] = []

            # Emulator descriptors are kept when game associations need them even
            # if their binaries are not selected. This lets the receiver reuse an
            # already-installed emulator without creating a duplicate.
            for emu in emulators:
                # Configuration-only exports must not smuggle emulator metadata.
                # When games/media/saves are indexed, only descriptors required
                # to preserve their associations are included. When no game is
                # indexed, an explicit emulator export includes all emulators.
                if str(emu.get("id")) not in emulator_ids_to_manifest:
                    continue
                item = {k: v for k, v in emu.items() if k not in {"available", "working_directory", "executable", "id"}}
                item["source_id"] = str(emu.get("id") or "")
                item["pack_executable"] = None
                if include_emulators:
                    exe = self.paths.decode(emu.get("executable"))
                    if exe and exe.is_file():
                        try:
                            rel = exe.resolve().relative_to(self.paths.emulators.resolve())
                            top = rel.parts[0] if rel.parts else safe_name(emu.get("name") or "Emulator")
                            source_dir = self.paths.emulators / top
                            folder_key = safe_name(str(emu.get("id") or top))
                            for src in source_dir.rglob("*"):
                                if src.is_file() and not src.is_symlink():
                                    arc = f"payload/emulators/{folder_key}/{src.relative_to(source_dir).as_posix()}"
                                    files.append((src, arc))
                            item["pack_executable"] = f"payload/emulators/{folder_key}/{exe.relative_to(source_dir).as_posix()}"
                        except ValueError:
                            # External emulator: metadata is enough for receiver-side reuse.
                            pass
                manifest_emulators.append(scrub_sensitive(item))

            for game in indexed_games:
                item = {
                    k: v for k, v in game.items()
                    if k not in {
                        "id", "available", "demo", "path", "executable", "save_path", "portable_save_path",
                        "cover", "background", "logo", "screenshots", "cover_version", "background_version",
                        "logo_version", "screenshot_version", "emulator_id",
                    }
                }
                item["source_id"] = str(game.get("id") or "")
                item["source_emulator_id"] = str(game.get("emulator_id") or "") or None
                item["pack_game_file"] = None
                item["pack_media"] = {}
                item["pack_save"] = None
                # Preserve the basename even in metadata-only packs. The receiver
                # can reconnect an existing ROM in its automatic platform folder.
                source_game = self.paths.decode(game.get("path") or game.get("executable"))
                if source_game:
                    item["original_filename"] = source_game.name
                if include_games and include_game_files:
                    src = source_game
                    if not src or not src.is_file():
                        src = self.paths.decode(game.get("executable"))
                    if src and src.is_file():
                        arc = f"payload/games/{safe_name(normalize_platform(game.get('platform'), default='Otra'))}/{safe_name(str(game.get('id')))}{src.suffix}"
                        files.append((src, arc))
                        item["pack_game_file"] = arc
                        item["original_filename"] = src.name
                    elif not game.get("launch_uri"):
                        # Silently exporting only metadata was the reason ROMs
                        # never arrived at the receiving ORBIT. Fail before
                        # writing a misleading 'complete' archive instead.
                        raise ValueError(
                            f"No se puede exportar la ROM de «{game.get('name') or 'Juego'}»: "
                            "el archivo original no existe. Revisa su ruta en la biblioteca."
                        )
                if include_media:
                    for kind in ("cover", "background", "logo"):
                        src = self.paths.decode(game.get(kind))
                        if src and src.is_file():
                            arc = f"payload/media/{kind}s/{safe_name(str(game.get('id')))}{src.suffix.casefold()}"
                            files.append((src, arc))
                            item["pack_media"][kind] = arc
                    shots = []
                    for index, value in enumerate(game.get("screenshots") or []):
                        src = self.paths.decode(value)
                        if src and src.is_file():
                            arc = f"payload/media/screenshots/{safe_name(str(game.get('id')))}-{index}{src.suffix.casefold()}"
                            files.append((src, arc))
                            shots.append(arc)
                    if shots:
                        item["pack_media"]["screenshots"] = shots
                if include_saves:
                    save_src = self.saves.portable_target(game, profile_id)
                    if not save_src.exists() and game.get("save_path"):
                        candidate = self.paths.decode(game.get("save_path"))
                        if candidate and candidate.exists():
                            try:
                                candidate.resolve().relative_to(self.paths.root.resolve())
                                save_src = candidate
                            except ValueError:
                                save_src = self.saves.portable_target(game, profile_id)
                    if save_src.exists():
                        base_arc = f"payload/saves/{safe_name(str(game.get('id')))}"
                        if save_src.is_file():
                            arc = f"{base_arc}/{safe_name(save_src.name)}"
                            files.append((save_src, arc))
                            item["pack_save"] = {"type": "file", "members": [arc]}
                        else:
                            members = []
                            for src in save_src.rglob("*"):
                                if src.is_file() and not src.is_symlink():
                                    arc = f"{base_arc}/{src.relative_to(save_src).as_posix()}"
                                    files.append((src, arc))
                                    members.append(arc)
                            if members:
                                item["pack_save"] = {"type": "directory", "members": members}
                manifest_games.append(scrub_sensitive(item))

            profile = self._find_profile(profile_id)
            profile_meta: dict[str, Any] = {
                "source_id": profile_id,
                "name": str(profile.get("name") or "Perfil"),
                "avatar": str(profile.get("avatar") or "orbit") if not str(profile.get("avatar") or "").startswith("@launcher/") else "orbit",
                "color": str(profile.get("color") or "#65f4c5"),
            }
            avatar_value = str(profile.get("avatar") or "")
            if include_other and avatar_value.startswith("@launcher/"):
                avatar = self.paths.decode(avatar_value)
                if avatar and avatar.is_file():
                    arc = f"payload/profile/avatar{avatar.suffix.casefold()}"
                    files.append((avatar, arc))
                    profile_meta["avatar_member"] = arc

            other: dict[str, Any] = {}
            if include_other:
                other = {
                    "collections": self._profile_load("collections", [], profile_id),
                    "history": self._profile_load("history", [], profile_id),
                    "ai_memory": self.assistant.memory(profile_id),
                    "custom_themes": self.themes.list(profile_id),
                }

            manifest = {
                "source_version": (self.paths.root / "VERSION").read_text(encoding="utf-8").strip() if (self.paths.root / "VERSION").exists() else "unknown",
                "scope": "profile" if full_profile else ("configuration" if include_configuration and not any((include_games, include_emulators, include_media, include_saves, include_other)) else "selection"),
                "profile": profile_meta,
                "profile_name": profile_meta["name"],  # v2-friendly field
                "games": manifest_games,
                "emulators": manifest_emulators,
                "configuration": self._portable_config_for_export(profile_id) if include_configuration else {},
                "other": scrub_sensitive(other) if include_other else {},
                "components": {
                    "games": bool(include_games),
                    "emulators": bool(include_emulators),
                    "configuration": bool(include_configuration),
                    "saves": bool(include_saves),
                    "media": bool(include_media),
                    "other": bool(include_other),
                },
                "options": {
                    "include_game_files": bool(include_game_files),
                    "include_emulators": bool(include_emulators),
                    "include_media": bool(include_media),
                    "include_saves": bool(include_saves),
                    "include_configuration": bool(include_configuration),
                    "include_other": bool(include_other),
                    "full_profile": bool(full_profile),
                },
                "layout_policy": "receiver-decides",
            }
            def pack_progress(info: dict[str, Any]) -> None:
                if progress is None:
                    return
                mapped = dict(info)
                raw_percent = float(mapped.get("percent") or 0.0)
                mapped["percent"] = min(1.0, 0.05 + (0.95 * raw_percent))
                progress(mapped)

            path = self.orbitpacks.create(manifest, files, name=name, destination=destination, progress=pack_progress if progress else None)
            return {
                "path": self.paths.encode(path), "filename": path.name,
                "games": len(manifest_games) if include_games else 0,
                "roms": sum(bool(g.get("pack_game_file")) for g in manifest_games),
                "emulators": len(manifest_emulators) if include_emulators else 0,
                "size": path.stat().st_size, "components": manifest["components"], "scope": manifest["scope"],
            }

    def inspect_orbitpack(self, pack_path: str) -> dict[str, Any]:
        decoded = self.paths.decode(pack_path)
        if not decoded:
            raise ValueError("Selecciona un ORBIT Pack.")
        info = self.orbitpacks.inspect(decoded, verify_files=True)
        manifest = info["manifest"]
        platforms: dict[str, int] = {}
        destinations: dict[str, str] = {}
        duplicate_count = 0
        current = self.games()
        for g in manifest.get("games") or []:
            if not isinstance(g, dict):
                continue
            p = normalize_platform(g.get("platform"), default="Otra")
            platforms[p] = platforms.get(p, 0) + 1
            organization = (self.settings().get("organization") or {}).get("platform_paths") or {}
            target = organization.get(p) or f"@launcher/games/{safe_name(p)}"
            destinations[p] = str(target)
            if self._pack_duplicate_game(g, current):
                duplicate_count += 1
        components = self._pack_components(manifest)
        profile = manifest.get("profile") if isinstance(manifest.get("profile"), dict) else {"name": manifest.get("profile_name") or "Perfil"}
        rom_files = sum(bool(g.get("pack_game_file")) for g in manifest.get("games") or [] if isinstance(g, dict))
        rom_missing = sum(not g.get("pack_game_file") and not g.get("launch_uri")
                          for g in manifest.get("games") or [] if isinstance(g, dict))
        return {
            "path": str(decoded), "size": info["size"], "version": (manifest.get("version") or 1),
            "scope": manifest.get("scope") or "selection", "profile": profile,
            "games": len(manifest.get("games") or []), "emulators": len(manifest.get("emulators") or []),
            "rom_files": rom_files, "rom_missing": rom_missing,
            "platforms": platforms, "destinations": destinations, "duplicates": duplicate_count,
            "options": manifest.get("options") or {}, "components": components,
        }

    def _merge_pack_other(self, other: dict[str, Any], game_ids: dict[str, str], config_conflict: str) -> None:
        current_collections = self._profile_load("collections", [])
        if not isinstance(current_collections, list):
            current_collections = []
        names = {str(x.get("name") or "").strip().casefold(): x for x in current_collections if isinstance(x, dict)}
        ids = {str(x.get("id") or "") for x in current_collections if isinstance(x, dict)}
        for raw in other.get("collections") or []:
            if not isinstance(raw, dict):
                continue
            remapped = [game_ids.get(str(x)) for x in raw.get("game_ids") or []]
            remapped = [x for x in remapped if x]
            name = str(raw.get("name") or "Colección importada").strip()[:60] or "Colección importada"
            existing = names.get(name.casefold())
            if existing:
                existing["game_ids"] = list(dict.fromkeys([*(existing.get("game_ids") or []), *remapped]))
            else:
                item = dict(raw)
                item["name"] = name
                item["game_ids"] = remapped
                requested = str(item.get("id") or "")
                if not requested or requested in ids:
                    requested = uuid.uuid4().hex
                item["id"] = requested
                ids.add(requested)
                current_collections.append(item)
                names[name.casefold()] = item
        self._profile_save("collections", current_collections)

        current_history = self._profile_load("history", [])
        if not isinstance(current_history, list):
            current_history = []
        seen = {json.dumps(x, ensure_ascii=False, sort_keys=True) for x in current_history if isinstance(x, dict)}
        for raw in other.get("history") or []:
            if not isinstance(raw, dict):
                continue
            item = dict(raw)
            if item.get("game_id"):
                mapped = game_ids.get(str(item.get("game_id")))
                if not mapped:
                    continue
                item["game_id"] = mapped
            sig = json.dumps(item, ensure_ascii=False, sort_keys=True)
            if sig not in seen:
                current_history.append(item)
                seen.add(sig)
        self._profile_save("history", current_history[-500:])

        incoming_memory = other.get("ai_memory") if isinstance(other.get("ai_memory"), dict) else {}
        if incoming_memory:
            current_memory = self.assistant.memory(self._active_profile_id())
            current_prefs = dict(current_memory.get("preferences") or {})
            incoming_prefs = dict(incoming_memory.get("preferences") or {})
            prefs = _deep_merge(incoming_prefs, current_prefs) if config_conflict == "keep-existing" else _deep_merge(current_prefs, incoming_prefs)
            recent = list(dict.fromkeys([*(incoming_memory.get("recent_queries") or []), *(current_memory.get("recent_queries") or [])]))[:20]
            self._profile_save("ai_memory", {"preferences": prefs, "recent_queries": recent})

        current_themes = self.themes.list(self._active_profile_id())
        theme_ids = {str(x.get("id") or "") for x in current_themes}
        theme_names = {str(x.get("name") or "").casefold() for x in current_themes}
        changed = False
        for raw in other.get("custom_themes") or []:
            if not isinstance(raw, dict):
                continue
            item = dict(raw)
            if str(item.get("id") or "") in theme_ids or str(item.get("name") or "").casefold() in theme_names:
                continue
            cleaned = ThemeManager._clean(item, str(item.get("id") or f"custom-{uuid.uuid4().hex[:12]}"))
            current_themes.append(cleaned)
            theme_ids.add(cleaned["id"])
            theme_names.add(str(cleaned.get("name") or "").casefold())
            changed = True
        if changed:
            self._profile_save("custom_themes", current_themes)

    def import_orbitpack(
        self,
        pack_path: str,
        conflict: str = "skip",
        *,
        components: list[str] | None = None,
        profile_strategy: str = "merge-active",
        config_conflict: str = "keep-existing",
        progress: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        if conflict not in {"skip", "keep-both", "replace-metadata"}:
            raise ValueError("Política de conflicto no válida.")
        if profile_strategy not in {"merge-active", "new-profile"}:
            raise ValueError("Estrategia de perfil no válida.")
        if config_conflict not in {"keep-existing", "import-preferred"}:
            raise ValueError("Política de configuración no válida.")
        decoded = self.paths.decode(pack_path)
        if not decoded:
            raise ValueError("Selecciona un ORBIT Pack.")
        started_at = time.monotonic()
        copied_bytes = 0
        unpacked_bytes = 0
        last_percent = 0.

        def emit(info: dict[str, Any]) -> None:
            nonlocal unpacked_bytes, last_percent
            unpacked_bytes = max(unpacked_bytes, int(info.get("total_bytes") or 0) // 2)
            if progress:
                elapsed = max(0.001, time.monotonic() - started_at)
                pct = max(last_percent, min(0.99, float(info.get("percent") or 0.)))
                last_percent = pct
                progress({**info, "percent": pct, "eta_seconds": (elapsed / pct * (1-pct)) if pct > .02 else None})

        emit({"phase": "verifying", "percent": 0., "processed_bytes": 0, "total_bytes": 0, "current": None})
        temp, root, manifest = self.orbitpacks.extract(decoded, progress=emit if progress else None)
        available = self._pack_components(manifest)
        if components is None:
            selected = {key for key, enabled in available.items() if enabled}
        else:
            selected = {str(x) for x in components if str(x) in available and available.get(str(x))}
        if not selected:
            temp.cleanup()
            raise ValueError("Selecciona al menos un tipo de contenido para importar.")

        total_steps = max(1, (len(manifest.get("emulators") or []) if "emulators" in selected or "games" in selected else 0)
                          + len(manifest.get("games") or []) + 2)
        completed_steps = 0
        # The archive has been verified and extracted; applying each entry is
        # another observable unit of work (including metadata-only entries).
        def applied(label: str) -> None:
            nonlocal completed_steps
            completed_steps += 1
            emit({"phase": "importing", "percent": .60 + .39 * min(1., completed_steps / total_steps),
                  "processed_bytes": unpacked_bytes * 2 + copied_bytes,
                  "total_bytes": unpacked_bytes * 2 + copied_bytes,
                  "current": label})

        def copy_file(src: Path, dest: Path, *, display_name: str | None = None) -> None:
            nonlocal copied_bytes
            dest.parent.mkdir(parents=True, exist_ok=True)
            size = max(1, src.stat().st_size)
            done = 0
            created = False
            try:
                with src.open("rb") as inp:
                    with dest.open("xb") as out:
                        created = True
                        for chunk in iter(lambda: inp.read(1024 * 1024), b""):
                            out.write(chunk)
                            done += len(chunk)
                            copied_bytes += len(chunk)
                            emit({"phase": "importing", "percent": .60 + .39 * min(1., (completed_steps + done / size) / total_steps),
                                  "processed_bytes": unpacked_bytes * 2 + copied_bytes,
                                  "total_bytes": unpacked_bytes * 2 + copied_bytes,
                                  "current": display_name or src.name})
                shutil.copystat(src, dest)
            except Exception:
                if created:
                    dest.unlink(missing_ok=True)
                raise

        imported_paths: list[Path] = []
        original_active = self._active_profile_id()
        global_before = self.store.load("settings", {})
        before_profile = {
            name: self._profile_load(name, default, original_active)
            for name, default in (
                ("games", []), ("emulators", []), ("history", []), ("collections", []),
                ("profile_settings", {}), ("ai_memory", {"preferences": {}, "recent_queries": []}), ("custom_themes", []),
            )
        }
        rollback_point = self.create_recovery_point("antes-de-importar-orbitpack")
        created_profile_id: str | None = None
        target_profile_id = original_active

        try:
            required = sum(p.stat().st_size for p in root.rglob("*") if p.is_file())
            try:
                if required > shutil.disk_usage(self.paths.root).free:
                    raise ValueError("No hay espacio libre suficiente para importar este ORBIT Pack.")
            except OSError:
                pass

            profile_meta = manifest.get("profile") if isinstance(manifest.get("profile"), dict) else {}
            if profile_strategy == "new-profile":
                name = self._unique_profile_import_name(str(profile_meta.get("name") or manifest.get("profile_name") or "Perfil importado"))
                avatar = str(profile_meta.get("avatar") or "orbit")
                if avatar not in DEFAULT_PROFILE_AVATARS:
                    avatar = "orbit"
                new_profile = self.add_profile(name, avatar)
                created_profile_id = str(new_profile["id"])
                incoming_color = str(profile_meta.get("color") or "")
                if re.fullmatch(r"#[0-9a-fA-F]{6}", incoming_color):
                    self.update_profile(created_profile_id, {"color": incoming_color})
                self.select_profile(created_profile_id)
                target_profile_id = created_profile_id
                before_target = None
            else:
                before_target = before_profile

            # The pack may contain file payloads for components not selected;
            # integrity was already verified, but only selected content is copied.
            imported_emulators: dict[str, str] = {}
            existing_emus = self.emulators()
            for packed in manifest.get("emulators") or []:
                applied(str(packed.get("name") or "Emulador") if isinstance(packed, dict) else "Emulador")
                if not isinstance(packed, dict):
                    continue
                platform = normalize_platform(packed.get("platform"), default="Otra")
                packed_name = str(packed.get("name") or "Emulador")
                source_id = str(packed.get("source_id") or packed.get("id") or "")
                matching = next((
                    e for e in existing_emus
                    if str(e.get("name") or "").casefold() == packed_name.casefold()
                    and normalize_platform(e.get("platform"), default="Otra") == platform
                    and e.get("available")
                ), None)
                if matching:
                    imported_emulators[source_id] = str(matching.get("id"))
                    continue
                if "emulators" not in selected:
                    continue
                pack_exe = packed.get("pack_executable")
                if not pack_exe:
                    continue
                src_exe = (root / str(pack_exe)).resolve()
                src_exe.relative_to(root)
                parts = Path(str(pack_exe)).parts
                try:
                    idx = parts.index("emulators")
                    folder_name = parts[idx + 1]
                except (ValueError, IndexError):
                    continue
                src_dir = root / "payload" / "emulators" / folder_name
                dest_dir = self._emulator_destination(platform, packed_name or folder_name)
                if src_dir.is_dir():
                    if any(dest_dir.iterdir()):
                        dest_dir = dest_dir.parent / f"{dest_dir.name}-{uuid.uuid4().hex[:6]}"
                    # Do not overwrite any receiver files, even on failure.
                    dest_dir.mkdir(parents=True, exist_ok=True)
                    imported_paths.append(dest_dir)
                    for source_file in src_dir.rglob("*"):
                        if source_file.is_file():
                            copy_file(source_file, dest_dir / source_file.relative_to(src_dir))
                    rel_exe = src_exe.relative_to(src_dir)
                    dest_exe = dest_dir / rel_exe
                    item = self.add_emulator({
                        "name": packed_name, "platform": platform, "executable": str(dest_exe),
                        "arguments": packed.get("arguments") or '"{rom}"', "working_directory": str(dest_dir),
                    })
                    existing_emus.append(item)
                    imported_emulators[source_id] = str(item.get("id"))

            added = skipped = metadata_only = saves_imported = media_imported = roms_imported = 0
            save_conflicts = 0
            save_locations: list[str] = []
            game_id_map: dict[str, str] = {}
            current = self.games()

            def place_rom(packed_game: dict[str, Any], platform: str, title: str) -> str | None:
                """Place a ROM in the receiver's existing automatic platform folder.

                Reuse identical files instead of making unnecessary duplicates;
                never overwrite a different ROM or an existing user's file.
                """
                nonlocal roms_imported
                arc = packed_game.get("pack_game_file")
                if not arc:
                    return None  # Earlier metadata-only .orbitpack files remain importable.
                src = (root / str(arc)).resolve()
                src.relative_to(root)
                if not src.is_file():
                    raise ValueError(f"Falta la ROM de «{title}» dentro del ORBIT Pack.")
                dest_dir = self._platform_destination(platform)
                original_name = safe_name(str(packed_game.get("original_filename") or src.name))
                filename = original_name if Path(original_name).suffix else original_name + src.suffix
                stem, suffix = Path(filename).stem, Path(filename).suffix
                dest = dest_dir / filename
                if dest.is_file() and sha256_file(dest) == sha256_file(src):
                    return str(dest)
                if dest.exists():
                    dest = dest_dir / f"{stem}-{uuid.uuid4().hex[:6]}{suffix}"
                copy_file(src, dest, display_name=filename)
                imported_paths.append(dest)
                roms_imported += 1
                return str(dest)

            def restore_packed_game_preferences(new_game: dict[str, Any], packed_game: dict[str, Any]) -> dict[str, Any]:
                """Keep favourites/play statistics on freshly imported games only."""
                games_on_disk = self._profile_load("games", [])
                for stored_game in games_on_disk:
                    if stored_game.get("id") != new_game.get("id"):
                        continue
                    for key in ("favorite", "hidden"):
                        stored_game[key] = bool(packed_game.get(key, False))
                    for key in ("play_time_seconds", "last_session_seconds", "launch_count"):
                        try:
                            stored_game[key] = min(2 ** 40, max(0, int(packed_game.get(key) or 0)))
                        except (ValueError, TypeError, OverflowError):
                            stored_game[key] = 0
                    for key in ("last_played", "added_at"):
                        value = packed_game.get(key)
                        if isinstance(value, str) and len(value) <= 80:
                            stored_game[key] = value
                    self._profile_save("games", games_on_disk)
                    return stored_game
                return new_game

            for packed in manifest.get("games") or []:
                applied(str(packed.get("name") or "Juego") if isinstance(packed, dict) else "Juego")
                if not isinstance(packed, dict):
                    continue
                source_game_id = str(packed.get("source_id") or packed.get("id") or "")
                name = str(packed.get("name") or "Juego")
                platform = normalize_platform(packed.get("platform"), default="PC")
                region = str(packed.get("region") or "")
                revision = str(packed.get("revision") or "")
                duplicate = self._pack_duplicate_game(packed, current)
                mapped_emu = imported_emulators.get(str(packed.get("source_emulator_id") or packed.get("emulator_id") or ""))
                game: dict[str, Any] | None = duplicate
                if duplicate:
                    game_id_map[source_game_id] = str(duplicate.get("id"))

                if "games" in selected:
                    if duplicate and conflict == "skip":
                        skipped += 1
                        # A previous metadata-only import can leave the game in
                        # the library without a ROM. Re-importing a complete
                        # pack must repair that SAME game, not skip the payload.
                        existing_file = self.paths.decode(duplicate.get("path") or duplicate.get("executable"))
                        if (not existing_file or not existing_file.is_file()) and packed.get("pack_game_file"):
                            restored_path = place_rom(packed, platform, name)
                            repair = {"path": restored_path}
                            if platform == "PC":
                                repair["executable"] = restored_path
                            if mapped_emu and not duplicate.get("emulator_id"):
                                repair["emulator_id"] = mapped_emu
                            game = self.update_game(str(duplicate.get("id")), repair)
                            skipped -= 1
                    elif duplicate and conflict == "replace-metadata":
                        patch = {
                            "description": packed.get("description"), "genre": packed.get("genre"), "year": packed.get("year"),
                            "developer": packed.get("developer"), "players": packed.get("players"), "tags": packed.get("tags"),
                            "notes": packed.get("notes"), "region": region, "revision": revision,
                            "performance_demand": packed.get("performance_demand"),
                        }
                        if mapped_emu:
                            patch["emulator_id"] = mapped_emu
                        existing_file = self.paths.decode(duplicate.get("path") or duplicate.get("executable"))
                        if (not existing_file or not existing_file.is_file()) and packed.get("pack_game_file"):
                            restored_path = place_rom(packed, platform, name)
                            patch["path"] = restored_path
                            if platform == "PC":
                                patch["executable"] = restored_path
                        game = self.update_game(str(duplicate.get("id")), patch)
                    else:
                        game_path = place_rom(packed, platform, name)
                        if game_path:
                            game = self.add_game({
                                "name": name, "platform": platform, "path": game_path,
                                "executable": game_path if platform == "PC" else None,
                                "description": packed.get("description"), "genre": packed.get("genre"), "year": packed.get("year"),
                                "developer": packed.get("developer"), "players": packed.get("players"), "tags": packed.get("tags"),
                                "status": packed.get("status"), "notes": packed.get("notes"), "arguments": packed.get("arguments"),
                                "region": region, "revision": revision, "performance_demand": packed.get("performance_demand"),
                                "emulator_id": mapped_emu, "source": "orbitpack",
                                "steam_app_id": packed.get("steam_app_id"), "launch_uri": packed.get("launch_uri"),
                            })
                            game = restore_packed_game_preferences(game, packed)
                            current.append(game)
                            game_id_map[source_game_id] = str(game.get("id"))
                            added += 1
                        elif not duplicate:
                            # The old implementation silently dropped metadata-
                            # only exports, which made Import look like a no-op.
                            # Register an unavailable library entry at the
                            # receiver's existing automatic destination instead.
                            dest_dir = self._platform_destination(platform)
                            filename = safe_name(str(packed.get("original_filename") or name))
                            candidate = dest_dir / filename
                            # If the filename exists, reconnect it; otherwise
                            # preserve a portable missing-file reference.
                            game = self.add_game({
                                "name": name, "platform": platform, "path": str(candidate),
                                "executable": str(candidate) if platform == "PC" else None,
                                "description": packed.get("description"), "genre": packed.get("genre"),
                                "year": packed.get("year"), "developer": packed.get("developer"),
                                "players": packed.get("players"), "tags": packed.get("tags"),
                                "status": packed.get("status"), "notes": packed.get("notes"),
                                "arguments": packed.get("arguments"), "region": region,
                                "revision": revision, "performance_demand": packed.get("performance_demand"),
                                "emulator_id": mapped_emu, "source": "orbitpack", "launch_uri": packed.get("launch_uri"),
                                "steam_app_id": packed.get("steam_app_id"),
                            })
                            game = restore_packed_game_preferences(game, packed)
                            current.append(game)
                            game_id_map[source_game_id] = str(game.get("id"))
                            metadata_only += int(not candidate.is_file())
                            added += 1

                if not game:
                    continue

                # Media import is non-destructive for an existing receiver game:
                # existing cover/background/logo wins; screenshots can be appended.
                if "media" in selected:
                    media = packed.get("pack_media") or {}
                    for kind in ("cover", "background", "logo"):
                        arc = media.get(kind) if isinstance(media, dict) else None
                        if arc and not game.get(kind):
                            src = (root / str(arc)).resolve()
                            src.relative_to(root)
                            if src.is_file():
                                updated = self.set_game_media(str(game.get("id")), kind, str(src))
                                created = self.paths.decode(updated.get(kind))
                                if created and created.exists():
                                    imported_paths.append(created)
                                    media_imported += 1
                                game = updated
                    for arc in (media.get("screenshots") or []) if isinstance(media, dict) else []:
                        src = (root / str(arc)).resolve()
                        src.relative_to(root)
                        if src.is_file():
                            updated = self.set_game_media(str(game.get("id")), "screenshot", str(src))
                            shots = updated.get("screenshots") or []
                            if shots:
                                created = self.paths.decode(shots[-1])
                                if created and created.exists():
                                    imported_paths.append(created)
                                    media_imported += 1
                            game = updated

                if "saves" in selected:
                    save_info = packed.get("pack_save") or {}
                    members = (save_info.get("members") or []) if isinstance(save_info, dict) else []
                    if members:
                        target = self.saves.portable_target(game, self._active_profile_id())
                        if target.exists():
                            # Preserve v0.5's separate non-destructive import
                            # folder; never overwrite an existing save.
                            target = target.with_name(f"{target.name}-imported-{uuid.uuid4().hex[:6]}")
                            save_conflicts += 1
                        target.mkdir(parents=True, exist_ok=True)
                        imported_paths.append(target)
                        base_prefix = f"payload/saves/{safe_name(source_game_id)}/"
                        for arc in members:
                            src = (root / str(arc)).resolve()
                            src.relative_to(root)
                            if not src.is_file():
                                continue
                            rel = str(arc)
                            if rel.startswith(base_prefix):
                                rel = rel[len(base_prefix):]
                            out = (target / rel).resolve()
                            out.relative_to(target.resolve())
                            out.parent.mkdir(parents=True, exist_ok=True)
                            if out.exists():
                                out = out.with_name(f"{out.stem}-imported-{uuid.uuid4().hex[:6]}{out.suffix}")
                            copy_file(src, out)
                        saves_imported += 1
                        save_locations.append(self.paths.encode(target) or str(target))

            if "configuration" in selected and isinstance(manifest.get("configuration"), dict):
                incoming_config = self._portable_config_for_import(manifest.get("configuration"), imported_emulators)
                current_config = {k: self.settings().get(k) for k in PROFILE_SETTING_KEYS if k in self.settings()}
                if config_conflict == "keep-existing":
                    merged_config = _deep_merge(incoming_config, current_config)
                else:
                    merged_config = _deep_merge(current_config, incoming_config)
                self.save_settings(merged_config)

            if "other" in selected and isinstance(manifest.get("other"), dict):
                self._merge_pack_other(scrub_sensitive(manifest["other"]), game_id_map, config_conflict)
                avatar_member = str(profile_meta.get("avatar_member") or "")
                if created_profile_id and avatar_member:
                    src = (root / avatar_member).resolve()
                    src.relative_to(root)
                    if src.is_file():
                        updated_avatar = self.set_profile_avatar(created_profile_id, str(src))
                        avatar_path = self.paths.decode(updated_avatar.get("avatar"))
                        if avatar_path and avatar_path.exists():
                            imported_paths.append(avatar_path)

            applied("Guardando cambios")
            if progress:
                progress({"phase": "done", "percent": 1., "processed_bytes": unpacked_bytes * 2 + copied_bytes,
                          "total_bytes": unpacked_bytes * 2 + copied_bytes, "eta_seconds": 0., "current": None})

            return {
                "added": added, "skipped": skipped, "metadata_only": metadata_only,
                "roms": roms_imported,
                "emulators": len({v for v in imported_emulators.values()}), "saves": saves_imported,
                "media": media_imported, "profile_id": target_profile_id, "profile_created": bool(created_profile_id),
                "save_conflicts": save_conflicts, "save_locations": save_locations,
                "components": sorted(selected), "rollback": rollback_point,
            }
        except Exception:
            # Restore exact receiver metadata and remove only physical payload
            # created by this import. The recovery point remains available too.
            try:
                self.store.save("settings", global_before if isinstance(global_before, dict) else {})
                if created_profile_id:
                    shutil.rmtree(self.paths.data / "profiles" / created_profile_id, ignore_errors=True)
                    shutil.rmtree(self.paths.backups / "profiles" / created_profile_id, ignore_errors=True)
                else:
                    for name, value in before_profile.items():
                        self._profile_save(name, value, original_active)
            finally:
                for path in reversed(imported_paths):
                    try:
                        if path.is_dir():
                            shutil.rmtree(path, ignore_errors=True)
                        else:
                            path.unlink(missing_ok=True)
                    except OSError:
                        pass
            raise
        finally:
            temp.cleanup()


    def _game_available(self, game: dict[str, Any]) -> bool:
        if game.get("demo"):
            return False
        if game.get("launch_uri"):
            path = self.paths.decode(game.get("path")) if game.get("path") else None
            return bool(path is None or path.exists())
        target = self.paths.decode(game.get("executable") or game.get("path"))
        if not target or not target.exists() or not target.is_file():
            return False
        emulator_id = game.get("emulator_id")
        if emulator_id:
            emulator = next((e for e in self.emulators() if e.get("id") == emulator_id), None)
            return bool(emulator and emulator.get("available"))
        return normalize_platform(game.get("platform"), default="PC") == "PC"
