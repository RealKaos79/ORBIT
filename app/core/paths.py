from __future__ import annotations

import os
from pathlib import Path


class PortablePaths:
    """Resolve paths relative to the launcher root without relying on drive letters."""

    TOKEN = "@launcher/"

    def __init__(self, root: Path | None = None) -> None:
        env_root = os.getenv("PORTABLE_LAUNCHER_ROOT")
        if root is not None:
            self.root = Path(root).resolve()
        elif env_root:
            self.root = Path(env_root).resolve()
        else:
            self.root = Path(__file__).resolve().parents[2]

        self.data = self.root / "data"
        self.media = self.root / "media"
        self.covers = self.media / "covers"
        self.backgrounds = self.media / "backgrounds"
        self.logos = self.media / "logos"
        self.screenshots = self.media / "screenshots"
        self.games = self.root / "games"
        self.emulators = self.root / "emulators"
        self.saves = self.root / "saves"
        self.backups = self.root / "backups"
        self.logs = self.root / "logs"
        self.exports = self.root / "exports"
        self.system = self.root / "system"
        self.recovery = self.backups / "recovery"
        self.trash = self.root / ".orbit-trash"

    def ensure_layout(self) -> None:
        for path in (
            self.data,
            self.media,
            self.covers,
            self.backgrounds,
            self.logos,
            self.screenshots,
            self.games,
            self.emulators,
            self.saves,
            self.backups,
            self.logs,
            self.exports,
            self.system,
            self.recovery,
            self.trash,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def _assert_inside_root(self, path: Path) -> Path:
        resolved = path.resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise ValueError("Ruta portable inválida: intenta salir de la carpeta del launcher.") from exc
        return resolved

    def encode(self, value: str | Path | None) -> str | None:
        """Store paths inside the launcher as @launcher/...; external paths stay absolute."""
        if value is None or str(value).strip() == "":
            return None

        text = str(value).strip()
        if text.startswith(self.TOKEN):
            decoded = self.decode(text)
            if decoded is None:
                return None
            relative = decoded.relative_to(self.root)
            return self.TOKEN + relative.as_posix()

        path = Path(text).expanduser()
        if not path.is_absolute():
            path = self.root / path
        try:
            resolved = path.resolve()
        except OSError:
            resolved = path.absolute()
        try:
            relative = resolved.relative_to(self.root)
            return self.TOKEN + relative.as_posix()
        except ValueError:
            return str(resolved)

    def decode(self, value: str | Path | None) -> Path | None:
        if value is None or str(value).strip() == "":
            return None
        text = str(value).strip()
        if text.startswith(self.TOKEN):
            relative = text[len(self.TOKEN):].replace("/", os.sep)
            return self._assert_inside_root(self.root / relative)
        path = Path(text).expanduser()
        if not path.is_absolute():
            path = self.root / path
        return path.resolve()

    def display(self, value: str | Path | None) -> str:
        if value is None:
            return ""
        text = str(value)
        if text.startswith(self.TOKEN):
            return text
        encoded = self.encode(value)
        return encoded or ""
