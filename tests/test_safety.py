from __future__ import annotations

import logging
import tempfile
import unittest
from pathlib import Path

import game_scanner
from artwork_manager import ARTWORK_DOWNLOAD_HEADERS, SteamGridDBClient, cleanup_downloaded_artwork, download_artwork_for_shortcut
from config import ARTWORK_REQUESTS
from config import _parse_scan_drives
from fixer import diagnose_shortcuts
from game_scanner import discover_games
from shortcut_builder import build_shortcut, get_unsigned_id
from steam_paths import list_steam_users
from vdf_manager import backup_shortcuts, load_shortcuts, reindex_shortcuts, verify_persisted_shortcuts, write_shortcuts


class SteamPathSafetyTests(unittest.TestCase):
    def test_list_steam_users_does_not_create_missing_config_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            steam_root = Path(temp_dir)
            user_dir = steam_root / "userdata" / "123456"
            user_dir.mkdir(parents=True)

            users = list_steam_users(steam_root)

            self.assertEqual(len(users), 1)
            self.assertFalse((user_dir / "config").exists())
            self.assertEqual(users[0].shortcuts_path, user_dir / "config" / "shortcuts.vdf")


class ConfigParsingTests(unittest.TestCase):
    def test_parse_scan_drives_normalizes_and_deduplicates_entries(self) -> None:
        drives = _parse_scan_drives('C:, c:\\, "D:/", E:\\')

        self.assertEqual(drives, [Path("C:/"), Path("D:/"), Path("E:/")])


class ArtworkCleanupTests(unittest.TestCase):
    def test_cleanup_downloaded_artwork_removes_existing_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            target = Path(temp_dir) / "grid" / "123_icon.png"
            target.parent.mkdir(parents=True)
            target.write_bytes(b"data")

            cleanup_downloaded_artwork([target], logging.getLogger("test"))

            self.assertFalse(target.exists())

    def test_authorized_get_falls_back_to_plain_download_headers_after_401(self) -> None:
        class FakeResponse:
            def __init__(self, status_code: int) -> None:
                self.status_code = status_code

        class FakeSession:
            def __init__(self) -> None:
                self.calls: list[dict | None] = []

            def get(self, url: str, timeout: int, headers: dict | None = None):
                self.calls.append(headers)
                return FakeResponse(401)

        class FakeRequests:
            def __init__(self) -> None:
                self.calls: list[dict | None] = []

            def get(self, url: str, timeout: int, headers: dict | None = None):
                self.calls.append(headers)
                return FakeResponse(200)

        fake_requests = FakeRequests()
        fake_session = FakeSession()

        client = SteamGridDBClient.__new__(SteamGridDBClient)
        setattr(client, "_requests", fake_requests)
        client.api_key = "secret"
        client.logger = logging.getLogger("test")
        setattr(client, "session", fake_session)

        response = client._authorized_get("https://example.com/test.png", timeout=30)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(fake_requests.calls, [ARTWORK_DOWNLOAD_HEADERS])


class ShortcutBuilderTests(unittest.TestCase):
    def test_build_shortcut_quotes_exe_and_startdir(self) -> None:
        shortcut = build_shortcut("Example Game", r"C:\Games\Example\game.exe")

        self.assertEqual(shortcut["Exe"], '"C:\\Games\\Example\\game.exe"')
        self.assertEqual(shortcut["StartDir"], '"C:\\Games\\Example\\"')


class GameScannerTests(unittest.TestCase):
    def test_discover_games_skips_existing_app_name_matches(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            game_dir = root / "LEGO The Incredibles"
            game_dir.mkdir(parents=True)
            (game_dir / "LEGO The Incredibles_DX11.exe").write_bytes(b"stub")

            original_known_dirs = game_scanner.KNOWN_GAME_DIRS
            original_target_drives = game_scanner.TARGET_DRIVES
            try:
                game_scanner.KNOWN_GAME_DIRS = [root]
                game_scanner.TARGET_DRIVES = []
                results = discover_games(
                    existing_exe_paths=set(),
                    steam_common_dirs=[],
                    logger=logging.getLogger("test"),
                    existing_app_names={"lego the incredibles"},
                )
            finally:
                game_scanner.KNOWN_GAME_DIRS = original_known_dirs
                game_scanner.TARGET_DRIVES = original_target_drives

            self.assertEqual(results, [])


class FixerTests(unittest.TestCase):
    def test_diagnose_shortcuts_flags_unfixable_wildcard_exe(self) -> None:
        shortcut = build_shortcut("Wildcard Game", r"C:\Games\Wildcard\game.exe")
        shortcut["Exe"] = "!(*uninst*|*launcher*)"

        issues = diagnose_shortcuts({"0": shortcut})

        self.assertIn("0", issues)
        self.assertTrue(any("cannot be safely fixed automatically" in issue for issue in issues["0"]))


class VdfWorkflowTests(unittest.TestCase):
    def test_write_shortcuts_round_trip_persists_expected_data(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            shortcuts_path = Path(temp_dir) / "shortcuts.vdf"
            data = {
                "shortcuts": reindex_shortcuts(
                    [
                        build_shortcut("Example Game", r"C:\Games\Example\game.exe"),
                    ]
                )
            }

            write_shortcuts(shortcuts_path, data)
            verified, _ = verify_persisted_shortcuts(shortcuts_path, data)

            self.assertTrue(verified)
            self.assertEqual(load_shortcuts(shortcuts_path), data)

    def test_backup_shortcuts_creates_empty_backup_when_source_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            shortcuts_path = Path(temp_dir) / "shortcuts.vdf"

            backup_path = backup_shortcuts(shortcuts_path)

            self.assertTrue(backup_path.exists())
            self.assertEqual(load_shortcuts(backup_path), {"shortcuts": {}})


class ArtworkWorkflowTests(unittest.TestCase):
    def test_download_artwork_for_shortcut_uses_existing_files_without_network(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            grid_dir = Path(temp_dir)
            shortcut = build_shortcut("Existing Art Game", r"C:\Games\Art\game.exe")
            unsigned_appid = get_unsigned_id(int(shortcut["appid"]))

            for art_type, request in ARTWORK_REQUESTS.items():
                filename = request["filename"].format(appid=unsigned_appid, ext=".png")
                (grid_dir / filename).write_bytes(b"art")

            dummy_client = SteamGridDBClient.__new__(SteamGridDBClient)
            result = download_artwork_for_shortcut(shortcut, grid_dir, dummy_client, logging.getLogger("test"))

            self.assertEqual(result.downloaded, 0)
            self.assertEqual(result.failures, 0)
            self.assertEqual(result.skipped, len(ARTWORK_REQUESTS))
            self.assertTrue(str(shortcut.get("icon", "")).endswith("_icon.png"))


if __name__ == "__main__":
    unittest.main()
