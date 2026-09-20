from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from app.core.paths import PortablePaths
from app.services.image_pipeline import MAX_IMAGE_BYTES, store_image_bytes

API_ROOT = "https://www.steamgriddb.com/api/v2"
ALLOWED_IMAGE_HOST_SUFFIX = ".steamgriddb.com"

class CoverSearchService:
    def __init__(self, paths: PortablePaths) -> None:
        self.paths = paths

    @staticmethod
    def _request_json(url: str, api_key: str) -> dict[str, Any]:
        req = Request(url, headers={"Authorization": f"Bearer {api_key}", "User-Agent": "ORBIT/0.6.2"})
        with urlopen(req, timeout=8) as response:
            if int(getattr(response, "status", 200)) != 200:
                raise ValueError("El proveedor de carátulas no respondió correctamente.")
            raw = response.read(2 * 1024 * 1024)
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict) or not data.get("success", False):
            raise ValueError("No se pudo consultar el proveedor de carátulas.")
        return data

    def search(self, query: str, api_key: str, kind: str = "grid") -> dict[str, Any]:
        query = str(query or "").strip()
        key = str(api_key or "").strip()
        if not query:
            raise ValueError("Escribe el nombre del juego.")
        if not key:
            return {"configured": False, "games": [], "assets": [], "message": "Añade tu clave de SteamGridDB en Ajustes para buscar imágenes desde ORBIT."}
        games_data = self._request_json(f"{API_ROOT}/search/autocomplete/{quote(query)}", key)
        games = games_data.get("data") or []
        compact_games = [{"id": x.get("id"), "name": x.get("name"), "release_date": x.get("release_date")} for x in games[:12] if isinstance(x, dict)]
        if not compact_games:
            return {"configured": True, "games": [], "assets": [], "message": "No se encontraron coincidencias."}
        game_id = compact_games[0]["id"]
        endpoint = {"grid":"grids", "hero":"heroes", "logo":"logos"}.get(kind, "grids")
        assets_data = self._request_json(f"{API_ROOT}/{endpoint}/game/{game_id}", key)
        assets = []
        for x in (assets_data.get("data") or [])[:40]:
            if not isinstance(x, dict):
                continue
            url = x.get("url")
            thumb = x.get("thumb") or url
            if not url:
                continue
            assets.append({
                "id": x.get("id"), "url": url, "thumb": thumb,
                "width": x.get("width"), "height": x.get("height"),
                "style": x.get("style"), "language": x.get("language"),
            })
        return {"configured": True, "games": compact_games, "assets": assets, "selected_game_id": game_id}

    def assets_for_game(self, provider_game_id: int, api_key: str, kind: str = "grid") -> dict[str, Any]:
        key = str(api_key or "").strip()
        if not key:
            raise ValueError("Falta la clave de SteamGridDB.")
        endpoint = {"grid":"grids", "hero":"heroes", "logo":"logos"}.get(kind, "grids")
        data = self._request_json(f"{API_ROOT}/{endpoint}/game/{int(provider_game_id)}", key)
        assets=[]
        for x in (data.get("data") or [])[:60]:
            if isinstance(x, dict) and x.get("url"):
                assets.append({"id":x.get("id"),"url":x.get("url"),"thumb":x.get("thumb") or x.get("url"),"width":x.get("width"),"height":x.get("height"),"style":x.get("style"),"language":x.get("language")})
        return {"configured": True, "assets": assets, "selected_game_id": int(provider_game_id)}

    def download(self, url: str, destination: Path) -> Path:
        parsed = urlparse(str(url))
        host = (parsed.hostname or "").casefold()
        if parsed.scheme != "https" or not (host == "steamgriddb.com" or host.endswith(ALLOWED_IMAGE_HOST_SUFFIX)):
            raise ValueError("La URL de imagen no pertenece al proveedor permitido.")
        req = Request(url, headers={"User-Agent": "ORBIT/0.6.2", "Accept": "image/avif,image/webp,image/png,image/jpeg,image/gif,*/*;q=0.8"})
        with urlopen(req, timeout=12) as response:
            raw = response.read(MAX_IMAGE_BYTES + 1)
        if not raw:
            raise ValueError("El proveedor devolvió una imagen vacía.")
        if len(raw) > MAX_IMAGE_BYTES:
            raise ValueError("La imagen es demasiado grande.")
        # The CDN MIME/URL are only hints. The image pipeline validates the
        # actual bytes and stores the file using the canonical extension. This
        # avoids the historical "Formato de imagen no válido" failure when a
        # browser preview worked but the CDN extension/MIME did not match.
        return store_image_bytes(raw, destination, max_bytes=MAX_IMAGE_BYTES)
