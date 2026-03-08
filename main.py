from __future__ import annotations

import sys
import shutil
import importlib.util
from pathlib import Path

from artwork_manager import download_artwork_for_shortcuts, resolve_api_key
from config import LOG_FILE_NAME, MIN_PYTHON
from fixer import fix_shortcuts_interactively
from game_scanner import DiscoveredGame, discover_games
from logger_setup import setup_logging
from shortcut_builder import build_shortcut, normalized_exe_identity
from steam_paths import (
    SteamUser,
    find_steam_install_path,
    get_steam_common_directories,
    is_steam_running,
    list_steam_users,
)
from vdf_manager import (
    add_one_and_verify_test,
    backup_shortcuts,
    collect_existing_exe_paths,
    load_shortcuts,
    reindex_shortcuts,
    round_trip_integrity_test,
    verify_field_quoting,
    verify_persisted_shortcuts,
    write_shortcuts,
)


def check_python_version() -> None:
    if sys.version_info < MIN_PYTHON:
        required = ".".join(str(part) for part in MIN_PYTHON)
        print(f"Python {required}+ is required.")
        raise SystemExit(1)


def check_dependencies() -> None:
    missing = [name for name in ("vdf", "requests") if importlib.util.find_spec(name) is None]

    if missing:
        print(f"Missing required packages: {', '.join(missing)}")
        print(f"Install them with: pip install {' '.join(missing)}")
        raise SystemExit(1)


def prompt_for_users(users: list[SteamUser]) -> list[SteamUser]:
    if not users:
        print("No Steam userdata directories were found. Open Steam once and sign in first.")
        raise SystemExit(1)
    if len(users) == 1:
        return users

    print("Steam user IDs found:")
    for index, user in enumerate(users, start=1):
        print(f"  [{index}] {user.user_id} (last modified {user.last_modified:%Y-%m-%d %H:%M:%S})")
    print("  [a] All users")

    while True:
        choice = input("Choose a user or 'a' for all [1]: ").strip().lower() or "1"
        if choice == "a":
            return users
        if choice.isdigit() and 1 <= int(choice) <= len(users):
            return [users[int(choice) - 1]]
        print("Please enter a valid number or 'a'.")


def format_user_label(selected_users: list[SteamUser]) -> str:
    if len(selected_users) == 1:
        return selected_users[0].user_id
    return f"all ({', '.join(user.user_id for user in selected_users)})"


def load_existing_sets(users: list[SteamUser]) -> list[set[str]]:
    return [collect_existing_exe_paths(load_shortcuts(user.shortcuts_path)) for user in users]


def intersection_of_sets(values: list[set[str]]) -> set[str]:
    if not values:
        return set()
    result = set(values[0])
    for value in values[1:]:
        result &= value
    return result


def print_menu(steam_path: Path, selected_users: list[SteamUser]) -> None:
    counts = [len(load_shortcuts(user.shortcuts_path).get("shortcuts", {})) for user in selected_users]
    shortcut_display = str(counts[0]) if len(selected_users) == 1 else f"{sum(counts)} total across {len(selected_users)} users"

    print("\nSteam Non-Steam Game Manager")
    print("=" * 31)
    print(f"Steam path:  {steam_path}")
    print(f"User ID:     {format_user_label(selected_users)}")
    print(f"Shortcuts:   {shortcut_display}")
    print()
    print("[1] Scan for broken entries and fix them")
    print("[2] Scan drives for new games to add")
    print("[3] Download artwork for all shortcuts")
    print("[4] Full run (fix -> add -> artwork)")
    print("[5] List all current non-Steam shortcuts")
    print("[0] Exit")


def ensure_ready_to_write(shortcuts_path: Path, logger) -> bool:
    if is_steam_running():
        print("Steam is running. Close Steam completely before writing shortcuts.vdf.")
        logger.error("Refused to write because Steam is running")
        return False

    round_trip_ok, round_trip_message = round_trip_integrity_test(shortcuts_path)
    logger.info(round_trip_message)
    if not round_trip_ok:
        print(round_trip_message)
        return False

    add_one_ok, add_one_message = add_one_and_verify_test(shortcuts_path)
    logger.info(add_one_message)
    if not add_one_ok:
        print(add_one_message)
        return False

    for warning in verify_field_quoting(load_shortcuts(shortcuts_path)):
        logger.warning(warning)

    return True


def write_user_shortcuts(user: SteamUser, shortcuts_map: dict[str, dict], logger) -> bool:
    data = {"shortcuts": reindex_shortcuts(shortcuts_map)}
    if not ensure_ready_to_write(user.shortcuts_path, logger):
        return False

    backup_path: Path | None = None
    try:
        backup_path = backup_shortcuts(user.shortcuts_path)
    except OSError as error:
        logger.error("Failed to back up %s: %s", user.shortcuts_path, error)
        print(f"Backup failed for {user.user_id}: {error}")
        return False

    logger.info("Created backup at %s", backup_path)
    write_shortcuts(user.shortcuts_path, data)
    verified, message = verify_persisted_shortcuts(user.shortcuts_path, data)
    logger.info(message)
    if not verified:
        if backup_path is not None and backup_path.exists():
            shutil.copy2(backup_path, user.shortcuts_path)
            logger.error("Restored %s from backup after verification failure", user.shortcuts_path)
        print(message)
        return False
    return True


def list_shortcuts(selected_users: list[SteamUser]) -> None:
    for user in selected_users:
        print(f"\nUser {user.user_id}")
        shortcuts = load_shortcuts(user.shortcuts_path).get("shortcuts", {})
        if not shortcuts:
            print("  (no non-Steam shortcuts)")
            continue
        for index, shortcut in sorted(shortcuts.items(), key=lambda item: int(str(item[0]))):
            print(f"  [{index}] {shortcut.get('AppName', 'Unknown')} -> {shortcut.get('exe', '')}")


def select_games_to_add(candidates: list[DiscoveredGame]) -> list[DiscoveredGame]:
    if not candidates:
        print("No new non-Steam game candidates were found.")
        return []

    selected = [not candidate.ambiguous for candidate in candidates]
    while True:
        print(f"\nFound {len(candidates)} games to add:\n")
        for index, candidate in enumerate(candidates, start=1):
            mark = "x" if selected[index - 1] else " "
            suffix = " [needs review]" if candidate.ambiguous else ""
            print(f" [{mark}] {index:2d}. {candidate.app_name:<25} -> {candidate.exe_path}{suffix}")
        print("\nCommands: [a] Select all  [n] Select none  [1-#] Toggle  [c] Confirm  [q] Quit")
        response = input("Choose: ").strip().lower()
        if response == "a":
            selected = [True] * len(candidates)
            continue
        if response == "n":
            selected = [False] * len(candidates)
            continue
        if response == "c":
            break
        if response == "q":
            return []

        tokens = [token for token in response.replace(",", " ").split() if token]
        toggled = False
        for token in tokens:
            if token.isdigit() and 1 <= int(token) <= len(candidates):
                idx = int(token) - 1
                selected[idx] = not selected[idx]
                toggled = True
        if not toggled:
            print("Please enter one of the listed commands.")

    confirmed: list[DiscoveredGame] = []
    for is_selected, candidate in zip(selected, candidates):
        if not is_selected:
            continue
        if candidate.ambiguous:
            print(f"\n{candidate.app_name} has multiple possible executables:")
            for option_index, option in enumerate(candidate.candidates, start=1):
                print(f"  [{option_index}] {option}")
            while True:
                response = input(
                    f"Choose [1-{len(candidate.candidates)}], press Enter/y for the detected executable, or n to skip: "
                ).strip().lower()
                if response in {"", "y", "yes"}:
                    confirmed.append(candidate)
                    break
                if response in {"n", "no"}:
                    break
                if response.isdigit() and 1 <= int(response) <= len(candidate.candidates):
                    chosen_path = candidate.candidates[int(response) - 1]
                    confirmed.append(
                        DiscoveredGame(
                            app_name=candidate.app_name,
                            exe_path=chosen_path,
                            source_dir=candidate.source_dir,
                            score=candidate.score,
                            ambiguous=False,
                            candidates=candidate.candidates,
                        )
                    )
                    break
                print("Please enter a number, y, or n.")
            continue
        confirmed.append(candidate)
    return confirmed


def fix_existing_shortcuts(selected_users: list[SteamUser], logger) -> tuple[int, int]:
    total_fixed = 0
    total_removed = 0
    for user in selected_users:
        data = load_shortcuts(user.shortcuts_path)
        result = fix_shortcuts_interactively(data.get("shortcuts", {}), logger)
        if result.changed:
            if write_user_shortcuts(user, result.shortcuts, logger):
                total_fixed += result.fixed_count
                total_removed += result.removed_count
                print(f"Updated shortcuts for user {user.user_id}: {result.fixed_count} fixed, {result.removed_count} removed.")
        else:
            print(f"No changes needed for user {user.user_id}.")
    return total_fixed, total_removed


def scan_and_add_games(steam_path: Path, selected_users: list[SteamUser], logger) -> int:
    existing_sets = load_existing_sets(selected_users)
    common_existing = intersection_of_sets(existing_sets)
    steam_common_dirs = get_steam_common_directories(steam_path)
    candidates = discover_games(common_existing, steam_common_dirs, logger)
    chosen_games = select_games_to_add(candidates)
    if not chosen_games:
        print("No games selected.")
        return 0

    total_added = 0
    for user in selected_users:
        data = load_shortcuts(user.shortcuts_path)
        shortcuts_map = data.get("shortcuts", {})
        existing_for_user = collect_existing_exe_paths(data)
        combined = list(shortcuts_map.values())
        added_here = 0

        for game in chosen_games:
            identity = normalized_exe_identity(str(game.exe_path))
            if identity in existing_for_user:
                continue
            combined.append(build_shortcut(game.app_name, str(game.exe_path)))
            existing_for_user.add(identity)
            added_here += 1
            logger.info("Queued new shortcut '%s' for user %s", game.app_name, user.user_id)

        if added_here and write_user_shortcuts(user, reindex_shortcuts(combined), logger):
            total_added += added_here
            print(f"Added {added_here} game(s) for user {user.user_id}.")
        elif added_here == 0:
            print(f"No new games needed for user {user.user_id}.")

    return total_added


def download_all_artwork(selected_users: list[SteamUser], logger) -> int:
    api_key = resolve_api_key(prompt_if_missing=True)
    if not api_key:
        print("A SteamGridDB API key is required to download artwork.")
        return 0

    total_downloaded = 0
    for user in selected_users:
        data = load_shortcuts(user.shortcuts_path)
        shortcuts_map = data.get("shortcuts", {})
        if not shortcuts_map:
            print(f"No shortcuts found for user {user.user_id}.")
            continue

        try:
            result = download_artwork_for_shortcuts(shortcuts_map, user.grid_dir, api_key, logger)
        except RuntimeError as error:
            print(str(error))
            logger.error("Artwork download aborted: %s", error)
            return total_downloaded
        total_downloaded += result.downloaded
        if write_user_shortcuts(user, shortcuts_map, logger):
            print(
                f"Artwork for user {user.user_id}: {result.downloaded} downloaded, "
                f"{result.skipped} skipped, {result.failures} failed."
            )
    return total_downloaded


def full_run(steam_path: Path, selected_users: list[SteamUser], logger) -> None:
    total_fixed = 0
    total_removed = 0
    total_added = 0
    per_user_shortcuts: dict[str, dict[str, dict]] = {}

    for user in selected_users:
        data = load_shortcuts(user.shortcuts_path)
        result = fix_shortcuts_interactively(data.get("shortcuts", {}), logger)
        total_fixed += result.fixed_count
        total_removed += result.removed_count
        per_user_shortcuts[user.user_id] = result.shortcuts

    existing_sets = [
        {normalized_exe_identity(shortcut) for shortcut in shortcuts.values() if normalized_exe_identity(shortcut)}
        for shortcuts in per_user_shortcuts.values()
    ]
    steam_common_dirs = get_steam_common_directories(steam_path)
    candidates = discover_games(intersection_of_sets(existing_sets), steam_common_dirs, logger)
    chosen_games = select_games_to_add(candidates)

    for user in selected_users:
        shortcuts_map = per_user_shortcuts[user.user_id]
        existing = {normalized_exe_identity(shortcut) for shortcut in shortcuts_map.values() if normalized_exe_identity(shortcut)}
        combined = list(shortcuts_map.values())
        added_here = 0
        for game in chosen_games:
            identity = normalized_exe_identity(str(game.exe_path))
            if identity in existing:
                continue
            combined.append(build_shortcut(game.app_name, str(game.exe_path)))
            existing.add(identity)
            added_here += 1
            logger.info("Queued '%s' for user %s during full run", game.app_name, user.user_id)
        per_user_shortcuts[user.user_id] = reindex_shortcuts(combined)
        total_added += added_here

    if not chosen_games:
        print("No new games selected during full run.")

    api_key = resolve_api_key(prompt_if_missing=True)
    total_art = 0
    if api_key:
        try:
            for user in selected_users:
                art_result = download_artwork_for_shortcuts(per_user_shortcuts[user.user_id], user.grid_dir, api_key, logger)
                total_art += art_result.downloaded
                logger.info(
                    "Artwork result for user %s: downloaded=%s skipped=%s failures=%s",
                    user.user_id,
                    art_result.downloaded,
                    art_result.skipped,
                    art_result.failures,
                )
        except RuntimeError as error:
            print(str(error))
            logger.error("Artwork download aborted during full run: %s", error)
    else:
        print("Skipping artwork because no SteamGridDB API key was provided.")

    for user in selected_users:
        shortcuts_map = per_user_shortcuts[user.user_id]
        if write_user_shortcuts(user, shortcuts_map, logger):
            continue

    print(
        f"Full run complete: {total_fixed} fixed, {total_removed} removed, "
        f"{total_added} additions requested, {total_art} artwork files downloaded."
    )
    print("Start Steam to see your changes.")


def main() -> int:
    check_python_version()
    check_dependencies()
    logger = setup_logging(LOG_FILE_NAME)

    steam_path = find_steam_install_path()
    if steam_path is None:
        print("Could not find your Steam installation path.")
        logger.error("Steam installation path not found")
        return 1

    if is_steam_running():
        print("Steam is running. Close Steam completely before using this script.")
        logger.error("Refused to start because Steam is running")
        return 1

    selected_users = prompt_for_users(list_steam_users(steam_path))
    logger.info("Using Steam path %s", steam_path)
    logger.info("Selected Steam users: %s", ", ".join(user.user_id for user in selected_users))

    while True:
        print_menu(steam_path, selected_users)
        choice = input("Choose an option: ").strip()

        if choice == "0":
            print(f"Log written to {Path(LOG_FILE_NAME).resolve()}")
            return 0
        if choice == "1":
            fix_existing_shortcuts(selected_users, logger)
            continue
        if choice == "2":
            added = scan_and_add_games(steam_path, selected_users, logger)
            print(f"Added {added} new shortcut(s) in total.")
            continue
        if choice == "3":
            downloaded = download_all_artwork(selected_users, logger)
            print(f"Downloaded {downloaded} artwork file(s).")
            print("Start Steam to see your changes.")
            continue
        if choice == "4":
            full_run(steam_path, selected_users, logger)
            continue
        if choice == "5":
            list_shortcuts(selected_users)
            continue

        print("Please choose one of the listed options.")


if __name__ == "__main__":
    raise SystemExit(main())
