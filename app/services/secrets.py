from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from app.core.paths import PortablePaths

_SENSITIVE_KEYS = {
    "api_key", "apikey", "api-token", "api_token", "token", "access_token",
    "secret", "client_secret", "password", "steamgriddb_token", "steamgriddb_api_key",
}


def scrub_sensitive(value: Any) -> Any:
    """Return a deep copy with credentials removed from serializable data.

    ORBIT packs, recovery points and metadata exports must never carry API keys,
    tokens or passwords. The helper is intentionally generic so future
    integrations do not accidentally leak credentials either.
    """
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, child in value.items():
            normalized = re.sub(r"\s+", "_", str(key).strip().casefold())
            if normalized in _SENSITIVE_KEYS or normalized.endswith("_token") or normalized.endswith("_secret") or normalized.endswith("_password") or normalized.endswith("_api_key"):
                continue
            out[str(key)] = scrub_sensitive(child)
        return out
    if isinstance(value, list):
        return [scrub_sensitive(x) for x in value]
    return value


class SecretStore:
    """Small non-JSON credential store excluded from ORBIT backups/exports."""

    def __init__(self, paths: PortablePaths) -> None:
        self.paths = paths
        self.root = self.paths.data / ".secrets"
        self.root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _safe_profile(profile_id: str) -> str:
        raw = str(profile_id or "default")
        clean = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw).strip("._")
        return clean[:80] or "default"

    def _steamgrid_path(self, profile_id: str) -> Path:
        return self.root / f"steamgriddb-{self._safe_profile(profile_id)}.token"

    def get_steamgriddb(self, profile_id: str) -> str:
        path = self._steamgrid_path(profile_id)
        try:
            return path.read_text(encoding="utf-8").strip()
        except OSError:
            return ""

    def set_steamgriddb(self, profile_id: str, token: str) -> None:
        value = str(token or "").strip()
        path = self._steamgrid_path(profile_id)
        if not value:
            path.unlink(missing_ok=True)
            return
        fd, tmp_name = tempfile.mkstemp(prefix=".steamgrid-", suffix=".tmp", dir=str(self.root))
        try:
            with open(fd, "w", encoding="utf-8", closefd=True) as handle:
                handle.write(value)
                handle.flush()
                os.fsync(handle.fileno())
            Path(tmp_name).replace(path)
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
        finally:
            Path(tmp_name).unlink(missing_ok=True)

    @staticmethod
    def scrub_json_file(path: Path) -> bool:
        """Remove credentials from an existing JSON file in-place.

        Used once during v0.6.2 migration to clean old settings/config backups
        that may have contained the SteamGridDB key.
        """
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        clean = scrub_sensitive(raw)
        if clean == raw:
            return False
        path.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
        return True
