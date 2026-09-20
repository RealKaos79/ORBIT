from __future__ import annotations

import os
import subprocess
import webbrowser
from typing import Any

# Curated project/home pages. URLs are deliberately allow-listed so the local
# ORBIT API cannot be abused to open arbitrary URLs supplied by another page.
EMULATOR_SITES: list[dict[str, Any]] = [
    {"id": "mesen", "name": "Mesen CE", "platform": "NES / SNES / GB / GBA y más", "url": "https://github.com/nesdev-org/MesenCE", "status": "official-project"},
    {"id": "snes9x", "name": "Snes9x", "platform": "SNES / Super Famicom", "url": "https://www.snes9x.com/", "status": "official"},
    {"id": "project64", "name": "Project64", "platform": "Nintendo 64", "url": "https://www.pj64-emu.com/", "status": "official"},
    {"id": "sameboy", "name": "SameBoy", "platform": "Game Boy / Game Boy Color", "url": "https://sameboy.github.io/", "status": "official"},
    {"id": "melonds", "name": "melonDS", "platform": "Nintendo DS / DSi", "url": "https://melonds.kuribo64.net/", "status": "official"},
    {"id": "azahar", "name": "Azahar", "platform": "Nintendo 3DS", "url": "https://azahar-emu.org/", "status": "official"},
    {"id": "dolphin", "name": "Dolphin", "platform": "GameCube / Wii", "url": "https://dolphin-emu.org/", "status": "official"},
    {"id": "duckstation", "name": "DuckStation", "platform": "PlayStation (PS1)", "url": "https://www.duckstation.org/", "status": "official"},
    {"id": "pcsx2", "name": "PCSX2", "platform": "PlayStation 2", "url": "https://pcsx2.net/", "status": "official"},
    {"id": "ppsspp", "name": "PPSSPP", "platform": "PSP", "url": "https://www.ppsspp.org/", "status": "official"},
    {"id": "flycast", "name": "Flycast", "platform": "Dreamcast / Naomi / Atomiswave", "url": "https://github.com/flyinghead/flycast", "status": "official-project"},
    {"id": "kega", "name": "Kega Fusion", "platform": "Mega Drive / Genesis / Master System / Game Gear / Sega CD / 32X", "url": None, "status": "legacy"},
    {"id": "mame", "name": "MAME", "platform": "Arcade (y otros sistemas clásicos)", "url": "https://www.mamedev.org/", "status": "official"},
    {"id": "eden", "name": "Eden", "platform": "Nintendo Switch", "url": "https://eden-emu.dev/", "status": "official", "note": "Usa únicamente tus propios juegos, firmware y claves obtenidos legalmente."},
]


def emulator_sites() -> list[dict[str, Any]]:
    return [dict(item) for item in EMULATOR_SITES]


def open_emulator_site(site_id: str) -> dict[str, Any]:
    item = next((x for x in EMULATOR_SITES if x["id"] == str(site_id)), None)
    if item is None:
        raise KeyError("Emulador no reconocido.")
    url = item.get("url")
    if not url:
        raise ValueError("Kega Fusion es un proyecto legado y ORBIT no ha podido verificar una web oficial activa segura.")

    # On Windows, os.startfile delegates to the user's default browser and is
    # the most reliable way out of Edge kiosk/app mode. The URL is allow-listed.
    if os.name == "nt":
        os.startfile(str(url))  # type: ignore[attr-defined]
    else:
        # Development/test fallback.
        opened = webbrowser.open(str(url), new=2, autoraise=True)
        if not opened and os.environ.get("ORBIT_TESTING") != "1":
            try:
                subprocess.Popen(["xdg-open", str(url)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except OSError:
                pass
    return {"opened": True, "url": url, "name": item["name"]}
