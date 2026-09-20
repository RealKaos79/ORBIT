from __future__ import annotations

import re
import unicodedata
from typing import Any

from app.core.paths import PortablePaths
from app.core.storage import JsonStore
from app.services.ai_runtime import LocalModelRuntime, OnlineSearchRuntime


EMULATOR_HINTS = {
    "NES": "Mesen o Mesen Community Edition",
    "SNES": "Snes9x o Mesen",
    "Nintendo 64": "Project64",
    "Game Boy": "SameBoy",
    "Game Boy Color": "SameBoy",
    "Game Boy Advance": "mGBA",
    "Nintendo DS": "melonDS",
    "Nintendo 3DS": "Azahar",
    "Nintendo Switch": "un emulador de Switch compatible configurado por ti",
    "GameCube": "Dolphin",
    "Wii": "Dolphin",
    "PlayStation": "DuckStation",
    "PlayStation 2": "PCSX2",
    "PSP": "PPSSPP",
    "Dreamcast": "Flycast",
    "Mega Drive": "Kega Fusion o un núcleo compatible",
    "Arcade": "MAME",
}

PLATFORM_TERMS = {
    "nintendo switch": "Nintendo Switch", "switch": "Nintendo Switch",
    "playstation 2": "PlayStation 2", "ps2": "PlayStation 2",
    "playstation": "PlayStation", "ps1": "PlayStation", "psx": "PlayStation",
    "gamecube": "GameCube", "game cube": "GameCube", "wii": "Wii",
    "nintendo 3ds": "Nintendo 3DS", "3ds": "Nintendo 3DS",
    "nintendo ds": "Nintendo DS", "nds": "Nintendo DS",
    "nintendo 64": "Nintendo 64", "n64": "Nintendo 64",
    "game boy advance": "Game Boy Advance", "gba": "Game Boy Advance",
    "game boy color": "Game Boy Color", "gbc": "Game Boy Color",
    "game boy": "Game Boy", "snes": "SNES", "super nintendo": "SNES",
    "nes": "NES", "psp": "PSP", "dreamcast": "Dreamcast",
    "mega drive": "Mega Drive", "genesis": "Mega Drive", "arcade": "Arcade", "mame": "Arcade",
    "pc": "PC",
}


def _plain(text: str) -> str:
    folded = unicodedata.normalize("NFKD", str(text or ""))
    no_marks = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return " ".join(re.findall(r"[a-z0-9]+", no_marks.casefold()))


class OrbitAssistant:
    """Offline-first assistant with optional local LLM and explicit online lookup.

    The deterministic action layer remains available at all times. A configured
    local model receives only a compact ORBIT context and no filesystem write
    capability. Online search is a separate opt-in path and never becomes a
    dependency for normal assistant use.
    """

    def __init__(self, paths: PortablePaths) -> None:
        self.paths = paths
        self.local_model = LocalModelRuntime()
        self.online_search = OnlineSearchRuntime()

    def _store(self, profile_id: str) -> JsonStore:
        base = self.paths.data if profile_id == "default" else self.paths.data / "profiles" / profile_id
        backup = self.paths.backups / "profiles" / profile_id / "assistant"
        return JsonStore(self.paths, base_dir=base, backup_dir=backup)

    def memory(self, profile_id: str) -> dict[str, Any]:
        value = self._store(profile_id).load("ai_memory", {"preferences": {}, "recent_queries": []})
        return value if isinstance(value, dict) else {"preferences": {}, "recent_queries": []}

    def _remember_query(self, profile_id: str, query: str) -> None:
        mem = self.memory(profile_id)
        recent = [str(x) for x in mem.get("recent_queries") or []]
        recent = ([query.strip()] + [x for x in recent if x != query.strip()])[:20]
        mem["recent_queries"] = recent
        self._store(profile_id).save("ai_memory", mem)

    def set_preference(self, profile_id: str, key: str, value: str) -> dict[str, Any]:
        mem = self.memory(profile_id)
        prefs = mem.setdefault("preferences", {})
        prefs[str(key)[:80]] = str(value)[:300]
        self._store(profile_id).save("ai_memory", mem)
        return mem

    @staticmethod
    def _platform_from_text(normalized: str, games: list[dict[str, Any]]) -> str | None:
        # Prefer longer aliases so "playstation 2" is not swallowed by "playstation".
        for term in sorted(PLATFORM_TERMS, key=len, reverse=True):
            if re.search(rf"\b{re.escape(term)}\b", normalized):
                return PLATFORM_TERMS[term]
        for game in games:
            name = _plain(str(game.get("name") or ""))
            if name and len(name) >= 3 and name in normalized:
                return str(game.get("platform") or "PC")
        return None

    def _emulator_answer(self, normalized: str, games: list[dict[str, Any]], emulators: list[dict[str, Any]]) -> dict[str, Any] | None:
        emulator_words = ("emulador", "emular", "abrir rom", "ejecutar rom", "correr rom")
        need_words = ("necesito", "hace falta", "usar", "sirve", "recomienda", "cual", "que")
        if not any(x in normalized for x in emulator_words):
            return None
        if not any(x in normalized for x in need_words) and "emulador" not in normalized:
            return None
        platform = self._platform_from_text(normalized, games)
        if not platform:
            return {
                "kind": "emulator-help",
                "answer": "Dime la consola o el nombre del juego y te indicaré qué emulador necesita ORBIT.",
                "items": [],
                "engine": "offline-integrated",
            }
        if platform == "PC":
            return {"kind": "emulator-help", "answer": "Los juegos de PC normalmente se ejecutan de forma nativa y no necesitan emulador.", "items": [], "engine": "offline-integrated"}
        configured = [e for e in emulators if str(e.get("platform") or "") == platform]
        available = [e for e in configured if e.get("available")]
        if available:
            names = ", ".join(str(e.get("name") or "Emulador") for e in available[:3])
            return {
                "kind": "emulator-help",
                "answer": f"Para {platform} ya tienes configurado {names}. ORBIT puede usarlo al asociarlo al juego.",
                "items": [{"id": e.get("id"), "name": e.get("name"), "platform": e.get("platform"), "available": bool(e.get("available"))} for e in available[:5]],
                "engine": "offline-integrated",
            }
        suggestion = EMULATOR_HINTS.get(platform, "un emulador compatible")
        return {
            "kind": "emulator-help",
            "answer": f"Para {platform} necesitas configurar {suggestion} en ORBIT y después asociarlo al juego.",
            "items": [],
            "engine": "offline-integrated",
        }

    @staticmethod
    def _local_model_context(games: list[dict[str, Any]], emulators: list[dict[str, Any]], readiness: dict[str, Any] | None, memory: dict[str, Any]) -> dict[str, Any]:
        compact_games = [
            {
                "name": g.get("name"), "platform": g.get("platform"), "favorite": bool(g.get("favorite")),
                "available": bool(g.get("available")), "last_played": g.get("last_played"), "tags": (g.get("tags") or [])[:8],
            }
            for g in games if not g.get("demo")
        ][:120]
        compact_emulators = [
            {"name": e.get("name"), "platform": e.get("platform"), "available": bool(e.get("available"))}
            for e in emulators
        ][:60]
        return {
            "games": compact_games,
            "emulators": compact_emulators,
            "readiness": {"ok": bool((readiness or {}).get("ok")), "problems": (readiness or {}).get("problems", [])[:20]},
            "preferences": memory.get("preferences", {}),
        }

    def ask(
        self,
        profile_id: str,
        query: str,
        *,
        games: list[dict[str, Any]],
        emulators: list[dict[str, Any]] | None = None,
        readiness: dict[str, Any] | None = None,
        settings: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        text = str(query or "").strip()
        if not text:
            raise ValueError("Escribe una petición para ORBIT AI.")
        self._remember_query(profile_id, text)
        normalized = _plain(text)
        low = text.casefold()
        emulators = emulators or []
        ai_settings = (settings or {}).get("ai") if isinstance(settings, dict) else {}
        ai_settings = ai_settings if isinstance(ai_settings, dict) else {}
        memory = self.memory(profile_id)

        if any(x in normalized for x in ("reescribe el codigo", "modifica tu codigo", "borra orbit", "elimina orbit")):
            return {"kind": "safety", "answer": "Puedo diagnosticar ORBIT y preparar un informe, pero no reescribo ni borro el programa desde la IA.", "items": [], "engine": "offline-integrated"}

        if "recuerda" in normalized and "prefiero" in normalized:
            match = re.search(r"prefiero\s+(.+)$", text, flags=re.IGNORECASE)
            value = match.group(1).strip() if match else text
            self.set_preference(profile_id, "nota", value)
            return {"kind": "memory", "answer": "He guardado esa preferencia solo para este perfil.", "items": [], "engine": "offline-integrated"}

        wants_online = any(x in normalized for x in ("busca online", "busca en internet", "buscar online", "internet", "en la web"))
        online_cfg = ai_settings.get("online_search") if isinstance(ai_settings.get("online_search"), dict) else {}
        if wants_online and online_cfg.get("enabled"):
            clean_query = re.sub(r"(?i)\b(busca|buscar)\s+(online|en\s+internet|en\s+la\s+web)\b", "", text).strip() or text
            try:
                results = self.online_search.search(clean_query, online_cfg)
                if results:
                    local_cfg = ai_settings.get("local_model") if isinstance(ai_settings.get("local_model"), dict) else {}
                    if local_cfg.get("enabled"):
                        context = self._local_model_context(games, emulators, readiness, memory)
                        context["online_results"] = results
                        try:
                            answer = self.local_model.generate(local_cfg, clean_query, context)
                            return {"kind": "online-search", "answer": answer, "items": results, "engine": "local-model+online"}
                        except Exception:
                            pass
                    return {"kind": "online-search", "answer": f"He encontrado {len(results)} resultado(s) online. La IA offline sigue disponible aunque cierres Internet.", "items": results, "engine": "online-search"}
            except Exception:
                # Network failure must never break the offline assistant.
                pass

        emulator_answer = self._emulator_answer(normalized, games, emulators)
        if emulator_answer:
            return emulator_answer

        if "favorit" in normalized:
            items = [g for g in games if g.get("favorite") and not g.get("demo")]
            return self._games_answer("Estos son tus favoritos", items)

        if any(x in normalized for x in ("sin jugar", "no haya jugado", "no he jugado", "sin estrenar")):
            items = [g for g in games if not g.get("demo") and not g.get("last_played") and int(g.get("launch_count") or 0) == 0]
            return self._games_answer("Juegos que todavía no has iniciado", items)

        platform = self._platform_from_text(normalized, games)
        if platform and any(x in normalized for x in ("juegos de", "juego de", "que tengo", "biblioteca", "mostrar", "ensena")):
            items = [g for g in games if str(g.get("platform")) == platform and not g.get("demo")]
            return self._games_answer(f"Juegos de {platform}", items)

        if any(x in normalized for x in ("estado", "esta bien", "listo mi orbit", "problemas", "diagnostico")) and readiness:
            problems = readiness.get("problems") or []
            if problems:
                return {"kind": "status", "answer": f"He encontrado {len(problems)} punto(s) que necesitan atención.", "items": problems[:20], "engine": "offline-integrated"}
            return {"kind": "status", "answer": "ORBIT no ha detectado problemas en la comprobación actual.", "items": [], "engine": "offline-integrated"}

        if any(x in normalized for x in ("que juego", "a que juego", "recomienda", "recomiendame", "elige un juego")):
            candidates = [g for g in games if not g.get("demo") and g.get("available")]
            candidates.sort(key=lambda g: (bool(g.get("last_played")), int(g.get("launch_count") or 0), str(g.get("name") or "")))
            return self._games_answer("Podrías jugar a uno de estos", candidates[:5])

        local_cfg = ai_settings.get("local_model") if isinstance(ai_settings.get("local_model"), dict) else {}
        if local_cfg.get("enabled"):
            try:
                context = self._local_model_context(games, emulators, readiness, memory)
                answer = self.local_model.generate(local_cfg, text, context)
                return {"kind": "local-model", "answer": answer, "items": [], "engine": "local-model"}
            except Exception:
                # Continue into deterministic local fallback.
                pass

        words = [w for w in normalized.split() if len(w) >= 3 and w not in {"para", "como", "quiero", "puedo", "tengo", "orbit"}]
        scored: list[tuple[int, dict[str, Any]]] = []
        for game in games:
            hay = _plain(" ".join(str(game.get(k) or "") for k in ("name", "platform", "genre", "developer", "description", "notes")))
            hay += " " + _plain(" ".join(str(x) for x in game.get("tags") or []))
            score = sum(1 for w in words if w in hay)
            if score:
                scored.append((score, game))
        scored.sort(key=lambda x: (-x[0], str(x[1].get("name") or "")))
        if scored:
            return self._games_answer("He encontrado estas coincidencias en tu biblioteca", [g for _, g in scored[:10]])
        return {
            "kind": "help",
            "answer": "Puedo entender peticiones sobre juegos, emuladores, favoritos, estado de ORBIT y recomendaciones sin depender de frases exactas. Si configuras un modelo local, también puedo responder preguntas más abiertas completamente offline.",
            "items": [],
            "engine": "offline-integrated",
        }

    @staticmethod
    def _games_answer(title: str, games: list[dict[str, Any]]) -> dict[str, Any]:
        items = [{"id": g.get("id"), "name": g.get("name"), "platform": g.get("platform"), "available": bool(g.get("available"))} for g in games[:20]]
        return {"kind": "games", "answer": f"{title}: {len(games)} resultado(s).", "items": items, "engine": "offline-integrated"}
