from __future__ import annotations

from typing import Any


PLATFORM_DEMAND = {
    "NES": 1, "SNES": 1, "Game Boy": 1, "Game Boy Color": 1, "Game Boy Advance": 1,
    "Mega Drive": 1, "PlayStation": 2, "Nintendo 64": 2, "Nintendo DS": 2, "Arcade": 2,
    "Dreamcast": 3, "PSP": 3, "GameCube": 3, "Wii": 3,
    "PlayStation 2": 4, "Nintendo 3DS": 4,
    "Nintendo Switch": 5, "PC": 4,
}

LABELS = {
    4: ("excellent", "Excelente", "🟢"),
    3: ("good", "Muy bueno", "🟢"),
    2: ("acceptable", "Aceptable", "🟡"),
    1: ("issues", "Puede tener problemas", "🟠"),
    0: ("not-recommended", "No recomendado", "🔴"),
}


def _ram_gb(system: dict[str, Any]) -> float | None:
    raw = system.get("ram_bytes")
    if not raw:
        return None
    try:
        return float(raw) / (1024 ** 3)
    except (TypeError, ValueError):
        return None


def estimate_game_performance(game: dict[str, Any], system: dict[str, Any]) -> dict[str, Any]:
    platform = str(game.get("platform") or "PC")
    explicit = game.get("performance_demand")
    try:
        demand = max(1, min(5, int(explicit))) if explicit not in (None, "") else PLATFORM_DEMAND.get(platform, 3)
    except (TypeError, ValueError):
        demand = PLATFORM_DEMAND.get(platform, 3)

    cores = int(system.get("cpu_cores") or 0)
    ram = _ram_gb(system)
    gpu = str(system.get("gpu") or "").strip()
    gpu_known = bool(gpu and gpu.casefold() not in {"no detectada", "se cargará en diagnóstico"})

    if not cores or ram is None:
        return {
            "code": "unknown", "label": "Sin datos suficientes", "icon": "⚪", "score": None,
            "platform": platform, "demand": demand,
            "reasons": ["ORBIT necesita detectar CPU y RAM para hacer una estimación."],
            "recommendations": ["Abre Diagnóstico para completar la detección del equipo."],
            "disclaimer": "Estimación cualitativa; ORBIT no inventa FPS.",
        }

    capacity = 1
    if cores >= 4: capacity += 1
    if cores >= 8: capacity += 1
    if ram >= 8: capacity += 1
    if ram >= 16: capacity += 1
    if gpu_known: capacity += 1
    # Convert capacity/demand delta into a stable 0..4 quality score.
    delta = capacity - demand
    score = 4 if delta >= 2 else 3 if delta == 1 else 2 if delta == 0 else 1 if delta == -1 else 0
    code, label, icon = LABELS[score]
    reasons = [f"Demanda estimada de {platform}: nivel {demand}/5.", f"CPU detectada: {cores} núcleos.", f"RAM detectada: {ram:.1f} GB."]
    if gpu_known:
        reasons.append("GPU detectada; la estimación puede considerar aceleración gráfica disponible.")
    else:
        reasons.append("GPU no identificada; la estimación es más conservadora.")
    recommendations: list[str] = []
    if score <= 1:
        recommendations += ["Empieza con resolución nativa o 720p y evita escalados altos.", "Usa el emulador recomendado para esta plataforma y revisa su backend gráfico."]
    elif score == 2:
        recommendations += ["Empieza con ajustes equilibrados y sube resolución después de comprobar estabilidad."]
    else:
        recommendations += ["Puedes empezar con los ajustes recomendados del emulador y subir calidad gradualmente."]
    return {
        "code": code, "label": label, "icon": icon, "score": score,
        "platform": platform, "demand": demand, "reasons": reasons,
        "recommendations": recommendations,
        "disclaimer": "Estimación cualitativa; el rendimiento real depende del juego y del emulador. ORBIT no inventa FPS.",
    }
