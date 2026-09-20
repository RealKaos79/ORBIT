from __future__ import annotations

import base64
import json
import subprocess
import tempfile
import unittest
import zipfile
from urllib.request import Request, urlopen
from pathlib import Path
from unittest.mock import Mock, patch

from app.core.paths import PortablePaths
from app.core.storage import JsonStore
from app.services.ai_runtime import LocalModelRuntime
from app.services.library import LibraryService
from app.server import LauncherServer
from app.services.orbitpack import OrbitPackService
from app.services.secrets import scrub_sensitive


def _fixture_b64(value: str) -> bytes:
    return base64.b64decode(value)


def fake_png() -> bytes:
    return _fixture_b64("iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAAFElEQVR4nGMU0bD5z8DAwMDEAAUAFYABe3P1OxMAAAAASUVORK5CYII=")


def fake_jpeg() -> bytes:
    return _fixture_b64("/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjIyMjL/wAARCAACAAIDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwDyOiiiuw5D/9k=")


def fake_webp() -> bytes:
    return _fixture_b64("UklGRjAAAABXRUJQVlA4ICQAAABQAQCdASoCAAIAAUAmJQBOgCgAAP76id+R2EN2HLri5shvAAA=")


def fake_gif() -> bytes:
    return _fixture_b64("R0lGODdhAgACAIAAAAAAAAAAACwAAAAAAgACAAAIBgABCAQQEAA7")


def fake_bmp() -> bytes:
    return _fixture_b64("Qk1GAAAAAAAAADYAAAAoAAAAAgAAAAIAAAABABgAAAAAABAAAADEDgAAxA4AAAAAAAAAAAAAPCgUPCgUAAA8KBQ8KBQAAA==")


def fake_avif() -> bytes:
    return _fixture_b64("AAAAIGZ0eXBhdmlmAAAAAGF2aWZtaWYxbWlhZk1BMUIAAADrbWV0YQAAAAAAAAAhaGRscgAAAAAAAAAAcGljdAAAAAAAAAAAAAAAAAAAAAAOcGl0bQAAAAAAAQAAAB5pbG9jAAAAAEQAAAEAAQAAAAEAAAETAAAAJwAAAChpaW5mAAAAAAABAAAAGmluZmUCAAAAAAEAAGF2MDFDb2xvcgAAAABqaXBycAAAAEtpcGNvAAAAFGlzcGUAAAAAAAAAAgAAAAIAAAAQcGl4aQAAAAADCAgIAAAADGF2MUOBAAwAAAAAE2NvbHJuY2x4AAEADQAGgAAAABdpcG1hAAAAAAAAAAEAAQQBAoMEAAAAL21kYXQSAAoIGAA2iAhoNCAyGRTHh4ZlAgggnlAAAABIWtlc1jDhXA3mpxQ=")


def fake_ico() -> bytes:
    return _fixture_b64("AAABAAEAICAAAAAAIABuAAAAFgAAAIlQTkcNChoKAAAADUlIRFIAAAAgAAAAIAgGAAAAc3p69AAAADVJREFUeJztzkEBADAIxLBjGiZiIvBva8jgkxpo6r7+WexszgEAAAAAAAAAAAAAAAAAAJJkAK9jAbeBBpVgAAAAAElFTkSuQmCC")


def fake_tiff() -> bytes:
    return _fixture_b64("SUkqAAgAAAALAAABBAABAAAAAgAAAAEBBAABAAAAAgAAAAIBAwAEAAAAkgAAAAMBAwABAAAAAQAAAAYBAwABAAAAAgAAABEBBAABAAAAmgAAABUBAwABAAAABAAAABYBBAABAAAAAgAAABcBBAABAAAAEAAAABwBAwABAAAAAQAAAFIBAwABAAAAAgAAAAAAAAAIAAgACAAIABQoPP8UKDz/FCg8/xQoPP8=")


class Orbit062Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="orbit-v062-test-")
        self.root = Path(self.tmp.name).resolve()
        (self.root / "VERSION").write_text("0.6.2\n", encoding="utf-8")
        self.paths = PortablePaths(self.root)
        self.store = JsonStore(self.paths)
        self.lib = LibraryService(self.paths, self.store)

    def tearDown(self):
        self.tmp.cleanup()

    def real_games(self, lib=None):
        lib = lib or self.lib
        return [g for g in lib.games() if not g.get("demo")]

    def add_game(self, name="Juego", platform="PC", lib=None, paths=None):
        lib = lib or self.lib
        paths = paths or self.paths
        suffix = ".exe" if platform == "PC" else ".iso"
        file = paths.games / platform / f"{name}{suffix}"
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(b"MZ-GAME" if suffix == ".exe" else b"ROM-DATA")
        payload = {"name": name, "platform": platform, "path": str(file)}
        if platform == "PC":
            payload["executable"] = str(file)
        return lib.add_game(payload)

    def make_receiver(self):
        td = tempfile.TemporaryDirectory(prefix="orbit-v062-receiver-")
        root = Path(td.name).resolve()
        (root / "VERSION").write_text("0.6.2\n", encoding="utf-8")
        paths = PortablePaths(root)
        lib = LibraryService(paths, JsonStore(paths))
        return td, paths, lib


class TestSecrets062(Orbit062Case):
    def test_steamgrid_token_is_outside_settings_json(self):
        self.lib.save_settings({"cover_search": {"api_key": "TOP-SECRET-STEAMGRID", "provider": "steamgriddb"}})
        raw = (self.paths.data / "settings.json").read_text(encoding="utf-8")
        self.assertNotIn("TOP-SECRET-STEAMGRID", raw)
        self.assertTrue(self.lib.settings()["cover_search"]["api_key_configured"])
        self.assertEqual(self.lib.secrets.get_steamgriddb("default"), "TOP-SECRET-STEAMGRID")

    def test_steamgrid_token_never_enters_orbitpack(self):
        self.lib.save_settings({"cover_search": {"api_key": "NEVER-IN-PACK"}})
        result = self.lib.create_orbitpack(
            include_games=False, include_emulators=False, include_media=False,
            include_saves=False, include_configuration=True, include_other=False,
            name="config-only",
        )
        pack = self.paths.decode(result["path"])
        self.assertNotIn(b"NEVER-IN-PACK", pack.read_bytes())
        with zipfile.ZipFile(pack) as z:
            manifest = json.loads(z.read("manifest.json"))
        self.assertNotIn("api_key", json.dumps(manifest))

    def test_steamgrid_token_never_enters_recovery(self):
        self.lib.save_settings({"cover_search": {"api_key": "NEVER-IN-RECOVERY"}})
        point = self.lib.create_recovery_point("secret-check")
        archive = self.paths.decode(point["path"])
        self.assertNotIn(b"NEVER-IN-RECOVERY", archive.read_bytes())
        with zipfile.ZipFile(archive) as z:
            self.assertFalse(any(".secrets" in name for name in z.namelist()))

    def test_generic_secret_scrubber_is_recursive(self):
        raw = {"ok": 1, "nested": {"token": "a", "client_secret": "b", "keep": "c"}, "items": [{"api_key": "d", "x": 2}]}
        clean = scrub_sensitive(raw)
        self.assertEqual(clean, {"ok": 1, "nested": {"keep": "c"}, "items": [{"x": 2}]})


class TestOrbitPack062(Orbit062Case):
    def test_configuration_only_pack_contains_no_games_or_emulators(self):
        self.add_game("ShouldNotTravel")
        emu_file = self.paths.emulators / "Fake" / "fake.exe"; emu_file.parent.mkdir(parents=True); emu_file.write_bytes(b"MZ")
        self.lib.add_emulator({"name": "Fake", "platform": "NES", "executable": str(emu_file)})
        result = self.lib.create_orbitpack(
            include_games=False, include_emulators=False, include_media=False,
            include_saves=False, include_configuration=True, include_other=False,
        )
        info = self.lib.inspect_orbitpack(str(self.paths.decode(result["path"])))
        self.assertEqual(info["games"], 0)
        self.assertEqual(info["emulators"], 0)
        self.assertTrue(info["components"]["configuration"])
        self.assertFalse(info["components"]["games"])

    def test_configuration_only_pack_has_no_payload_members(self):
        self.add_game("NotInConfig")
        result = self.lib.create_orbitpack(
            game_ids=[], include_games=False, include_game_files=False, include_emulators=False,
            include_media=False, include_saves=False, include_configuration=True, include_other=False,
            name="strict-config-only",
        )
        pack = self.paths.decode(result["path"])
        with zipfile.ZipFile(pack) as archive:
            payload_members = [name for name in archive.namelist() if name.startswith("payload/")]
        self.assertEqual(payload_members, [])

    def test_full_profile_marks_every_component(self):
        self.add_game("Full")
        result = self.lib.create_orbitpack(full_profile=True, name="full-profile")
        self.assertEqual(result["scope"], "profile")
        self.assertTrue(all(result["components"].values()))

    def test_partial_import_configuration_only_does_not_import_game(self):
        self.add_game("SourceGame")
        self.lib.save_settings({"theme": "light"})
        result = self.lib.create_orbitpack(
            include_game_files=True, include_games=True, include_emulators=False,
            include_media=False, include_saves=False, include_configuration=True,
        )
        td, paths2, lib2 = self.make_receiver()
        try:
            before = len(self.real_games(lib2))
            imported = lib2.import_orbitpack(str(self.paths.decode(result["path"])), components=["configuration"], config_conflict="import-preferred")
            self.assertEqual(len(self.real_games(lib2)), before)
            self.assertEqual(lib2.settings()["theme"], "light")
            self.assertEqual(imported["components"], ["configuration"])
        finally:
            td.cleanup()

    def test_import_merge_preserves_existing_and_adds_new_game(self):
        self.add_game("Imported")
        result = self.lib.create_orbitpack(include_game_files=True, include_emulators=False, include_media=False)
        td, paths2, lib2 = self.make_receiver()
        try:
            self.add_game("Existing", lib=lib2, paths=paths2)
            lib2.import_orbitpack(str(self.paths.decode(result["path"])), components=["games"])
            names = {g["name"] for g in self.real_games(lib2)}
            self.assertEqual(names, {"Existing", "Imported"})
        finally:
            td.cleanup()

    def test_new_profile_import_does_not_destroy_default_profile(self):
        profile = self.lib.add_profile("Cristina", "star")
        self.lib.select_profile(profile["id"])
        self.add_game("ProfileGame")
        result = self.lib.create_orbitpack(full_profile=True, name="profile")
        td, paths2, lib2 = self.make_receiver()
        try:
            original = self.add_game("DefaultGame", lib=lib2, paths=paths2)
            out = lib2.import_orbitpack(str(self.paths.decode(result["path"])), profile_strategy="new-profile")
            self.assertTrue(out["profile_created"])
            self.assertTrue(any(g["name"] == "ProfileGame" for g in self.real_games(lib2)))
            lib2.select_profile("default")
            self.assertTrue(any(g["id"] == original["id"] for g in self.real_games(lib2)))
            self.assertFalse(any(g["name"] == "ProfileGame" for g in self.real_games(lib2)))
        finally:
            td.cleanup()

    def test_import_uses_receiver_automatic_folder(self):
        self.add_game("Portable", platform="GameCube")
        result = self.lib.create_orbitpack(include_game_files=True, include_emulators=False, include_media=False)
        td, paths2, lib2 = self.make_receiver()
        try:
            custom = paths2.games / "Receptor" / "GC"
            lib2.set_platform_destination("GameCube", str(custom))
            lib2.import_orbitpack(str(self.paths.decode(result["path"])), components=["games"])
            imported = next(g for g in self.real_games(lib2) if g["name"] == "Portable")
            self.assertEqual(paths2.decode(imported["path"]).parent, custom.resolve())
            self.assertNotIn(str(self.root), imported["path"])
        finally:
            td.cleanup()

    def test_import_always_creates_recovery_point(self):
        self.add_game("Recoverable")
        result = self.lib.create_orbitpack(include_game_files=True, include_emulators=False, include_media=False)
        td, paths2, lib2 = self.make_receiver()
        try:
            out = lib2.import_orbitpack(str(self.paths.decode(result["path"])), components=["games"])
            rollback = paths2.decode(out["rollback"]["path"])
            self.assertTrue(rollback.is_file())
        finally:
            td.cleanup()

    def test_unsigned_payload_member_is_rejected(self):
        result = self.lib.create_orbitpack(include_games=False, include_emulators=False, include_media=False, include_saves=False, include_configuration=True)
        original = self.paths.decode(result["path"])
        tampered = self.paths.exports / "unsigned.orbitpack"
        with zipfile.ZipFile(original) as src, zipfile.ZipFile(tampered, "w") as dst:
            for item in src.infolist():
                dst.writestr(item, src.read(item.filename))
            dst.writestr("payload/evil.bin", b"unsigned")
        with self.assertRaises(ValueError):
            self.lib.inspect_orbitpack(str(tampered))

    def test_duplicate_archive_members_are_rejected_at_creation(self):
        f1 = self.root / "a.bin"; f2 = self.root / "b.bin"; f1.write_bytes(b"a"); f2.write_bytes(b"b")
        service = OrbitPackService(self.paths)
        with self.assertRaises(ValueError):
            service.create({"games": []}, [(f1, "payload/x.bin"), (f2, "payload/x.bin")], "dupe")

    def test_export_reports_real_progress_and_custom_destination(self):
        game = self.add_game("ProgressGame")
        source = self.paths.decode(game["path"])
        source.write_bytes((b"ORBIT-PROGRESS-" * 131072)[:1500000])
        destination = self.root / "chosen-by-user.orbitpack"
        events = []
        result = self.lib.create_orbitpack(
            include_game_files=True, include_emulators=False, include_media=False,
            destination=destination, progress=events.append, name="progress",
        )
        self.assertTrue(destination.is_file())
        self.assertEqual(self.paths.decode(result["path"]).resolve(), destination.resolve())
        self.assertTrue(any(0 < float(e.get("percent") or 0) < 1 for e in events))
        self.assertEqual(float(events[-1].get("percent") or 0), 1.0)
        self.assertIn("eta_seconds", events[-1])
        info = self.lib.orbitpacks.inspect(destination, verify_files=True)
        self.assertEqual(info["manifest"]["format"], "ORBITPACK")


    def test_export_import_preserves_cover_media(self):
        game = self.add_game("CoverTravel")
        cover = self.root / "travel.webp"
        cover.write_bytes(fake_webp())
        self.lib.set_game_media(game["id"], "cover", str(cover))
        result = self.lib.create_orbitpack(
            include_game_files=True, include_emulators=False, include_media=True, name="cover-travel"
        )
        td, paths2, lib2 = self.make_receiver()
        try:
            out = lib2.import_orbitpack(str(self.paths.decode(result["path"])), components=["games", "media"])
            imported = next(g for g in self.real_games(lib2) if g["name"] == "CoverTravel")
            imported_cover = paths2.decode(imported.get("cover"))
            self.assertTrue(imported_cover and imported_cover.is_file())
            self.assertEqual(imported_cover.suffix.lower(), ".webp")
            self.assertGreaterEqual(out.get("media", 0), 1)
        finally:
            td.cleanup()


    def test_selective_game_export_contains_only_requested_games_and_files(self):
        games = [self.add_game(name) for name in ("Mario Kart 7", "Pokemon Y", "Super Mario Odyssey", "Zelda")]
        selected = [games[0], games[2]]
        for game in games:
            cover = self.root / f"{game['id']}.png"; cover.write_bytes(fake_png())
            self.lib.set_game_cover(game["id"], str(cover))
        result = self.lib.create_orbitpack(
            game_ids=[g["id"] for g in selected], include_games=True, include_game_files=True,
            include_emulators=False, include_media=True, include_saves=False, include_configuration=False,
            name="selected-games",
        )
        pack = self.paths.decode(result["path"])
        with zipfile.ZipFile(pack) as z:
            manifest = json.loads(z.read("manifest.json"))
            names = {g.get("name") for g in manifest.get("games") or []}
            members = set(z.namelist())
        self.assertEqual(names, {"Mario Kart 7", "Super Mario Odyssey"})
        for game in selected:
            self.assertTrue(any(game["id"] in member for member in members))
        for game in (games[1], games[3]):
            self.assertFalse(any(game["id"] in member for member in members))

        td, _paths2, lib2 = self.make_receiver()
        try:
            lib2.import_orbitpack(str(pack), components=["games", "media"])
            self.assertEqual({g["name"] for g in self.real_games(lib2)}, {"Mario Kart 7", "Super Mario Odyssey"})
        finally:
            td.cleanup()

    def test_selective_media_only_exports_only_requested_game_cover(self):
        first = self.add_game("Media One")
        second = self.add_game("Media Two")
        for game, raw in ((first, fake_png()), (second, fake_jpeg())):
            source = self.root / f"{game['id']}.img"
            source.write_bytes(raw)
            self.lib.set_game_cover(game["id"], str(source))
        result = self.lib.create_orbitpack(
            game_ids=[first["id"]], include_games=False, include_game_files=False,
            include_emulators=False, include_media=True, include_saves=False,
            include_configuration=False, include_other=False, name="one-cover",
        )
        pack = self.paths.decode(result["path"])
        with zipfile.ZipFile(pack) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            members = set(archive.namelist())
        self.assertFalse(manifest["components"]["games"])
        self.assertTrue(manifest["components"]["media"])
        self.assertEqual([g["source_id"] for g in manifest["games"]], [first["id"]])
        self.assertTrue(any(name.startswith("payload/media/covers/") and first["id"] in name for name in members))
        self.assertFalse(any(second["id"] in name for name in members))
        self.assertFalse(any(name.startswith("payload/games/") for name in members))

    def test_selective_saves_only_excludes_unselected_game_save(self):
        first = self.add_game("Save One")
        second = self.add_game("Save Two")
        for game in (first, second):
            save_dir = self.lib.saves.portable_target(game, self.lib._active_profile_id())
            save_dir.mkdir(parents=True, exist_ok=True)
            (save_dir / "slot1.sav").write_bytes(game["name"].encode("utf-8"))
        result = self.lib.create_orbitpack(
            game_ids=[second["id"]], include_games=False, include_game_files=False,
            include_emulators=False, include_media=False, include_saves=True,
            include_configuration=False, include_other=False, name="one-save",
        )
        pack = self.paths.decode(result["path"])
        with zipfile.ZipFile(pack) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            members = set(archive.namelist())
        self.assertEqual([g["source_id"] for g in manifest["games"]], [second["id"]])
        self.assertTrue(any(name.startswith("payload/saves/") and second["id"] in name for name in members))
        self.assertFalse(any(first["id"] in name for name in members))

    def test_explicit_empty_game_selection_exports_no_game_metadata(self):
        self.add_game("NotSelected")
        result = self.lib.create_orbitpack(
            game_ids=[], include_games=False, include_emulators=False, include_media=False,
            include_saves=False, include_configuration=True, include_other=False,
        )
        info = self.lib.orbitpacks.inspect(self.paths.decode(result["path"]), verify_files=True)
        self.assertEqual(info["manifest"].get("games"), [])
        self.assertFalse(info["manifest"]["components"]["games"])

    def test_full_profile_ignores_partial_game_ids_and_exports_all_games(self):
        one = self.add_game("One")
        self.add_game("Two")
        result = self.lib.create_orbitpack(game_ids=[one["id"]], full_profile=True, name="all-profile")
        info = self.lib.orbitpacks.inspect(self.paths.decode(result["path"]), verify_files=True)
        self.assertEqual({g["name"] for g in info["manifest"]["games"]}, {"One", "Two"})

    def test_emulator_checkbox_exports_all_emulators_not_only_selected_game_association(self):
        e1 = self.paths.emulators / "E1" / "e1.exe"; e1.parent.mkdir(parents=True); e1.write_bytes(b"MZ1")
        e2 = self.paths.emulators / "E2" / "e2.exe"; e2.parent.mkdir(parents=True); e2.write_bytes(b"MZ2")
        emu1 = self.lib.add_emulator({"name":"E1","platform":"NES","executable":str(e1)})
        self.lib.add_emulator({"name":"E2","platform":"SNES","executable":str(e2)})
        game = self.add_game("NesGame", platform="NES")
        self.lib.update_game(game["id"], {"emulator_id": emu1["id"]})
        result = self.lib.create_orbitpack(game_ids=[game["id"]], include_games=True, include_emulators=True, include_media=False)
        info = self.lib.orbitpacks.inspect(self.paths.decode(result["path"]), verify_files=True)
        self.assertEqual({e["name"] for e in info["manifest"]["emulators"]}, {"E1", "E2"})


class TestMedia062(Orbit062Case):
    def test_gif_cover_is_accepted_and_persisted(self):
        game = self.add_game("GifCover")
        image = self.root / "cover.gif"; image.write_bytes(fake_gif())
        updated = self.lib.set_game_media(game["id"], "cover", str(image))
        target = self.paths.decode(updated["cover"])
        self.assertTrue(target.is_file())
        self.assertEqual(target.suffix.lower(), ".gif")

    def test_avif_cover_is_accepted_and_persisted(self):
        game = self.add_game("AvifCover")
        image = self.root / "cover.avif"; image.write_bytes(fake_avif())
        updated = self.lib.set_game_media(game["id"], "cover", str(image))
        target = self.paths.decode(updated["cover"])
        self.assertTrue(target.is_file())
        self.assertEqual(target.suffix.lower(), ".avif")


    def test_ico_cover_is_accepted_and_persisted(self):
        game = self.add_game("IcoCover")
        image = self.root / "cover.ico"
        image.write_bytes(fake_ico())
        updated = self.lib.set_game_cover(game["id"], str(image))
        target = self.paths.decode(updated["cover"])
        self.assertTrue(target.is_file())
        self.assertEqual(target.suffix.lower(), ".ico")
        self.lib = LibraryService(self.paths, JsonStore(self.paths))
        loaded = next(g for g in self.real_games() if g["id"] == game["id"] )
        self.assertTrue(self.paths.decode(loaded["cover"]).is_file())

    def test_tiff_is_converted_to_png_when_decoder_is_available(self):
        game = self.add_game("TiffCover")
        image = self.root / "cover.tiff"
        image.write_bytes(fake_tiff())
        try:
            updated = self.lib.set_game_cover(game["id"], str(image))
        except ValueError as exc:
            if "no dispone de un decodificador" in str(exc):
                self.skipTest("Este entorno no dispone de conversor TIFF; Windows usa el fallback nativo.")
            raise
        target = self.paths.decode(updated["cover"])
        self.assertTrue(target.is_file())
        self.assertEqual(target.suffix.lower(), ".png")
        self.assertEqual(target.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")

    def test_online_cover_apply_routes_to_cover_directory(self):
        game = self.add_game("OnlineCover")

        def fake_download(_url, destination):
            target = destination.with_suffix(".jpg")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(fake_jpeg())
            return target

        self.lib.cover_search.download = Mock(side_effect=fake_download)
        updated = self.lib.apply_game_art(game["id"], "cover", "https://cdn.steamgriddb.com/test.jpg")
        target = self.paths.decode(updated["cover"])
        self.assertTrue(target.is_file())
        self.assertEqual(target.parent, self.paths.covers.resolve())
        self.assertTrue(target.read_bytes().startswith(b"\xff\xd8\xff"))

    def test_steamgriddb_download_accepts_generic_mime_when_signature_is_valid(self):
        class FakeResponse:
            status = 200
            headers = {"Content-Type": "application/octet-stream"}
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def read(self, _size=-1): return fake_png()

        with patch("app.services.cover_search.urlopen", return_value=FakeResponse()):
            target = self.lib.cover_search.download("https://cdn.steamgriddb.com/test/no-extension", self.root / "downloaded")
        self.assertEqual(target.suffix.lower(), ".png")
        self.assertTrue(target.is_file())


    def test_all_supported_online_cover_formats_can_be_applied(self):
        signatures = {
            ".png": fake_png(),
            ".jpg": fake_jpeg(),
            ".webp": fake_webp(),
            ".gif": fake_gif(),
            ".avif": fake_avif(),
            ".ico": fake_ico(),
            ".bmp": fake_bmp(),
        }
        game = self.add_game("AllFormats")
        for ext, raw in signatures.items():
            with self.subTest(ext=ext):
                def fake_download(_url, destination, ext=ext, raw=raw):
                    target = destination.with_suffix(ext)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(raw)
                    return target
                self.lib.cover_search.download = Mock(side_effect=fake_download)
                updated = self.lib.apply_game_art(game["id"], "cover", f"https://cdn.steamgriddb.com/test{ext}")
                target = self.paths.decode(updated["cover"])
                self.assertTrue(target.is_file())
                self.assertEqual(target.suffix.lower(), ext)


    def test_manual_bmp_cover_survives_restart(self):
        game = self.add_game("BmpRestart")
        image = self.root / "manual.bmp"; image.write_bytes(fake_bmp())
        updated = self.lib.set_game_cover(game["id"], str(image))
        stored = updated["cover"]
        self.lib = LibraryService(self.paths, JsonStore(self.paths))
        loaded = next(g for g in self.real_games() if g["id"] == game["id"])
        target = self.paths.decode(loaded["cover"])
        self.assertEqual(loaded["cover"], stored)
        self.assertTrue(target and target.is_file())
        self.assertEqual(target.suffix.lower(), ".bmp")

    def test_manual_cover_uses_real_content_not_wrong_extension(self):
        game = self.add_game("WrongSuffix")
        image = self.root / "actually-png.jpg"; image.write_bytes(fake_png())
        updated = self.lib.set_game_cover(game["id"], str(image))
        target = self.paths.decode(updated["cover"])
        self.assertEqual(target.suffix.lower(), ".png")
        self.assertEqual(target.read_bytes(), fake_png())

    def test_existing_managed_cover_is_not_rewritten_on_restart(self):
        game = self.add_game("ExistingManaged")
        source = self.root / "existing.png"
        source.write_bytes(fake_png())
        updated = self.lib.set_game_cover(game["id"], str(source))
        target = self.paths.decode(updated["cover"])
        before_bytes = target.read_bytes()
        before_mtime = target.stat().st_mtime_ns
        before_ref = updated["cover"]
        self.lib = LibraryService(self.paths, JsonStore(self.paths))
        loaded = next(g for g in self.real_games() if g["id"] == game["id"] )
        after = self.paths.decode(loaded["cover"])
        self.assertEqual(loaded["cover"], before_ref)
        self.assertEqual(after.read_bytes(), before_bytes)
        self.assertEqual(after.stat().st_mtime_ns, before_mtime)

    def test_legacy_external_cover_is_migrated_without_deleting_original(self):
        game = self.add_game("LegacyExternal")
        external = self.root / "outside" / "legacy.jpg"; external.parent.mkdir(); external.write_bytes(fake_jpeg())
        games = self.lib._profile_load("games", [])
        target_game = next(g for g in games if g.get("id") == game["id"])
        target_game["cover"] = str(external.resolve())
        self.lib._profile_save("games", games)
        self.lib = LibraryService(self.paths, JsonStore(self.paths))
        loaded = next(g for g in self.real_games() if g["id"] == game["id"])
        managed = self.paths.decode(loaded["cover"])
        self.assertTrue(external.is_file())
        self.assertTrue(managed and managed.is_file())
        self.assertEqual(managed.parent, self.paths.covers.resolve())
        self.assertTrue(str(loaded["cover"]).startswith("@launcher/media/covers/"))

    def test_legacy_mismatched_managed_extension_is_repaired_on_restart(self):
        game = self.add_game("LegacyMismatch")
        wrong = self.paths.covers / "old-cover.jpg"; wrong.parent.mkdir(parents=True, exist_ok=True); wrong.write_bytes(fake_png())
        games = self.lib._profile_load("games", [])
        target_game = next(g for g in games if g.get("id") == game["id"])
        target_game["cover"] = self.paths.encode(wrong)
        self.lib._profile_save("games", games)
        self.lib = LibraryService(self.paths, JsonStore(self.paths))
        loaded = next(g for g in self.real_games() if g["id"] == game["id"])
        managed = self.paths.decode(loaded["cover"])
        self.assertTrue(managed and managed.is_file())
        self.assertEqual(managed.suffix.lower(), ".png")
        self.assertTrue(wrong.is_file(), "La migración no debe borrar el fichero legacy original")

    def test_changing_one_cover_does_not_break_other_game_shared_legacy_cover(self):
        first = self.add_game("FirstShared")
        second = self.add_game("SecondShared")
        shared = self.paths.covers / "shared.jpg"; shared.parent.mkdir(parents=True, exist_ok=True); shared.write_bytes(fake_jpeg())
        games = self.lib._profile_load("games", [])
        for item in games:
            if item.get("id") in {first["id"], second["id"]}:
                item["cover"] = self.paths.encode(shared)
        self.lib._profile_save("games", games)
        replacement = self.root / "replacement.png"; replacement.write_bytes(fake_png())
        self.lib.set_game_cover(first["id"], str(replacement))
        second_loaded = next(g for g in self.real_games() if g["id"] == second["id"])
        self.assertEqual(self.paths.decode(second_loaded["cover"]), shared.resolve())
        self.assertTrue(shared.is_file())

    def test_real_steamgriddb_download_pipeline_persists_after_restart(self):
        game = self.add_game("OnlineRestart")
        class FakeResponse:
            status = 200
            headers = {"Content-Type": "application/octet-stream"}
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def read(self, _size=-1): return fake_bmp()
        with patch("app.services.cover_search.urlopen", return_value=FakeResponse()):
            updated = self.lib.apply_game_art(game["id"], "cover", "https://cdn.steamgriddb.com/asset/no-extension")
        self.assertEqual(self.paths.decode(updated["cover"]).suffix.lower(), ".bmp")
        self.lib = LibraryService(self.paths, JsonStore(self.paths))
        loaded = next(g for g in self.real_games() if g["id"] == game["id"])
        self.assertTrue(self.paths.decode(loaded["cover"]).is_file())
        self.assertEqual(self.paths.decode(loaded["cover"]).suffix.lower(), ".bmp")
    def test_http_art_apply_pipeline_survives_server_restart(self):
        game = self.add_game("HttpOnlineCover")

        class FakeResponse:
            status = 200
            headers = {"Content-Type": "application/octet-stream"}
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def read(self, _size=-1): return fake_bmp()

        server = LauncherServer(self.root)
        host, port = server.start()
        base = f"http://{host}:{port}"
        try:
            body = json.dumps({
                "kind": "cover",
                "url": "https://cdn.steamgriddb.com/asset/generic-response",
            }).encode("utf-8")
            request = Request(
                f"{base}/api/games/{game['id']}/art/apply",
                data=body, method="POST", headers={"Content-Type": "application/json"},
            )
            with patch("app.services.cover_search.urlopen", return_value=FakeResponse()):
                with urlopen(request) as response:
                    result = json.loads(response.read().decode("utf-8"))
            cover = result["game"]["cover"]
            self.assertTrue(cover.startswith("@launcher/media/covers/"))
            self.assertTrue(cover.endswith(".bmp"))
            media_url = f"{base}/media/{cover[len('@launcher/media/'):]}"
            with urlopen(media_url) as response:
                self.assertEqual(response.headers.get_content_type(), "image/bmp")
                self.assertEqual(response.read(), fake_bmp())
        finally:
            server.stop()

        restarted = LauncherServer(self.root)
        host, port = restarted.start()
        base = f"http://{host}:{port}"
        try:
            with urlopen(f"{base}/api/state") as response:
                state = json.loads(response.read().decode("utf-8"))
            loaded = next(g for g in state["games"] if g.get("id") == game["id"] )
            self.assertEqual(loaded["cover"], cover)
            media_url = f"{base}/media/{cover[len('@launcher/media/'):]}"
            with urlopen(media_url) as response:
                self.assertEqual(response.headers.get_content_type(), "image/bmp")
                self.assertEqual(response.read(), fake_bmp())
        finally:
            restarted.stop()



class TestAI062(Orbit062Case):
    def test_natural_language_emulator_question_needs_no_punctuation(self):
        game = self.add_game("Shadow Test", platform="PlayStation 2")
        result = self.lib.ask_ai("que emulador necesito para shadow test")
        self.assertEqual(result["kind"], "emulator-help")
        self.assertIn("PCSX2", result["answer"])

    def test_local_model_is_used_when_configured(self):
        self.lib.save_settings({"ai": {"local_model": {"enabled": True, "provider": "ollama", "endpoint": "http://127.0.0.1:11434", "model": "test"}}})
        self.lib.assistant.local_model.generate = Mock(return_value="Respuesta local")
        result = self.lib.ask_ai("explica mi colección con detalle")
        self.assertEqual(result["engine"], "local-model")
        self.assertEqual(result["answer"], "Respuesta local")

    def test_local_model_failure_falls_back_offline(self):
        self.lib.save_settings({"ai": {"local_model": {"enabled": True, "provider": "ollama", "endpoint": "http://127.0.0.1:11434", "model": "test"}}})
        self.lib.assistant.local_model.generate = Mock(side_effect=OSError("offline"))
        result = self.lib.ask_ai("una pregunta abierta cualquiera")
        self.assertEqual(result["engine"], "offline-integrated")

    def test_online_search_is_not_used_when_disabled(self):
        self.lib.assistant.online_search.search = Mock(return_value=[{"title": "No"}])
        self.lib.save_settings({"ai": {"online_search": {"enabled": False}}})
        result = self.lib.ask_ai("busca en internet noticias de emulación")
        self.assertFalse(self.lib.assistant.online_search.search.called)
        self.assertNotEqual(result["engine"], "online-search")

    def test_online_search_is_used_only_when_enabled_and_requested(self):
        self.lib.assistant.online_search.search = Mock(return_value=[{"title": "Resultado", "snippet": "Texto", "url": "https://example.invalid"}])
        self.lib.save_settings({"ai": {"online_search": {"enabled": True, "language": "es"}}})
        result = self.lib.ask_ai("busca en internet historia de los emuladores")
        self.assertTrue(self.lib.assistant.online_search.search.called)
        self.assertEqual(result["engine"], "online-search")
        self.assertEqual(result["items"][0]["title"], "Resultado")

    def test_local_model_rejects_remote_endpoint(self):
        with self.assertRaises(ValueError):
            LocalModelRuntime._endpoint({"provider": "ollama", "endpoint": "https://example.com", "model": "x"})


class TestFrontend062(Orbit062Case):
    def test_navigation_module_spatial_and_gamepad_labels(self):
        script = r'''
const n=require('./app/static/navigation.js');
const rects=[
 {left:0,top:0,width:100,height:40},
 {left:-120,top:55,width:100,height:40},
 {left:0,top:100,width:100,height:40},
 {left:110,top:0,width:100,height:40}
];
if(n.bestSpatialIndex(rects,0,0,1)!==2) process.exit(10);
if(n.bestSpatialIndex(rects,0,1,0)!==3) process.exit(11);
if(n.gamepadStyle('DualSense Wireless Controller')!=='playstation') process.exit(12);
if(n.gamepadStyle('Nintendo Switch Pro Controller')!=='nintendo') process.exit(13);
if(n.gamepadStyle('Xbox Wireless Controller')!=='xbox') process.exit(14);
if(n.gamepadLabels('playstation').accept!=='✕') process.exit(15);
if(n.applyDeadzone(.1,.2)!==0) process.exit(16);
'''
        proc = subprocess.run(["node", "-e", script], cwd=self.root, capture_output=True, text=True)
        # The test root is temporary, so run the shipped module from project cwd instead.
        if proc.returncode != 0 and "Cannot find module" in (proc.stderr or ""):
            project = Path(__file__).resolve().parents[1]
            proc = subprocess.run(["node", "-e", script], cwd=project, capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_frontend_declares_right_stick_pointer_and_dynamic_hints(self):
        project = Path(__file__).resolve().parents[1]
        js = (project / "app/static/app.js").read_text(encoding="utf-8")
        html = (project / "app/static/index.html").read_text(encoding="utf-8")
        self.assertIn("moveGamepadPointer", js)
        self.assertIn("bestSpatialIndex", js)
        self.assertIn('id="gamepadPointer"', html)
        self.assertIn('id="hintAccept"', html)

    def test_settings_ui_exposes_partial_orbitpack_and_local_ai(self):
        project = Path(__file__).resolve().parents[1]
        js = (project / "app/static/app.js").read_text(encoding="utf-8")
        self.assertIn("include_configuration", js)
        self.assertIn("profile_strategy", js)
        self.assertIn("config_conflict", js)
        self.assertIn("aiLocalModel", js)
        self.assertIn("data-ai-toggle", js)

    def test_export_ui_has_native_save_picker_and_real_progress_polling(self):
        project = Path(__file__).resolve().parents[1]
        js = (project / "app/static/app.js").read_text(encoding="utf-8")
        css = (project / "app/static/styles.css").read_text(encoding="utf-8")
        self.assertIn("/api/dialog/save_orbitpack", js)
        self.assertIn("/api/orbitpack/export/start", js)
        self.assertIn("/api/orbitpack/export/progress", js)
        self.assertIn("orbitExportBar", js)
        self.assertIn("export-progress-fill", css)

    def test_export_ui_exposes_individual_game_selection_controls(self):
        project = Path(__file__).resolve().parents[1]
        js = (project / "app/static/app.js").read_text(encoding="utf-8")
        self.assertIn('name="game_id"', js)
        self.assertIn("orbitpackSelectAll", js)
        self.assertIn("orbitpackSelectNone", js)
        self.assertIn("payload.game_ids", js)
        self.assertIn("Seleccionar todo", js)
        self.assertIn("Deseleccionar todo", js)
        self.assertIn("leaveFullProfile", js)


if __name__ == "__main__":
    unittest.main()
