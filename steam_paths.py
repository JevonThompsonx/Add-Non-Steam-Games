from __future__ import annotations

import os
import importlib
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from config import DEFAULT_STEAM_PATHS

try:
    import winreg
except ImportError:
    winreg = None


@dataclass(slots=True)
class SteamUser:
    user_id: str
    userdata_dir: Path
    config_dir: Path
    shortcuts_path: Path
    grid_dir: Path
    last_modified: datetime


def _candidate_registry_paths() -> list[str]:
    return [
        r"SOFTWARE\Valve\Steam",
        r"SOFTWARE\WOW6432Node\Valve\Steam",
    ]


def find_steam_install_path() -> Path | None:
    env_value = os.environ.get("STEAM_PATH")
    if env_value:
        env_path = Path(env_value)
        if env_path.exists():
            return env_path

    if winreg is not None:
        for hive in (getattr(winreg, "HKEY_CURRENT_USER", None), getattr(winreg, "HKEY_LOCAL_MACHINE", None)):
            if hive is None:
                continue
            for registry_path in _candidate_registry_paths():
                try:
                    with winreg.OpenKey(hive, registry_path) as key:
                        for value_name in ("SteamPath", "InstallPath"):
                            try:
                                value, _ = winreg.QueryValueEx(key, value_name)
                            except FileNotFoundError:
                                continue
                            path = Path(str(value))
                            if path.exists():
                                return path
                except FileNotFoundError:
                    continue

    for path in DEFAULT_STEAM_PATHS:
        if path.exists():
            return path
    return None


def list_steam_users(steam_path: Path) -> list[SteamUser]:
    userdata_root = steam_path / "userdata"
    if not userdata_root.exists():
        return []

    users: list[SteamUser] = []
    for entry in userdata_root.iterdir():
        if not entry.is_dir() or not entry.name.isdigit():
            continue
        config_dir = entry / "config"
        config_dir.mkdir(parents=True, exist_ok=True)
        stat_source = config_dir if config_dir.exists() else entry
        users.append(
            SteamUser(
                user_id=entry.name,
                userdata_dir=entry,
                config_dir=config_dir,
                shortcuts_path=config_dir / "shortcuts.vdf",
                grid_dir=config_dir / "grid",
                last_modified=datetime.fromtimestamp(stat_source.stat().st_mtime),
            )
        )

    return sorted(users, key=lambda item: item.last_modified, reverse=True)


def is_steam_running() -> bool:
    result = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq steam.exe"],
        capture_output=True,
        text=True,
        check=False,
    )
    return "steam.exe" in result.stdout.lower()


def load_libraryfolders(steam_path: Path) -> list[Path]:
    vdf = importlib.import_module("vdf")

    library_file = steam_path / "steamapps" / "libraryfolders.vdf"
    libraries = {steam_path}
    if not library_file.exists():
        return sorted(libraries, key=lambda path: str(path).lower())

    with library_file.open("r", encoding="utf-8") as handle:
        data = vdf.load(handle)

    libraryfolders = data.get("libraryfolders", {})
    for value in libraryfolders.values():
        if isinstance(value, dict):
            path_value = value.get("path")
        else:
            path_value = value
        if not path_value:
            continue
        candidate = Path(str(path_value).replace("\\\\", "\\"))
        libraries.add(candidate)

    return sorted(libraries, key=lambda path: str(path).lower())


def get_steam_common_directories(steam_path: Path) -> list[Path]:
    common_dirs: list[Path] = []
    for library in load_libraryfolders(steam_path):
        common_path = library / "steamapps" / "common"
        if common_path.exists():
            common_dirs.append(common_path)
    return common_dirs


def path_is_in_steam_library(exe_path: str | Path, common_dirs: list[Path]) -> bool:
    candidate = Path(str(exe_path))
    try:
        candidate = candidate.resolve(strict=False)
    except OSError:
        candidate = candidate.absolute()

    for common_dir in common_dirs:
        try:
            resolved_common = common_dir.resolve(strict=False)
        except OSError:
            resolved_common = common_dir.absolute()
        try:
            candidate.relative_to(resolved_common)
            return True
        except ValueError:
            continue
    return False
