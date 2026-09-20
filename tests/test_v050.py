from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import time
import unittest
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from app.core.paths import PortablePaths
from app.core.storage import JsonStore
from app.server import LauncherServer
from app.services.library import LibraryService
from app.services.orbitpack import OrbitPackService
from app.services.performance import estimate_game_performance


class OrbitCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="orbit-v050-test-")
        self.root = Path(self.tmp.name).resolve()
        (self.root / "VERSION").write_text("0.5.0\n", encoding="utf-8")
        self.paths = PortablePaths(self.root)
        self.store = JsonStore(self.paths)
        self.lib = LibraryService(self.paths, self.store)

    def tearDown(self):
        self.tmp.cleanup()

    def real_games(self):
        return [g for g in self.lib.games() if not g.get("demo")]

    def add_pc_game(self, name="Test PC", *, save=False):
        exe = self.paths.games / f"{name}.exe"
        exe.parent.mkdir(parents=True, exist_ok=True)
        exe.write_bytes(b"MZ-not-a-real-exe")
        payload = {"name": name, "platform": "PC", "path": str(exe), "executable": str(exe)}
        if save:
            save_dir = self.paths.saves / "external-source"
            save_dir.mkdir(parents=True, exist_ok=True)
            (save_dir / "slot.dat").write_text("SAVE-A", encoding="utf-8")
            payload["save_path"] = str(save_dir)
        return self.lib.add_game(payload)


class TestPaths(OrbitCase):
    def test_portable_paths_and_traversal(self):
        inside = self.paths.games / "A" / "x.rom"
        inside.parent.mkdir(parents=True, exist_ok=True)
        inside.write_bytes(b"x")
        enc = self.paths.encode(inside)
        self.assertEqual(enc, "@launcher/games/A/x.rom")
        self.assertEqual(self.paths.decode(enc), inside.resolve())
        outside = Path(tempfile.gettempdir()) / "outside-orbit-test.bin"
        self.assertTrue(Path(self.paths.encode(outside)).is_absolute())
        with self.assertRaises(ValueError):
            self.paths.decode("@launcher/../escape")

    def test_layout_contains_system_folder(self):
        self.assertTrue(self.paths.system.is_dir())


class TestMigrationAndProfiles(OrbitCase):
    def test_legacy_privacy_key_is_removed(self):
        settings = self.lib.default_settings()
        settings["privacy_mode"] = True
        self.store.save("settings", settings)
        # Recreate service to execute migration.
        self.lib = LibraryService(self.paths, self.store)
        self.assertNotIn("privacy_mode", self.lib.settings())
        persisted = self.store.load("settings", {})
        self.assertNotIn("privacy_mode", persisted)
        self.lib.save_settings({"privacy_mode": True})
        self.assertNotIn("privacy_mode", self.lib.settings())

    def test_profile_library_and_settings_are_isolated(self):
        default_game = self.add_pc_game("Principal")
        p = self.lib.add_profile("Cristina", "star")
        self.lib.select_profile(p["id"])
        self.assertFalse(any(g.get("id") == default_game["id"] for g in self.real_games()))
        self.lib.save_settings({"theme": "light"})
        other_game = self.add_pc_game("CristinaGame")
        self.assertEqual(self.lib.settings()["theme"], "light")
        self.lib.select_profile("default")
        self.assertTrue(any(g.get("id") == default_game["id"] for g in self.real_games()))
        self.assertFalse(any(g.get("id") == other_game["id"] for g in self.real_games()))
        self.assertNotEqual(self.lib.settings()["theme"], "light")

    def test_profile_ai_memory_is_isolated(self):
        self.lib.ask_ai("recuerda que prefiero juegos cortos")
        self.assertTrue(self.lib.ai_memory()["recent_queries"])
        p = self.lib.add_profile("Familia")
        self.lib.select_profile(p["id"])
        self.assertEqual(self.lib.ai_memory().get("recent_queries"), [])
        self.lib.ask_ai("recuerda que prefiero cooperativos")
        second = self.lib.ai_memory()
        self.lib.select_profile("default")
        first = self.lib.ai_memory()
        self.assertNotEqual(first.get("preferences"), second.get("preferences"))


class TestGamesRequirementsPerformance(OrbitCase):
    def test_game_metadata_persists_and_validates_demand(self):
        game = self.add_pc_game("Metadata")
        updated = self.lib.update_game(game["id"], {"region": "EUR", "revision": "Rev 2", "performance_demand": 5})
        self.assertEqual((updated["region"], updated["revision"], updated["performance_demand"]), ("EUR", "Rev 2", 5))
        self.lib = LibraryService(self.paths, self.store)
        again = next(g for g in self.lib.games() if g.get("id") == game["id"])
        self.assertEqual((again["region"], again["revision"], again["performance_demand"]), ("EUR", "Rev 2", 5))
        with self.assertRaises(ValueError):
            self.lib.update_game(game["id"], {"performance_demand": "potente"})

    def test_switch_requirements_missing_then_present(self):
        rom = self.paths.games / "Switch" / "Demo.nsp"
        rom.parent.mkdir(parents=True, exist_ok=True); rom.write_bytes(b"rom")
        game = self.lib.add_game({"name": "Switch Demo", "platform": "Nintendo Switch", "path": str(rom)})
        status = self.lib.requirements_for_game(game["id"])
        self.assertTrue(status["required"])
        self.assertFalse(status["ok"])
        fw = self.paths.system / "switch" / "firmware"; fw.mkdir(parents=True); (fw / "file.nca").write_bytes(b"firmware")
        keys = self.paths.system / "switch" / "keys"; keys.mkdir(parents=True); (keys / "prod.keys").write_text("keydata", encoding="utf-8")
        status = self.lib.requirements_for_game(game["id"])
        self.assertTrue(status["ok"])
        self.assertIn("no descarga ni distribuye", status["legal_note"])

    def test_performance_never_invents_fps_and_handles_unknown(self):
        game = {"platform": "Nintendo Switch", "performance_demand": 5}
        unknown = estimate_game_performance(game, {"cpu_cores": 0, "ram_bytes": 0})
        self.assertEqual(unknown["label"], "Sin datos suficientes")
        self.assertIn("no inventa FPS", unknown["disclaimer"])
        known = estimate_game_performance(game, {"cpu_cores": 8, "ram_bytes": 16 * 1024**3, "gpu": "GPU Test"})
        self.assertIn(known["label"], {"Excelente", "Muy bueno", "Aceptable", "Puede tener problemas", "No recomendado"})
        self.assertIn("no inventa FPS", known["disclaimer"])


class TestThemesAndAI(OrbitCase):
    def test_custom_theme_save_export_import_and_official_protection(self):
        theme = self.lib.save_custom_theme({"name": "Cristina Neon", "accent": "#112233", "size": "large", "shape": "very-rounded"})
        self.assertTrue(theme["id"].startswith("custom-"))
        self.lib.save_settings({"theme": theme["id"]})
        self.assertEqual(self.lib.settings()["theme"], theme["id"])
        exported = self.lib.export_custom_theme(theme["id"])
        path = self.paths.decode(exported["path"])
        self.assertTrue(path and path.is_file())
        imported = self.lib.import_custom_theme(str(path))
        self.assertNotEqual(imported["id"], theme["id"])
        with self.assertRaises(ValueError):
            self.lib.save_custom_theme({"id": "dark", "name": "No"})
        self.lib.delete_custom_theme(theme["id"])
        self.assertEqual(self.lib.settings()["theme"], "dark")

    def test_ai_is_bounded_offline_and_searches_local_library(self):
        g = self.add_pc_game("Carreras Lunar")
        self.lib.update_game(g["id"], {"genre": "Carreras", "favorite": True})
        fav = self.lib.ask_ai("muéstrame mis favoritos")
        self.assertEqual(fav["kind"], "games")
        self.assertTrue(any(x["id"] == g["id"] for x in fav["items"]))
        found = self.lib.ask_ai("busca carreras lunar")
        self.assertTrue(any(x["id"] == g["id"] for x in found["items"]))
        safety = self.lib.ask_ai("borra ORBIT y reescribe el código")
        self.assertEqual(safety["kind"], "safety")

    def test_ai_can_be_disabled_per_profile(self):
        self.lib.save_settings({"ai": {"enabled": False, "engine": "offline-integrated"}})
        with self.assertRaises(ValueError):
            self.lib.ask_ai("favoritos")


class TestOrganizationAndMedia(OrbitCase):
    def test_organization_accepts_only_inside_orbit(self):
        dest = self.paths.games / "Mi GameCube"
        settings = self.lib.set_platform_destination("GameCube", str(dest))
        self.assertEqual(settings["organization"]["platform_paths"]["GameCube"], "@launcher/games/Mi GameCube")
        outside = Path(tempfile.gettempdir()) / "orbit-external-games"
        with self.assertRaises(ValueError):
            self.lib.set_platform_destination("GameCube", str(outside))

    def test_invalid_image_signature_is_rejected(self):
        game = self.add_pc_game("Image")
        fake = self.root / "fake.png"; fake.write_text("not png", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.lib.set_game_media(game["id"], "cover", str(fake))

    def test_cover_search_without_api_key_is_explicitly_unconfigured(self):
        game = self.add_pc_game("CoverSearch")
        result = self.lib.search_game_art(game["id"], "grid")
        self.assertFalse(result.get("configured", True))


class TestSavesAndRecovery(OrbitCase):
    def test_save_backup_and_restore(self):
        game = self.add_pc_game("SaveGame", save=True)
        source = self.paths.decode(game["save_path"])
        backup = self.lib.backup_game_saves(game["id"], "manual-test")
        self.assertTrue(backup.get("backup_id"))
        (source / "slot.dat").write_text("CHANGED", encoding="utf-8")
        self.lib.restore_game_backup(game["id"], backup["backup_id"], confirmed=True)
        self.assertEqual((source / "slot.dat").read_text(encoding="utf-8"), "SAVE-A")

    def test_restore_requires_confirmation(self):
        game = self.add_pc_game("SafeRestore", save=True)
        backup = self.lib.backup_game_saves(game["id"])
        with self.assertRaises(ValueError):
            self.lib.restore_game_backup(game["id"], backup["backup_id"], confirmed=False)

    def test_recovery_point_restores_library_metadata(self):
        game = self.add_pc_game("Recovery")
        point = self.lib.create_recovery_point("before-change")
        self.lib.update_game(game["id"], {"name": "Changed"})
        self.lib.restore_recovery_point(point["path"], confirmed=True)
        restored = next(g for g in self.lib.games() if g.get("id") == game["id"])
        self.assertEqual(restored["name"], "Recovery")


class TestOrbitPack(OrbitCase):
    def _make_source_pack(self):
        emudir = self.paths.emulators / "Dolphin"
        emudir.mkdir(parents=True, exist_ok=True)
        exe = emudir / "Dolphin.exe"; exe.write_bytes(b"MZ-emulator")
        emu = self.lib.add_emulator({"name": "Dolphin", "platform": "GameCube", "executable": str(exe)})
        romdir = self.paths.games / "messy-source"; romdir.mkdir(parents=True, exist_ok=True)
        rom = romdir / "Zelda.iso"; rom.write_bytes(b"GAME-DATA")
        game = self.lib.add_game({"name": "Zelda Test", "platform": "GameCube", "path": str(rom), "emulator_id": emu["id"], "region": "EUR", "revision": "1.0"})
        portable = self.lib.saves.portable_target(game, "default"); portable.mkdir(parents=True); (portable / "slot.sav").write_text("SOURCE-SAVE", encoding="utf-8")
        result = self.lib.create_orbitpack([game["id"]], include_game_files=True, include_emulators=True, include_media=False, include_saves=True, name="Pack Test")
        return game, emu, self.paths.decode(result["path"])

    def test_pack_v2_integrity_receiver_layout_and_saves(self):
        game, emu, pack = self._make_source_pack()
        inspected = self.lib.inspect_orbitpack(str(pack))
        self.assertEqual(inspected["version"], 2)
        self.assertTrue(inspected["options"]["include_saves"])

        with tempfile.TemporaryDirectory(prefix="orbit-receiver-") as td:
            root2 = Path(td); (root2 / "VERSION").write_text("0.5.0", encoding="utf-8")
            paths2 = PortablePaths(root2); lib2 = LibraryService(paths2, JsonStore(paths2))
            custom = paths2.games / "Cristina" / "GameCube"
            lib2.set_platform_destination("GameCube", str(custom))
            result = lib2.import_orbitpack(str(pack), "skip")
            self.assertEqual(result["added"], 1)
            self.assertEqual(result["saves"], 1)
            imported = [g for g in lib2.games() if not g.get("demo")][0]
            imported_path = paths2.decode(imported["path"])
            self.assertEqual(imported_path.parent, custom.resolve())
            self.assertFalse("messy-source" in str(imported_path))
            self.assertEqual(imported["region"], "EUR")
            self.assertTrue(lib2.saves.portable_target(imported, "default").joinpath("slot.sav").exists())
            imported_emu = next(e for e in lib2.emulators() if e["id"] == imported["emulator_id"])
            self.assertTrue(paths2.decode(imported_emu["executable"]).exists())

    def test_pack_reuses_existing_emulator_and_does_not_overwrite_save(self):
        game, emu, pack = self._make_source_pack()
        with tempfile.TemporaryDirectory(prefix="orbit-receiver-") as td:
            root2 = Path(td); (root2 / "VERSION").write_text("0.5.0", encoding="utf-8")
            paths2 = PortablePaths(root2); lib2 = LibraryService(paths2, JsonStore(paths2))
            existing_dir = paths2.emulators / "ExistingDolphin"; existing_dir.mkdir(parents=True); exe=existing_dir/"Dolphin.exe"; exe.write_bytes(b"existing")
            existing = lib2.add_emulator({"name":"Dolphin","platform":"GameCube","executable":str(exe)})
            first = lib2.import_orbitpack(str(pack), "skip")
            imported = [g for g in lib2.games() if not g.get("demo")][0]
            self.assertEqual(imported["emulator_id"], existing["id"])
            save_target = lib2.saves.portable_target(imported, "default")
            (save_target / "slot.sav").write_text("RECEIVER-SAVE", encoding="utf-8")
            second = lib2.import_orbitpack(str(pack), "replace-metadata")
            self.assertEqual((save_target / "slot.sav").read_text(encoding="utf-8"), "RECEIVER-SAVE")
            self.assertGreaterEqual(second["saves"], 1)
            siblings = list(save_target.parent.glob(save_target.name + "-imported-*"))
            self.assertTrue(siblings)
            self.assertEqual(len([e for e in lib2.emulators() if e["name"]=="Dolphin"]), 1)

    def test_pack_detects_tampered_payload(self):
        game, emu, pack = self._make_source_pack()
        tampered = self.root / "exports" / "Tampered.orbitpack"
        shutil.copy2(pack, tampered)
        # Rewrite one payload member without updating checksums.
        with zipfile.ZipFile(tampered, "a") as z:
            member = next(n for n in z.namelist() if n.startswith("payload/games/"))
            z.writestr(member, b"TAMPERED")
        with self.assertRaises(ValueError):
            self.lib.inspect_orbitpack(str(tampered))

    def test_pack_rejects_path_traversal(self):
        bad = self.root / "bad.orbitpack"
        manifest = {"format":"ORBITPACK","version":2,"checksums":{}}
        raw = json.dumps(manifest).encode()
        with zipfile.ZipFile(bad,"w") as z:
            z.writestr("../evil.txt", "x")
            z.writestr("manifest.json", raw)
            z.writestr("manifest.sha256", hashlib.sha256(raw).hexdigest())
        with self.assertRaises(ValueError):
            OrbitPackService(self.paths).inspect(bad)

    def test_failed_pack_import_rolls_back_metadata_and_files(self):
        payload1=self.root/"one.iso"; payload1.write_bytes(b"ONE")
        payload2=self.root/"two.iso"; payload2.write_bytes(b"TWO")
        manifest={
            "games":[
                {"id":"one","source_id":"one","name":"One","platform":"GameCube","pack_game_file":"payload/games/one.iso","original_filename":"one.iso","pack_media":{}},
                {"id":"two","source_id":"two","name":"Two","platform":"GameCube","pack_game_file":"payload/games/two.iso","original_filename":"two.iso","pack_media":{"cover":"../outside.png"}},
            ],
            "emulators":[],"options":{"include_game_files":True},"layout_policy":"receiver-decides"
        }
        pack=OrbitPackService(self.paths).create(manifest,[(payload1,"payload/games/one.iso"),(payload2,"payload/games/two.iso")],name="rollback")
        before=[g.get("id") for g in self.real_games()]
        with self.assertRaises(ValueError):
            self.lib.import_orbitpack(str(pack),"keep-both")
        self.assertEqual([g.get("id") for g in self.real_games()],before)
        dest=self.paths.games/"GameCube"
        self.assertFalse((dest/"one.iso").exists())
        self.assertFalse((dest/"two.iso").exists())

    def test_pack_accepts_v1_manifest_for_compatibility(self):
        v1 = self.root / "legacy.orbitpack"
        manifest = {"format":"ORBITPACK","version":1,"checksums":{},"games":[],"emulators":[]}
        raw = json.dumps(manifest).encode()
        with zipfile.ZipFile(v1,"w") as z:
            z.writestr("manifest.json", raw); z.writestr("manifest.sha256", hashlib.sha256(raw).hexdigest())
        info = OrbitPackService(self.paths).inspect(v1)
        self.assertEqual(info["manifest"]["version"], 1)


class TestHttpAndStatic(OrbitCase):
    def _request(self, base, path, method="GET", payload=None, host=None):
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if host is not None:
            headers["Host"] = host
        req = urllib.request.Request(base + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read().decode("utf-8")) if "application/json" in (r.headers.get("Content-Type") or "") else r.read()
        except urllib.error.HTTPError as e:
            raw=e.read()
            try: body=json.loads(raw.decode("utf-8"))
            except Exception: body=raw
            return e.code, body

    def test_http_new_endpoints_profiles_and_retired_admin(self):
        server = LauncherServer(self.root)
        host, port = server.start()
        base=f"http://{host}:{port}"
        try:
            status, state = self._request(base,"/api/state")
            self.assertEqual(status,200); self.assertEqual(state["version"],"0.5.0")
            self.assertIn("custom_themes",state); self.assertNotIn("authorization",state)
            status, prof = self._request(base,"/api/profiles","POST",{"name":"HTTP Profile"})
            self.assertEqual(status,201); self.assertEqual(prof["profile"]["name"],"HTTP Profile")
            status, ready = self._request(base,"/api/readiness")
            self.assertEqual(status,200); self.assertTrue(ready["ok"])
            status, ai = self._request(base,"/api/ai/ask","POST",{"query":"favoritos"})
            self.assertEqual(status,200); self.assertTrue(ai["ok"])
            status, retired = self._request(base,"/api/authorization")
            self.assertEqual(status,404)
        finally:
            server.stop()

    def test_http_host_guard_and_content_type(self):
        server=LauncherServer(self.root); host,port=server.start(); base=f"http://{host}:{port}"
        try:
            status,_=self._request(base,"/api/ping",host="evil.example")
            self.assertEqual(status,421)
            req=urllib.request.Request(base+"/api/settings",data=b"{}",method="POST")
            try:
                urllib.request.urlopen(req,timeout=5); self.fail("Expected HTTP error")
            except urllib.error.HTTPError as e:
                self.assertEqual(e.code,400)
        finally: server.stop()

    def test_http_orbitpack_include_saves_reaches_backend(self):
        game=self.add_pc_game("HttpPack")
        portable=self.lib.saves.portable_target(game,"default");portable.mkdir(parents=True);(portable/"slot").write_text("x")
        server=LauncherServer(self.root);host,port=server.start();base=f"http://{host}:{port}"
        try:
            status,body=self._request(base,"/api/orbitpack/export","POST",{"game_ids":[game["id"]],"include_game_files":True,"include_saves":True,"include_media":False,"include_emulators":False,"name":"HTTP Saves"})
            self.assertEqual(status,200)
            pack=self.paths.decode(body["result"]["path"])
            info=OrbitPackService(self.paths).inspect(pack)
            self.assertTrue(info["manifest"]["options"]["include_saves"])
            self.assertTrue(info["manifest"]["games"][0]["pack_save"])
        finally: server.stop()

    def test_static_contains_core_and_new_functions_without_admin_ui(self):
        js=(Path(__file__).resolve().parents[1]/"app/static/app.js").read_text(encoding="utf-8")
        html=(Path(__file__).resolve().parents[1]/"app/static/index.html").read_text(encoding="utf-8")
        for fn in ["setupWizard","emulatorCenterModal","controllerMappingModal","orbitpackImportStart","readinessModal","orbitAiModal","themeEditorModal","detailModal"]:
            self.assertIn(f"function {fn}",js)
        self.assertNotIn("browseNative('file')",js)
        self.assertNotIn("authorizationGate",html)
        self.assertNotIn("privacyStatus",html)


class TestSafeModeAndCleanup(OrbitCase):
    def test_safe_mode_overrides_visual_settings_only(self):
        self.lib.save_settings({"theme":"light","interface_mode":"cinematic","start_view":"home"})
        old=os.environ.get("ORBIT_SAFE_MODE")
        os.environ["ORBIT_SAFE_MODE"]="1"
        server=LauncherServer(self.root)
        host,port=server.start(); base=f"http://{host}:{port}"
        try:
            with urllib.request.urlopen(base+"/api/state",timeout=5) as r: state=json.loads(r.read())
            self.assertTrue(state["safe_mode"]);self.assertEqual(state["settings"]["theme"],"dark");self.assertEqual(state["settings"]["start_view"],"settings")
            # Stored setting was not mutated.
            self.assertEqual(server.library.settings()["theme"],"light")
        finally:
            server.stop()
            if old is None: os.environ.pop("ORBIT_SAFE_MODE",None)
            else: os.environ["ORBIT_SAFE_MODE"]=old

    def test_no_admin_modules_are_shipped(self):
        source=Path(__file__).resolve().parents[1]
        self.assertFalse((source/"app/services/authorization.py").exists())
        self.assertFalse((source/"app/services/privacy.py").exists())
        self.assertFalse((source/"app/services/signing.py").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
