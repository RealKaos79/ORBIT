"""Regression tests for the 0.6.2 import/profile repair (no user data)."""
from __future__ import annotations

import io
import json
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import patch

from app.core.paths import PortablePaths
from app.core.storage import JsonStore
from app.services.library import LibraryService
from app.services.orbitpack import OrbitPackService
from app.server import LauncherServer
from test_v062 import fake_png, fake_bmp


class ImportProfileCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="orbit-import-fix-")
        self.root = Path(self.tmp.name).resolve()
        (self.root / "VERSION").write_text("0.6.2\n", encoding="utf-8")
        self.paths = PortablePaths(self.root)
        self.lib = LibraryService(self.paths, JsonStore(self.paths))

    def tearDown(self):
        self.tmp.cleanup()

    def game(self, name="Mario", platform="GameCube", lib=None, paths=None):
        lib, paths = lib or self.lib, paths or self.paths
        game_file = paths.games / platform / (name + (".exe" if platform == "PC" else ".iso"))
        game_file.parent.mkdir(parents=True, exist_ok=True)
        game_file.write_bytes(b"EXE" if platform == "PC" else b"ISO-DATA")
        return lib.add_game({"name": name, "platform": platform, "path": str(game_file)})

    def receiver(self):
        tmp = tempfile.TemporaryDirectory(prefix="orbit-import-receiver-")
        paths = PortablePaths(Path(tmp.name))
        (paths.root / "VERSION").write_text("0.6.2\n", encoding="utf-8")
        return tmp, paths, LibraryService(paths, JsonStore(paths))

    def pack(self, **opts):
        defaults = dict(include_games=True, include_game_files=True, include_emulators=False,
                        include_media=False, include_saves=False, include_configuration=False, include_other=False)
        defaults.update(opts)
        return self.paths.decode(self.lib.create_orbitpack(**defaults)["path"])

    @staticmethod
    def actual(lib):
        return [x for x in lib.games() if not x.get("demo")]


class TestFunctionalImports(ImportProfileCase):
    def test_metadata_only_export_import_is_not_noop(self):
        self.game()
        p = self.pack(include_game_files=False)
        tmp, paths, receiver = self.receiver()
        try:
            outcome = receiver.import_orbitpack(str(p), components=["games"])
            games = self.actual(receiver)
            self.assertEqual(outcome["added"], 1)
            self.assertEqual(outcome["metadata_only"], 1)
            self.assertEqual(games[0]["name"], "Mario")
            self.assertFalse(games[0]["available"])
            self.assertEqual(games[0]["path"], "@launcher/games/GameCube/Mario.iso")
            self.assertEqual(self.actual(LibraryService(paths, JsonStore(paths)))[0]["id"], games[0]["id"])
        finally:
            tmp.cleanup()

    def test_metadata_only_reconnects_existing_automatic_folder_file(self):
        self.game()
        pack = self.pack(include_game_files=False)
        tmp, paths, receiver = self.receiver()
        try:
            destination = paths.games / "Custom" / "GC"
            receiver.set_platform_destination("GameCube", str(destination))
            destination.mkdir(parents=True, exist_ok=True)
            (destination / "Mario.iso").write_bytes(b"EXISTING")
            result = receiver.import_orbitpack(str(pack), components=["games"])
            self.assertEqual(result["metadata_only"], 0)
            self.assertEqual(self.actual(receiver)[0]["path"], paths.encode(destination / "Mario.iso"))
            self.assertEqual((destination / "Mario.iso").read_bytes(), b"EXISTING")
        finally:
            tmp.cleanup()

    def test_only_configuration_does_not_import_games_or_payload(self):
        self.game()
        self.lib.save_settings({"theme": "forest"})
        pack = self.pack(include_configuration=True)
        tmp, paths, receiver = self.receiver()
        try:
            result = receiver.import_orbitpack(str(pack), components=["configuration"], config_conflict="import-preferred")
            self.assertFalse(self.actual(receiver))
            self.assertEqual(receiver.settings()["theme"], "forest")
            self.assertEqual(result["components"], ["configuration"])
            self.assertFalse(list(paths.games.rglob("*.iso")))
        finally:
            tmp.cleanup()

    def test_only_covers_can_merge_without_creating_games(self):
        src_game = self.game()
        image = self.root / "manual.bmp"
        image.write_bytes(fake_bmp())
        self.lib.set_game_cover(src_game["id"], str(image))
        pack = self.pack(include_media=True)
        tmp, paths, receiver = self.receiver()
        try:
            dest_game = self.game(lib=receiver, paths=paths)
            outcome = receiver.import_orbitpack(str(pack), components=["media"])
            self.assertEqual(outcome["added"], 0)
            self.assertEqual(outcome["media"], 1)
            self.assertEqual(len(self.actual(receiver)), 1)
            self.assertTrue(paths.decode(self.actual(receiver)[0]["cover"]).is_file())
            self.assertEqual(self.actual(receiver)[0]["id"], dest_game["id"])
        finally:
            tmp.cleanup()

    def test_only_saves_preserves_library_and_stores_portable_saves(self):
        src_game = self.game()
        original = self.lib.saves.portable_target(src_game, "default")
        original.mkdir(parents=True, exist_ok=True)
        (original / "slot1.sav").write_bytes(b"SAVE-ABC")
        pack = self.pack(include_saves=True)
        tmp, paths, receiver = self.receiver()
        try:
            receiver_game = self.game(lib=receiver, paths=paths)
            result = receiver.import_orbitpack(str(pack), components=["saves"])
            self.assertEqual(result["saves"], 1)
            self.assertEqual(len(self.actual(receiver)), 1)
            target = receiver.saves.portable_target(receiver_game, "default")
            self.assertEqual((target / "slot1.sav").read_bytes(), b"SAVE-ABC")
        finally:
            tmp.cleanup()

    def test_progress_real_phases_monotonic_and_persistent_after_restart(self):
        self.game("One")
        self.game("Two")
        pack = self.pack()
        tmp, paths, receiver = self.receiver()
        events = []
        try:
            outcome = receiver.import_orbitpack(str(pack), components=["games"], progress=events.append)
            percentages = [x["percent"] for x in events]
            self.assertGreater(len(events), 5)
            self.assertEqual(percentages, sorted(percentages))
            self.assertEqual(percentages[-1], 1)
            self.assertIn("verifying", {x["phase"] for x in events})
            self.assertIn("extracting", {x["phase"] for x in events})
            self.assertIn("importing", {x["phase"] for x in events})
            self.assertEqual(len(self.actual(LibraryService(paths, JsonStore(paths)))), 2)
            self.assertEqual(outcome["added"], 2)
        finally:
            tmp.cleanup()

    def test_nonselected_components_never_affect_receiver(self):
        src = self.game()
        image = self.root / "cover.png"
        image.write_bytes(fake_png())
        self.lib.set_game_cover(src["id"], str(image))
        self.lib.save_settings({"theme": "ocean"})
        pack = self.pack(include_media=True, include_configuration=True)
        tmp, paths, receiver = self.receiver()
        try:
            receiver.import_orbitpack(str(pack), components=["games"])
            self.assertIsNone(self.actual(receiver)[0]["cover"])
            self.assertNotEqual(receiver.settings()["theme"], "ocean")
            self.assertFalse(list(paths.covers.iterdir()))
        finally:
            tmp.cleanup()

    def test_corrupt_archive_cannot_modify_receiver(self):
        self.game()
        pack = self.pack()
        with zipfile.ZipFile(pack, "a") as z:
            z.writestr("payload/unverified.bin", b"CORRUPTION")
        tmp, paths, receiver = self.receiver()
        try:
            with self.assertRaises(ValueError):
                receiver.import_orbitpack(str(pack))
            self.assertFalse(self.actual(receiver))
            self.assertFalse(list(paths.games.rglob("*.iso")))
        finally:
            tmp.cleanup()

    def test_duplicate_zip_entries_rejected_before_extraction(self):
        self.game()
        pack = self.pack()
        with zipfile.ZipFile(pack, "a") as z:
            with __import__("warnings").catch_warnings():
                __import__("warnings").simplefilter("ignore", UserWarning)
                z.writestr("manifest.sha256", "NOT-VALID")
        with self.assertRaisesRegex(ValueError, "duplicados"):
            OrbitPackService(self.paths).extract(str(pack))

    def test_failed_copy_removes_partial_files_and_restores_library(self):
        self.game()
        pack = self.pack()
        tmp, paths, receiver = self.receiver()
        try:
            original = Path.open
            def broken_open(path, *args, **kwargs):
                if str(path).endswith("Mario.iso") and args and args[0] == "xb" and str(path).startswith(str(paths.root)):
                    raise OSError("simulated disk full")
                return original(path, *args, **kwargs)
            with patch.object(Path, "open", broken_open):
                with self.assertRaises(OSError):
                    receiver.import_orbitpack(str(pack), components=["games"])
            self.assertFalse(self.actual(receiver))
            self.assertFalse(list(paths.games.rglob("*.iso")))
        finally:
            tmp.cleanup()

    def test_new_profile_import_does_not_modify_default_profile(self):
        self.game()
        pack = self.pack()
        tmp, paths, receiver = self.receiver()
        try:
            old = self.game("MyOldGame", lib=receiver, paths=paths)
            receiver.import_orbitpack(str(pack), components=["games"], profile_strategy="new-profile")
            self.assertEqual({x["name"] for x in self.actual(receiver)}, {"Mario"})
            receiver.select_profile("default")
            self.assertEqual({x["id"] for x in self.actual(receiver)}, {old["id"]})
        finally:
            tmp.cleanup()


class TestProfiles(ImportProfileCase):
    def test_existing_profile_name_color_preserves_games_and_settings(self):
        p = self.lib.add_profile("Original", "cat")
        self.lib.select_profile(p["id"])
        original_game = self.game("Owned")
        self.lib.save_settings({"theme": "forest"})
        updated = self.lib.update_profile(p["id"], {"name": "Nuevo", "color": "#AA22BB"})
        self.assertEqual(updated["name"], "Nuevo")
        self.assertEqual(updated["color"], "#aa22bb")
        fresh = LibraryService(self.paths, JsonStore(self.paths))
        self.assertEqual(fresh.profiles()["items"][-1]["name"], "Nuevo")
        self.assertEqual(fresh.games()[0]["id"], original_game["id"])
        self.assertEqual(fresh.settings()["theme"], "forest")

    def test_profile_photo_validation_persistence_and_no_reset_on_rename(self):
        p = self.lib.add_profile("Photo", "orbit")
        photo = self.root / "photo.jpg"  # extension lies; real bytes PNG
        photo.write_bytes(fake_png())
        self.lib.set_profile_avatar(p["id"], str(photo))
        old = next(x for x in self.lib.profiles()["items"] if x["id"] == p["id"])["avatar"]
        self.assertTrue(old.endswith(".png"))
        self.lib.update_profile(p["id"], {"name": "Renamed", "color": "#114488"})
        profile = next(x for x in LibraryService(self.paths, JsonStore(self.paths)).profiles()["items"] if x["id"] == p["id"])
        self.assertEqual(profile["avatar"], old)
        self.assertTrue(self.paths.decode(old).is_file())

    def test_invalid_new_photo_never_deletes_old_photo(self):
        p = self.lib.add_profile("Photo", "orbit")
        valid = self.root / "photo.png"
        valid.write_bytes(fake_png())
        old = self.lib.set_profile_avatar(p["id"], str(valid))["avatar"]
        corrupt = self.root / "bad.png"
        corrupt.write_bytes(b"not an image")
        with self.assertRaises(ValueError):
            self.lib.set_profile_avatar(p["id"], str(corrupt))
        self.assertEqual(self.lib._find_profile(p["id"])["avatar"], old)
        self.assertTrue(self.paths.decode(old).is_file())

    def test_shared_legacy_profile_photo_not_deleted_when_one_profile_changes(self):
        p1 = self.lib.add_profile("A", "orbit")
        p2 = self.lib.add_profile("B", "orbit")
        src = self.root / "shared.png"
        src.write_bytes(fake_png())
        shared = self.lib.set_profile_avatar(p1["id"], str(src))["avatar"]
        settings = self.lib._global_settings()
        next(item for item in settings["profiles"]["items"] if item["id"] == p2["id"])["avatar"] = shared
        self.lib.store.save("settings", settings)
        self.lib.update_profile(p1["id"], {"avatar": "cat"})
        self.assertTrue(self.paths.decode(shared).is_file())
        self.assertEqual(self.lib._find_profile(p2["id"])["avatar"], shared)
        self.lib.set_profile_avatar(p1["id"], str(src))
        self.assertTrue(self.paths.decode(shared).is_file())
        self.assertEqual(self.lib._find_profile(p2["id"])["avatar"], shared)

    def test_profile_color_rejects_invalid_values_without_saving(self):
        profile = self.lib.add_profile("Safe", "star")
        with self.assertRaises(ValueError):
            self.lib.update_profile(profile["id"], {"name": "Changed", "color": "red;background:url()"})
        self.assertEqual(self.lib._find_profile(profile["id"])["name"], "Safe")

    def test_full_profile_transfers_color_without_admin_or_secret(self):
        p = self.lib.add_profile("Purple", "star")
        self.lib.update_profile(p["id"], {"color": "#aa33cc"})
        self.lib.select_profile(p["id"])
        pack = self.paths.decode(self.lib.create_orbitpack(full_profile=True)["path"])
        tmp, paths, receiver = self.receiver()
        try:
            result = receiver.import_orbitpack(str(pack), profile_strategy="new-profile")
            matching = next(x for x in receiver.profiles()["items"] if x["id"] == result["profile_id"])
            self.assertEqual(matching["color"], "#aa33cc")
        finally:
            tmp.cleanup()


class TestHttpImport(ImportProfileCase):
    @staticmethod
    def request(base, route, payload=None, binary=False):
        data = payload if binary else (json.dumps(payload).encode() if payload is not None else None)
        req = Request(base+route, data=data, headers={"Content-Type": "application/octet-stream" if binary else "application/json"} if data is not None else {}, method="POST" if data is not None else "GET")
        with urlopen(req, timeout=20) as response:
            return json.load(response)

    def test_browser_upload_inspect_async_import_and_poll(self):
        self.game()
        pack = self.pack()
        server_root = self.root / "receiver-http"
        server_root.mkdir()
        server = LauncherServer(server_root)
        host, port = server.start()
        base=f"http://{host}:{port}"
        try:
            up = self.request(base, "/api/orbitpack/upload", pack.read_bytes(), binary=True)
            staged=Path(up["path"])
            self.assertTrue(staged.is_file())
            inspection=self.request(base,"/api/orbitpack/inspect",{"path":str(staged)})
            self.assertTrue(inspection["result"]["components"]["games"])
            started=self.request(base,"/api/orbitpack/import/start",{"path":str(staged),"components":["games"]})
            self.assertTrue(started["job_id"])
            for _ in range(250):
                job=self.request(base, "/api/orbitpack/import/progress?job_id="+started["job_id"])["job"]
                if job["status"] in ("done","error"):
                    break
                time.sleep(.025)
            self.assertEqual(job["status"],"done",job.get("error"))
            self.assertEqual(job["percent"],1)
            self.assertEqual(job["result"]["added"],1)
            self.assertFalse(staged.exists())
            server.stop()
            restarted=LauncherServer(server_root)
            self.assertEqual({x["name"] for x in self.actual(restarted.library)}, {"Mario"})
        finally:
            if server.is_running:
                server.stop()

    def test_upload_rejects_nonbinary_content_type(self):
        server=LauncherServer(self.root / "server-upload-invalid")
        host,port=server.start()
        try:
            req=Request(f"http://{host}:{port}/api/orbitpack/upload",data=b"TEST",headers={"Content-Type":"application/json"},method="POST")
            with self.assertRaises(HTTPError) as exc:
                urlopen(req,timeout=10)
            self.assertEqual(exc.exception.code,400)
        finally:
            server.stop()

    def test_http_browser_photo_validates_bytes_saves_and_survives_restart(self):
        server_root = self.root / "receiver-avatar"
        server_root.mkdir()
        server = LauncherServer(server_root)
        person = server.library.add_profile("Custom", "orbit")
        host, port = server.start()
        base = f"http://{host}:{port}"
        try:
            original = self.request(base, f"/api/profiles/{person['id']}/avatar/upload", fake_png(), binary=True)
            avatar = original["profile"]["avatar"]
            self.assertTrue(avatar.endswith(".png"))
            self.assertTrue(server.paths.decode(avatar).is_file())
            self.assertFalse(list((server.paths.data / ".avatar-staging").glob("*.bin")))
            with self.assertRaises(HTTPError) as ctx:
                self.request(base, f"/api/profiles/{person['id']}/avatar/upload", b"bad-image", binary=True)
            self.assertEqual(ctx.exception.code, 400)
            self.assertEqual(server.library._find_profile(person["id"])["avatar"], avatar)
            server.stop()
            restarted = LauncherServer(server_root)
            self.assertEqual(restarted.library._find_profile(person["id"])["avatar"], avatar)
            self.assertTrue(restarted.paths.decode(avatar).is_file())
        finally:
            if server.is_running:
                server.stop()

    def test_import_job_rejects_concurrent_run_without_stealing_lock(self):
        server = LauncherServer(self.root / "receiver-concurrent")
        server._active_import.acquire()
        try:
            with self.assertRaisesRegex(ValueError, "importación en curso"):
                server._start_import_job({"path": "not-started.orbitpack"})
            self.assertTrue(server._active_import.locked())
        finally:
            server._active_import.release()

    def test_frontend_wires_real_import_and_profile_edit(self):
        js=(Path(__file__).resolve().parents[1]/"app"/"static"/"app.js").read_text(encoding="utf-8")
        self.assertIn("/api/orbitpack/import/start",js)
        self.assertIn("/api/orbitpack/import/progress",js)
        self.assertIn("/api/orbitpack/upload",js)
        self.assertIn('function chooseProfilePhoto(',js)
        self.assertIn('/avatar/upload',js)
        self.assertIn('data-action="profile-manager"',js)
        self.assertIn('Seleccionar todo',js)
        self.assertIn('Deseleccionar todo',js)
