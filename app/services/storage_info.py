from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.core.paths import PortablePaths


def _dir_size(path: Path) -> int:
    total = 0
    if not path.exists():
        return 0
    try:
        if path.is_file():
            return path.stat().st_size
        for root, _dirs, files in os.walk(path):
            for filename in files:
                try:
                    total += (Path(root) / filename).stat().st_size
                except OSError:
                    pass
    except OSError:
        pass
    return total


def storage_breakdown(paths: PortablePaths) -> dict[str, Any]:
    categories = {
        "games": paths.games,
        "emulators": paths.emulators,
        "media": paths.media,
        "saves": paths.saves,
        "backups": paths.backups,
        "data": paths.data,
    }
    usage = {name: _dir_size(path) for name, path in categories.items()}
    disk = os.statvfs(paths.root) if os.name != "nt" else None
    if disk:
        total = disk.f_frsize * disk.f_blocks
        free = disk.f_frsize * disk.f_bavail
    else:
        import shutil
        du = shutil.disk_usage(paths.root)
        total, free = du.total, du.free
    return {"categories": usage, "total": total, "free": free, "used": total - free}
