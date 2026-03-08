from __future__ import annotations

import os
import re
from pathlib import Path

def _load_local_env() -> dict[str, str]:
    env_path = Path(__file__).resolve().with_name(".env")
    if not env_path.exists():
        return {}

    values: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _get_env_value(*names: str) -> str | None:
    local_env = _load_local_env()
    for name in names:
        value = os.environ.get(name)
        if value:
            return value.strip()
        value = local_env.get(name)
        if value:
            return value.strip()
    return None


def _parse_scan_drives(value: str | None) -> list[Path]:
    if not value:
        return []

    drives: list[Path] = []
    seen: set[str] = set()
    for raw_part in re.split(r"[;,]", value):
        part = raw_part.strip().strip('"').strip("'")
        if not part:
            continue
        normalized = part.replace("/", "\\")
        if re.fullmatch(r"^[A-Za-z]:$", normalized):
            normalized = f"{normalized}\\"
        elif re.fullmatch(r"^[A-Za-z]:\\?$", normalized):
            normalized = normalized[:2] + "\\"
        path = Path(normalized)
        identity = str(path).lower()
        if identity in seen:
            continue
        seen.add(identity)
        drives.append(path)
    return drives


MIN_PYTHON = (3, 10)
LOG_FILE_NAME = "steam-game-manager.log"

DEFAULT_STEAM_PATHS = [
    Path(r"C:\Program Files (x86)\Steam"),
    Path(r"C:\Program Files\Steam"),
]

TARGET_DRIVES = _parse_scan_drives(_get_env_value("SCAN_DRIVES", "GAME_SCAN_DRIVES")) or [
    Path("C:/"),
    Path("F:/"),
    Path("G:/"),
]

KNOWN_GAME_DIRS = [
    Path(r"C:\Program Files (x86)\GOG Galaxy\Games"),
    Path(r"C:\GOG Games"),
    Path(r"C:\Program Files\Epic Games"),
    Path(r"C:\Program Files (x86)\Origin Games"),
    Path(r"C:\Program Files\EA Games"),
    Path(r"C:\Program Files (x86)\Ubisoft\Ubisoft Game Launcher\games"),
    Path(r"C:\Program Files (x86)\Battle.net"),
    Path(r"C:\Riot Games"),
    Path(r"C:\Games"),
    Path(r"F:\Games"),
    Path(r"G:\Games"),
    Path(r"F:\SteamLibrary"),
    Path(r"G:\SteamLibrary"),
]

SYSTEM_ROOT_SKIP_DIRS = {
    "$recycle.bin",
    "documents and settings",
    "intel",
    "msocache",
    "onedrivetemp",
    "perflogs",
    "program files",
    "program files (x86)",
    "programdata",
    "recovery",
    "system volume information",
    "users",
    "windows",
}

SKIP_EXE_PATTERNS = {
    "quicksfv.exe",
    "unins000.exe",
    "uninstall.exe",
    "setup.exe",
    "install.exe",
    "config.exe",
    "language selector.exe",
    "installermessage.exe",
    "easyanticheat_eos_setup.exe",
    "vcredist_x64.exe",
    "vcredist_x86.exe",
    "dxsetup.exe",
    "dxwebsetup.exe",
    "dotnetfx.exe",
    "ndp*.exe",
    "oalinst.exe",
    "unitycrashhandler64.exe",
    "unitycrashhandler32.exe",
    "crashreporter.exe",
    "bugreporter.exe",
    "reporter.exe",
    "ue4prereqsetup_x64.exe",
    "ue4prereqsetup_x86.exe",
    "epicgameslauncher.exe",
    "origin.exe",
    "galaxyclient.exe",
    "ubisoftconnect.exe",
    "ubisoftgamelauncher.exe",
    "battlenet.exe",
    "battle.net.exe",
    "updater.exe",
    "patcher.exe",
    "update.exe",
    "crashreportclient.exe",
}

SKIP_DIRS = {
    "_commonredist",
    "_emulators",
    "__installer",
    "__support",
    "_redist",
    "_windows 7 fix",
    "artbookost",
    "directx",
    "dotnet",
    "easyanticheat",
    "emu",
    "md5",
    "nodvd",
    "plugins",
    "prerequisites",
    "redist",
    "soundtrack",
    "streamingassets",
    "support",
    "tools",
    "vcredist",
}

SKIP_EXE_STEMS = {
    "cemu",
    "citron",
    "citron-cmd",
    "citron-room",
    "dolphin",
    "dolphin-x64",
    "easyanticheat_eos_setup",
    "eden",
    "eden-cli",
    "eden-room",
    "installermessage",
    "language selector",
    "p3a_tool",
    "replication-server",
    "ryujinx",
    "sudachi",
    "zfgamebrowser",
}

SKIP_CANDIDATE_APP_NAMES = {
    "island creator",
    "app digister",
    "artbook ost",
    "dolphin-x64",
    "citron",
    "codex",
    "common redist",
    "easyanticheat",
    "eden",
    "eden-windows",
    "emu",
    "game",
    "launcher",
    "md5",
    "ldc",
    "ls",
    "tgaac",
    "plugins",
    "prophet",
    "redist",
    "steam (goldberg emu)",
    "streaming assets",
    "sudachi",
    "wii u emulator",
    "tool",
    "windows 7 fix",
    "x64",
    "x 64",
}

SKIP_PATH_KEYWORDS = {
    "artbook",
    "codex",
    "easyanticheat",
    "emu",
    "emulator",
    "goldberg",
    "md5",
    "nodvd",
    "plugin",
    "prophet",
    "redist",
    "soundtrack",
    "streamingassets",
    "tool",
}

GENERIC_CONTAINER_DIRS = {
    "app",
    "app_digister",
    "bin",
    "binaries",
    "game",
    "games",
    "win64",
    "x64",
    "x86",
}

GAME_HINT_FILES = {
    "gameinfo.txt",
    "steam_api.dll",
    "steam_api64.dll",
    "unityplayer.dll",
}

GAME_HINT_PREFIXES = (
    "ue4-",
    "ue5-",
    "d3d",
)

MAX_SCAN_DEPTH = 3
MAX_EXECUTABLE_SCAN_DEPTH = 2

API_KEY_ENV_NAMES = ("STEAMGRIDDB_API_KEY", "API_KEY")
ENV_FILE_NAMES = (".env",)

ARTWORK_REQUEST_DELAY_SECONDS = 0.5
ARTWORK_MAX_RETRIES = 3

ARTWORK_REQUESTS = {
    "portrait": {
        "endpoint": "/grids/game/{game_id}",
        "params": {
            "dimensions": "600x900",
            "styles": "alternate",
            "types": "static",
            "nsfw": "false",
        },
        "filename": "{appid}p{ext}",
    },
    "horizontal": {
        "endpoint": "/grids/game/{game_id}",
        "params": {
            "dimensions": "920x430",
            "styles": "alternate",
            "types": "static",
            "nsfw": "false",
        },
        "filename": "{appid}{ext}",
    },
    "hero": {
        "endpoint": "/heroes/game/{game_id}",
        "params": {
            "types": "static",
            "nsfw": "false",
        },
        "filename": "{appid}_hero{ext}",
    },
    "logo": {
        "endpoint": "/logos/game/{game_id}",
        "params": {
            "types": "static",
            "nsfw": "false",
            "mimes": "image/png",
        },
        "filename": "{appid}_logo{ext}",
    },
    "icon": {
        "endpoint": "/icons/game/{game_id}",
        "params": {
            "types": "static",
            "nsfw": "false",
        },
        "filename": "{appid}_icon{ext}",
    },
}

DUMMY_SHORTCUT_NAME = "Steam Game Manager Validation"
DUMMY_SHORTCUT_EXE = r"C:\Windows\System32\notepad.exe"

REQUIRED_SHORTCUT_DEFAULTS = {
    "ShortcutPath": "",
    "LaunchOptions": "",
    "IsHidden": 0,
    "AllowDesktopConfig": 1,
    "AllowOverlay": 1,
    "OpenVR": 0,
    "Devkit": 0,
    "DevkitGameID": "",
    "DevkitOverrideAppID": 0,
    "LastPlayTime": 0,
    "FlatpakAppID": "",
}

KNOWN_SHORTCUT_FIELDS = {
    "appid",
    "AppName",
    "StartDir",
    "icon",
    "ShortcutPath",
    "LaunchOptions",
    "IsHidden",
    "AllowDesktopConfig",
    "AllowOverlay",
    "Exe",
    "OpenVR",
    "openvr",
    "sortas",
    "Devkit",
    "DevkitGameID",
    "DevkitOverrideAppID",
    "LastPlayTime",
    "FlatpakAppID",
    "tags",
}
