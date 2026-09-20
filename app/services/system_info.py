from __future__ import annotations

import ctypes
import json
import os
import platform
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.paths import PortablePaths


@lru_cache(maxsize=1)
def _memory_bytes() -> int | None:
    if os.name == "nt":
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]
        status = MEMORYSTATUSEX()
        status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return int(status.ullTotalPhys)
        return None
    meminfo = Path("/proc/meminfo")
    if meminfo.exists():
        for line in meminfo.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.startswith("MemTotal:"):
                return int(line.split()[1]) * 1024
    return None


@lru_cache(maxsize=1)
def _gpu_name() -> str:
    try:
        if os.name == "nt":
            cmd = [
                "powershell.exe",
                "-NoProfile",
                "-Command",
                "Get-CimInstance Win32_VideoController | Select-Object -ExpandProperty Name | ConvertTo-Json -Compress",
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=4, check=False)
            raw = result.stdout.strip()
            if raw:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return " / ".join(str(x) for x in parsed)
                return str(parsed)
        else:
            result = subprocess.run(
                ["sh", "-lc", "lspci 2>/dev/null | grep -Ei 'vga|3d|display' | head -1"],
                capture_output=True,
                text=True,
                timeout=3,
                check=False,
            )
            if result.stdout.strip():
                return result.stdout.strip()
    except Exception:
        pass
    return "No detectada"


def collect_system_info(paths: PortablePaths, *, include_gpu: bool = True) -> dict[str, Any]:
    try:
        total, used, free = shutil.disk_usage(paths.root)
        storage = {"total": total, "used": used, "free": free}
    except OSError:
        storage = {"total": 0, "used": 0, "free": 0}

    return {
        "os": f"{platform.system()} {platform.release()}",
        "os_version": platform.version(),
        "architecture": platform.machine(),
        "cpu": platform.processor() or platform.machine(),
        "cpu_cores": os.cpu_count(),
        "gpu": _gpu_name() if include_gpu else "Se cargará en Diagnóstico",
        "ram_bytes": _memory_bytes(),
        "launcher_root": str(paths.root),
        "storage": storage,
        "python": platform.python_version(),
    }
