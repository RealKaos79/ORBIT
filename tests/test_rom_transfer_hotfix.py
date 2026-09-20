"""Regression tests for physical ROM transfer; no existing ORBIT feature is replaced."""
from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from app.core.paths import PortablePaths
from app.core.storage import JsonStore
from app.services.library import LibraryService
from app.services.orbitpack import sha256_file
from app.server import LauncherServer


class RomTransferHotfix(unittest.TestCase):
    def setUp(self):
        self.source_temp = tempfile.TemporaryDirectory(prefix='orbit-rom-source-')
        self.receiver_temp = tempfile.TemporaryDirectory(prefix='orbit-rom-target-')
        self.src = Path(self.source_temp.name)
        self.dst = Path(self.receiver_temp.name)
        for root in (self.src, self.dst):
            (root / 'VERSION').write_text('0.6.2\n', encoding='utf-8')
        self.sp = PortablePaths(self.src)
        self.dp = PortablePaths(self.dst)
        self.s = LibraryService(self.sp, JsonStore(self.sp))
        self.d = LibraryService(self.dp, JsonStore(self.dp))

    def tearDown(self):
        self.source_temp.cleanup()
        self.receiver_temp.cleanup()

    def game(self, name='Juego', data=b'ROM-content'):
        rom = self.sp.games / 'folder' / f'{name}.iso'
        rom.parent.mkdir(parents=True, exist_ok=True)
        rom.write_bytes(data)
        return self.s.add_game({'name': name, 'platform': 'GameCube', 'path': str(rom)}), rom

    def pack(self, **options):
        options.setdefault('include_emulators', False)
        options.setdefault('include_media', False)
        return self.sp.decode(self.s.create_orbitpack(**options)['path'])

    def real_games(self, lib):
        return [g for g in lib.games() if not g.get('demo')]

    def test_default_export_contains_real_rom_bytes_not_just_metadata(self):
        g, rom = self.game(data=b'ACTUAL-ROM-123')
        pack = self.pack()
        with zipfile.ZipFile(pack) as archive:
            manifest = json.loads(archive.read('manifest.json'))
            self.assertTrue(manifest['options']['include_game_files'])
            member = manifest['games'][0]['pack_game_file']
            self.assertEqual(archive.read(member), rom.read_bytes())
        self.assertEqual(self.s.inspect_orbitpack(str(pack))['rom_files'], 1)

    def test_default_import_places_rom_in_existing_automatic_folder(self):
        _, original = self.game(data=b'BYTE-FOR-BYTE-ROM')
        custom = self.dp.games / 'my-configured-folder' / 'GameCube'
        self.d.set_platform_destination('GameCube', str(custom))
        result = self.d.import_orbitpack(str(self.pack()), components=['games'])
        self.assertEqual(result['added'], 1)
        self.assertEqual(result['roms'], 1)
        imported = self.real_games(self.d)[0]
        target = self.dp.decode(imported['path'])
        self.assertEqual(target.parent, custom.resolve())
        self.assertEqual(target.read_bytes(), original.read_bytes())
        reopened = LibraryService(self.dp, JsonStore(self.dp))
        self.assertEqual(self.dp.decode(self.real_games(reopened)[0]['path']).read_bytes(), original.read_bytes())

    def test_selected_rom_only_does_not_export_unselected_game(self):
        chosen, chosen_rom = self.game('Chosen')
        self.game('Excluded')
        pack = self.pack(game_ids=[chosen['id']])
        with zipfile.ZipFile(pack) as archive:
            manifest = json.loads(archive.read('manifest.json'))
            self.assertEqual([g['name'] for g in manifest['games']], ['Chosen'])
            self.assertEqual(len([n for n in archive.namelist() if n.startswith('payload/games/')]), 1)
            self.assertEqual(archive.read(manifest['games'][0]['pack_game_file']), chosen_rom.read_bytes())
        self.d.import_orbitpack(str(pack), components=['games'])
        self.assertEqual([g['name'] for g in self.real_games(self.d)], ['Chosen'])

    def test_missing_source_rom_fails_export_no_misleading_archive(self):
        game, rom = self.game('Missing')
        rom.unlink()
        with self.assertRaisesRegex(ValueError, 'No se puede exportar la ROM'):
            self.pack()
        self.assertEqual(list(self.sp.exports.glob('*.orbitpack')), [])

    def test_missing_source_rom_does_not_block_explicit_metadata_only(self):
        _, rom = self.game('OldPack')
        rom.unlink()
        pack = self.pack(include_game_files=False)
        inspection = self.s.inspect_orbitpack(str(pack))
        self.assertEqual(inspection['games'], 1)
        self.assertEqual(inspection['rom_files'], 0)
        output = self.d.import_orbitpack(str(pack), components=['games'])
        self.assertEqual(output['metadata_only'], 1)
        self.assertEqual(output['roms'], 0)

    def test_old_metadata_only_pack_can_be_repaired_with_complete_pack(self):
        _, rom = self.game('NeedsRepair', b'RECOVERED-ROM')
        old_pack = self.pack(include_game_files=False, name='old')
        self.d.import_orbitpack(str(old_pack), components=['games'])
        before = self.real_games(self.d)[0]
        old_id = before['id']
        self.assertFalse(self.dp.decode(before['path']).is_file())
        complete_pack = self.pack(name='complete')
        out = self.d.import_orbitpack(str(complete_pack), components=['games'], conflict='skip')
        self.assertEqual(out['roms'], 1)
        games = self.real_games(self.d)
        self.assertEqual(len(games), 1)
        self.assertEqual(games[0]['id'], old_id)
        self.assertEqual(self.dp.decode(games[0]['path']).read_bytes(), rom.read_bytes())

    def test_import_twice_does_not_duplicate_rom_or_game(self):
        self.game('OnlyOnce')
        archive = self.pack()
        first = self.d.import_orbitpack(str(archive), components=['games'])
        second = self.d.import_orbitpack(str(archive), components=['games'])
        self.assertEqual((first['roms'], second['roms']), (1, 0))
        self.assertEqual(len(self.real_games(self.d)), 1)
        self.assertEqual(len(list(self.dp.games.rglob('*.iso'))), 1)

    def test_same_existing_rom_bytes_are_reused_without_overwrite(self):
        _, rom = self.game('Identical', b'IDENTICAL-ROM')
        existing_dir = self.dp.games / 'GameCube'
        existing_dir.mkdir(parents=True, exist_ok=True)
        preexisting = existing_dir / 'Identical.iso'
        preexisting.write_bytes(rom.read_bytes())
        output = self.d.import_orbitpack(str(self.pack()), components=['games'])
        self.assertEqual(output['roms'], 0)
        self.assertEqual(self.dp.decode(self.real_games(self.d)[0]['path']), preexisting)
        self.assertEqual(len(list(self.dp.games.rglob('*.iso'))), 1)

    def test_different_existing_rom_is_not_overwritten(self):
        self.game('Collision', b'NEW-ROM')
        existing_dir = self.dp.games / 'GameCube'
        existing_dir.mkdir(parents=True, exist_ok=True)
        existing = existing_dir / 'Collision.iso'
        existing.write_bytes(b'KEEP-ME')
        output = self.d.import_orbitpack(str(self.pack()), components=['games'])
        self.assertEqual(output['roms'], 1)
        self.assertEqual(existing.read_bytes(), b'KEEP-ME')
        imported = self.dp.decode(self.real_games(self.d)[0]['path'])
        self.assertNotEqual(imported, existing)
        self.assertEqual(imported.read_bytes(), b'NEW-ROM')

    def test_import_only_configuration_does_not_transfer_rom(self):
        self.game('NotSelected')
        pack = self.pack(include_configuration=True)
        self.d.import_orbitpack(str(pack), components=['configuration'])
        self.assertEqual(self.real_games(self.d), [])
        self.assertEqual(list(self.dp.games.rglob('*.iso')), [])

    def test_existing_emulator_association_preserved_after_rom_import(self):
        game, _ = self.game('WithEmulator')
        source_exe = self.sp.emulators / 'dolphin' / 'dolphin.exe'
        source_exe.parent.mkdir(parents=True, exist_ok=True)
        source_exe.write_bytes(b'EmulatorBinary')
        emu = self.s.add_emulator({'name': 'Dolphin', 'platform': 'GameCube', 'executable': str(source_exe)})
        self.s.update_game(game['id'], {'emulator_id': emu['id']})
        target_exe = self.dp.emulators / 'already-installed' / 'dolphin.exe'
        target_exe.parent.mkdir(parents=True, exist_ok=True)
        target_exe.write_bytes(b'PreexistingEmulator')
        existing = self.d.add_emulator({'name': 'Dolphin', 'platform': 'GameCube', 'executable': str(target_exe)})
        self.d.import_orbitpack(str(self.pack()), components=['games'])
        imported = self.real_games(self.d)[0]
        self.assertEqual(imported['emulator_id'], existing['id'])
        self.assertEqual(self.dp.decode(imported['path']).read_bytes(), b'ROM-content')
        self.assertEqual(len(self.d.emulators()), 1)

    def test_corrupt_rom_archive_rejected_without_changing_receiver(self):
        self.game('Integrity')
        pack = self.pack()
        bad = self.sp.exports / 'tampered.orbitpack'
        with zipfile.ZipFile(pack) as old, zipfile.ZipFile(bad, 'w') as new:
            for info in old.infolist():
                content = old.read(info.filename)
                if info.filename.startswith('payload/games/'):
                    content = b'TAMPERED-DATA'
                new.writestr(info, content)
        with self.assertRaisesRegex(ValueError, 'integridad'):
            self.d.import_orbitpack(str(bad), components=['games'])
        self.assertEqual(self.real_games(self.d), [])
        self.assertEqual(list(self.dp.games.rglob('*.iso')), [])

    def test_legacy_metadata_replacement_repairs_missing_rom(self):
        self.game('Replace')
        old_pack = self.pack(include_game_files=False, name='old')
        self.d.import_orbitpack(str(old_pack), components=['games'])
        original_id = self.real_games(self.d)[0]['id']
        full_pack = self.pack(name='new')
        self.d.import_orbitpack(str(full_pack), components=['games'], conflict='replace-metadata')
        self.assertEqual(self.real_games(self.d)[0]['id'], original_id)
        self.assertTrue(self.dp.decode(self.real_games(self.d)[0]['path']).is_file())

    def test_progress_reaches_completion_with_rom_bytes(self):
        self.game('Progress', b'R' * (2 * 1024 * 1024))
        export_events = []
        pack = self.sp.decode(self.s.create_orbitpack(include_emulators=False, include_media=False, progress=export_events.append)['path'])
        import_events = []
        self.d.import_orbitpack(str(pack), components=['games'], progress=import_events.append)
        self.assertTrue(any(e.get('current', '').endswith('.iso') for e in export_events if e.get('current')))
        self.assertTrue(any(e.get('current') == 'Progress.iso' for e in import_events))
        self.assertEqual(import_events[-1]['percent'], 1.0)
        self.assertEqual(import_events[-1]['phase'], 'done')

    def test_api_export_default_includes_rom_even_without_explicit_checkbox_field(self):
        game, rom = self.game('API-default')
        server = LauncherServer(self.src)
        server.library.create_orbitpack = self.s.create_orbitpack
        import threading
        # Exercise the same HTTP handler as the app export button.
        import urllib.request
        host, port = server.start()
        try:
            data = json.dumps({'game_ids': [game['id']], 'include_emulators': False, 'include_media': False}).encode()
            request = urllib.request.Request(f'http://{host}:{port}/api/orbitpack/export', data=data,
                headers={'Content-Type': 'application/json'}, method='POST')
            with urllib.request.urlopen(request, timeout=10) as response:
                result = json.load(response)['result']
            archive = self.sp.decode(result['path'])
            with zipfile.ZipFile(archive) as file:
                manifest = json.loads(file.read('manifest.json'))
                self.assertEqual(file.read(manifest['games'][0]['pack_game_file']), rom.read_bytes())
        finally:
            server.stop()

    def test_frontend_defaults_to_rom_export_but_allows_metadata_only(self):
        js = (Path(__file__).resolve().parents[1] / 'app/static/app.js').read_text(encoding='utf-8')
        self.assertIn('name="include_game_files" checked', js)
        self.assertIn('name="include_game_files"', js)
        self.assertIn('faltan ROMs en este paquete', js)

    def test_launch_uses_imported_rom_and_existing_emulator(self):
        """Actually launch a local emulator stub, not only inspect the DB."""
        if os.name == 'nt':
            self.skipTest('POSIX fixture executable; Windows native launcher requires Windows')
        game, rom = self.game('Playable', b'LAUNCHABLE-ROM')
        source_exe = self.sp.emulators / 'stub' / 'launcher'
        source_exe.parent.mkdir(parents=True, exist_ok=True)
        source_exe.write_bytes(b'#!/bin/sh\nexit 0\n')
        source_exe.chmod(0o755)
        emulator = self.s.add_emulator({'name':'Stub','platform':'GameCube','executable':str(source_exe)})
        self.s.update_game(game['id'], {'emulator_id': emulator['id']})
        result_file = self.dp.root / 'launched-rom-path.txt'
        target_exe = self.dp.emulators / 'stub-existing' / 'launcher'
        target_exe.parent.mkdir(parents=True, exist_ok=True)
        target_exe.write_text(f'#!/bin/sh\nprintf "%s" "$1" > "{result_file}"\n', encoding='utf-8')
        target_exe.chmod(0o755)
        receiver_emu = self.d.add_emulator({'name':'Stub','platform':'GameCube','executable':str(target_exe)})
        pack = self.pack()
        self.d.import_orbitpack(str(pack), components=['games'])
        imported = self.real_games(self.d)[0]
        self.assertEqual(imported['emulator_id'], receiver_emu['id'])
        self.d.launch(imported['id'])
        for _ in range(100):
            if result_file.exists():
                break
            time.sleep(.01)
        self.assertTrue(result_file.exists(), 'La ejecución no invocó el emulador')
        path = Path(result_file.read_text(encoding='utf-8'))
        self.assertEqual(path.read_bytes(), rom.read_bytes())

    def test_failure_after_first_rom_restores_files_and_library(self):
        self.game('First')
        self.game('Second')
        original_pack = self.pack()
        broken = self.sp.exports / 'bad-reference.orbitpack'
        # A newly signed but internally inconsistent manifest is rejected by
        # the apply step AFTER the first physical ROM was placed.
        import hashlib
        with zipfile.ZipFile(original_pack) as old, zipfile.ZipFile(broken, 'w') as new:
            manifest = json.loads(old.read('manifest.json'))
            manifest['games'][1]['pack_game_file'] = 'payload/games/nonexistent.iso'
            raw = json.dumps(manifest, ensure_ascii=False, indent=2).encode()
            for info in old.infolist():
                if info.filename == 'manifest.json':
                    new.writestr(info, raw)
                elif info.filename == 'manifest.sha256':
                    new.writestr(info, hashlib.sha256(raw).hexdigest())
                else:
                    new.writestr(info, old.read(info.filename))
        before = [g['id'] for g in self.real_games(self.d)]
        with self.assertRaisesRegex(ValueError, 'Falta la ROM'):
            self.d.import_orbitpack(str(broken), components=['games'])
        self.assertEqual([g['id'] for g in self.real_games(self.d)], before)
        self.assertEqual(list(self.dp.games.rglob('*.iso')), [])

    def test_launch_uri_pack_does_not_report_missing_rom(self):
        self.s.add_game({'name': 'External', 'platform': 'PC',
                         'path': str(self.sp.games / 'uninstalled.exe'),
                         'launch_uri': 'steam://rungameid/12345'})
        archive = self.pack()
        info = self.s.inspect_orbitpack(str(archive))
        self.assertEqual(info['rom_missing'], 0)
        self.assertEqual(info['rom_files'], 0)

    def test_pack_service_rejects_rom_disappearing_after_manifest_preflight(self):
        from app.services.orbitpack import OrbitPackService
        missing = self.sp.games / 'deleted.iso'
        with self.assertRaisesRegex(ValueError, 'dejó de estar disponible'):
            OrbitPackService(self.sp).create({}, [(missing, 'payload/games/GameCube/deleted.iso')])


if __name__ == '__main__':
    unittest.main()
