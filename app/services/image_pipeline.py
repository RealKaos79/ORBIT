from __future__ import annotations

import io
import os
import shutil
import subprocess
import struct
import uuid
from dataclasses import dataclass
from pathlib import Path


MAX_IMAGE_BYTES = 25 * 1024 * 1024


@dataclass(frozen=True)
class ImageFormat:
    name: str
    extension: str
    mime: str
    browser_safe: bool = True


PNG = ImageFormat("PNG", ".png", "image/png")
JPEG = ImageFormat("JPEG", ".jpg", "image/jpeg")
WEBP = ImageFormat("WEBP", ".webp", "image/webp")
GIF = ImageFormat("GIF", ".gif", "image/gif")
AVIF = ImageFormat("AVIF", ".avif", "image/avif")
BMP = ImageFormat("BMP", ".bmp", "image/bmp")
ICO = ImageFormat("ICO", ".ico", "image/x-icon")
TIFF = ImageFormat("TIFF", ".tiff", "image/tiff", browser_safe=False)

DIRECT_FORMATS = {x.name: x for x in (PNG, JPEG, WEBP, GIF, AVIF, BMP, ICO)}
SUPPORTED_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".jpe", ".jfif", ".webp", ".gif", ".avif", ".bmp", ".ico",
    # TIFF is accepted when a local decoder (Pillow) is available and is then
    # converted to PNG. It is intentionally not served directly to the browser.
    ".tif", ".tiff",
}


def _read_prefix(raw: bytes, size: int = 4096) -> bytes:
    return raw[:size]


def _avif_brand(prefix: bytes) -> bool:
    """Recognise AVIF ISO-BMFF brands without relying on filename/MIME."""
    if len(prefix) < 16 or prefix[4:8] != b"ftyp":
        return False
    try:
        box_size = int.from_bytes(prefix[:4], "big")
    except Exception:
        return False
    if box_size == 1 and len(prefix) >= 24:
        box_size = int.from_bytes(prefix[8:16], "big")
        brands = prefix[16:min(len(prefix), max(32, box_size))]
    else:
        brands = prefix[8:min(len(prefix), max(32, box_size or 32))]
    return b"avif" in brands or b"avis" in brands


def detect_image_format(raw: bytes) -> ImageFormat | None:
    """Detect image format from bytes, never from extension or HTTP headers."""
    prefix = _read_prefix(raw)
    if prefix.startswith(b"\x89PNG\r\n\x1a\n"):
        return PNG
    if prefix.startswith(b"\xff\xd8\xff"):
        return JPEG
    if len(prefix) >= 12 and prefix[:4] == b"RIFF" and prefix[8:12] == b"WEBP":
        return WEBP
    if prefix.startswith((b"GIF87a", b"GIF89a")):
        return GIF
    if _avif_brand(prefix):
        return AVIF
    if prefix.startswith(b"BM") and len(prefix) >= 18:
        return BMP
    if prefix.startswith(b"\x00\x00\x01\x00") and len(prefix) >= 6:
        return ICO
    if prefix.startswith((b"II*\x00", b"MM\x00*")):
        return TIFF
    return None


def _basic_structure_ok(raw: bytes, fmt: ImageFormat) -> bool:
    """Cheap structural checks to reject obvious non-images/truncated payloads.

    Full decoding is intentionally optional because ORBIT's portable embedded
    Python has no third-party dependencies. The browser performs final decoding
    when displaying the image; these checks make sure we do not trust a suffix.
    """
    try:
        if fmt is PNG:
            return len(raw) >= 24 and raw[12:16] == b"IHDR" and int.from_bytes(raw[16:20], "big") > 0 and int.from_bytes(raw[20:24], "big") > 0
        if fmt is GIF:
            return len(raw) >= 10 and int.from_bytes(raw[6:8], "little") > 0 and int.from_bytes(raw[8:10], "little") > 0
        if fmt is BMP:
            if len(raw) < 26:
                return False
            dib = int.from_bytes(raw[14:18], "little")
            if dib == 12 and len(raw) >= 26:
                return int.from_bytes(raw[18:20], "little") > 0 and int.from_bytes(raw[20:22], "little") > 0
            if dib >= 40 and len(raw) >= 26:
                width = int.from_bytes(raw[18:22], "little", signed=True)
                height = int.from_bytes(raw[22:26], "little", signed=True)
                return width != 0 and height != 0
            return False
        if fmt is ICO:
            return len(raw) >= 6 and int.from_bytes(raw[4:6], "little") > 0
        if fmt is WEBP:
            return len(raw) >= 16 and raw[12:16] in {b"VP8 ", b"VP8L", b"VP8X"}
        if fmt is AVIF:
            return len(raw) >= 16 and _avif_brand(raw[:4096])
        if fmt is TIFF:
            return len(raw) >= 8
        if fmt is JPEG:
            # JPEG streams end with EOI. Some web servers append harmless bytes,
            # so search the tail rather than requiring it as the final 2 bytes.
            return len(raw) >= 4 and b"\xff\xd9" in raw[-64:]
    except (ValueError, OverflowError, struct.error):
        return False
    return False


def read_image_bytes(path: Path, max_bytes: int = MAX_IMAGE_BYTES) -> bytes:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise ValueError(f"No se pudo leer la imagen: {exc}") from exc
    if size <= 0:
        raise ValueError("La imagen está vacía.")
    if size > max_bytes:
        raise ValueError(f"La imagen es demasiado grande. El máximo es {max_bytes // (1024 * 1024)} MB.")
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ValueError(f"No se pudo leer la imagen: {exc}") from exc
    return raw


def validate_image_bytes(raw: bytes, *, max_bytes: int = MAX_IMAGE_BYTES) -> ImageFormat:
    if not raw:
        raise ValueError("La imagen está vacía.")
    if len(raw) > max_bytes:
        raise ValueError(f"La imagen es demasiado grande. El máximo es {max_bytes // (1024 * 1024)} MB.")
    fmt = detect_image_format(raw)
    if fmt is None:
        raise ValueError("Formato de imagen no reconocido por su contenido.")
    if not _basic_structure_ok(raw, fmt):
        raise ValueError(f"La imagen {fmt.name} está dañada o incompleta.")
    return fmt



def _find_windows_powershell() -> str | None:
    if os.name != "nt":
        return None
    candidates = [shutil.which("powershell.exe"), shutil.which("pwsh.exe")]
    system_root = os.environ.get("SystemRoot") or os.environ.get("WINDIR")
    if system_root:
        candidates.extend([
            str(Path(system_root) / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"),
            str(Path(system_root) / "Sysnative" / "WindowsPowerShell" / "v1.0" / "powershell.exe"),
        ])
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    return None


def _try_windows_native_to_png(raw: bytes, fmt: ImageFormat, target: Path) -> bool:
    """Use Windows' built-in System.Drawing decoder as a no-install fallback."""
    powershell = _find_windows_powershell()
    if not powershell:
        return False
    source_path = target.with_name(f".{target.stem}.{uuid.uuid4().hex}{fmt.extension}")
    try:
        source_path.write_bytes(raw)
        source_literal = str(source_path).replace("'", "''")
        target_literal = str(target).replace("'", "''")
        script = (
            "Add-Type -AssemblyName System.Drawing; "
            f"$img=[System.Drawing.Image]::FromFile('{source_literal}'); "
            "try { "
            f"$img.Save('{target_literal}', [System.Drawing.Imaging.ImageFormat]::Png) "
            "} finally { $img.Dispose() }"
        )
        result = subprocess.run(
            [powershell, "-NoProfile", "-STA", "-Command", script],
            capture_output=True, text=True, timeout=30, check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return result.returncode == 0 and target.is_file() and target.stat().st_size > 0
    except Exception:
        return False
    finally:
        source_path.unlink(missing_ok=True)

def _try_pillow_to_png(raw: bytes, target: Path) -> bool:
    """Optional decoder/converter. ORBIT does not require Pillow at runtime."""
    try:
        from PIL import Image  # type: ignore
    except Exception:
        return False
    try:
        with Image.open(io.BytesIO(raw)) as image:
            image.load()
            # Keep alpha where applicable; RGB/RGBA are the most predictable for PNG.
            if image.mode not in {"RGB", "RGBA", "L", "LA", "P"}:
                image = image.convert("RGBA")
            image.save(target, format="PNG", optimize=True)
        return True
    except Exception:
        return False


def store_image_bytes(raw: bytes, destination_stem: Path, *, max_bytes: int = MAX_IMAGE_BYTES) -> Path:
    """Validate and store image content using a canonical extension.

    Direct browser-safe formats are preserved. Formats such as TIFF are
    converted to PNG when a decoder is available; unsupported content is never
    saved under a fake extension.
    """
    fmt = validate_image_bytes(raw, max_bytes=max_bytes)
    destination_stem.parent.mkdir(parents=True, exist_ok=True)
    if fmt.browser_safe:
        target = destination_stem.with_suffix(fmt.extension)
        temp = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
        try:
            with temp.open("wb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, target)
            return target
        finally:
            temp.unlink(missing_ok=True)

    target = destination_stem.with_suffix(".png")
    temp = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    try:
        if not _try_pillow_to_png(raw, temp) and not _try_windows_native_to_png(raw, fmt, temp):
            raise ValueError(
                f"La imagen es {fmt.name}. ORBIT la reconoce, pero este equipo no dispone de un decodificador para convertirla a PNG."
            )
        # Validate the converted output as well before replacing the destination.
        validate_image_bytes(temp.read_bytes(), max_bytes=max_bytes)
        os.replace(temp, target)
        return target
    finally:
        temp.unlink(missing_ok=True)


def store_image_file(source: Path, destination_stem: Path, *, max_bytes: int = MAX_IMAGE_BYTES) -> Path:
    raw = read_image_bytes(source, max_bytes=max_bytes)
    fmt = validate_image_bytes(raw, max_bytes=max_bytes)

    # If the source is already the canonical managed target, leave it untouched.
    canonical = destination_stem.with_suffix(fmt.extension if fmt.browser_safe else ".png")
    try:
        if fmt.browser_safe and source.resolve() == canonical.resolve():
            return source.resolve()
    except OSError:
        pass
    return store_image_bytes(raw, destination_stem, max_bytes=max_bytes)
