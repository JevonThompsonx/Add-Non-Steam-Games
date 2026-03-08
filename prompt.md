# Non-Steam Game Manager — AI Build Prompt

## PRIORITY RULES — Always Active

> **These rules override everything below. Re-read before every response.**

| # | Rule | Non-Negotiable |
|---|------|----------------|
| 1 | **ALWAYS back up `shortcuts.vdf` before modifying it.** Copy to `shortcuts.vdf.bak.<timestamp>`. If the backup fails, abort. | YES |
| 2 | **Steam MUST be closed** before writing `shortcuts.vdf`. Detect running Steam processes and refuse to write if Steam is open. | YES |
| 3 | **Binary VDF format is exact.** One wrong byte corrupts the entire file and Steam resets it to empty. Use a tested library (`vdf` for Python) — never hand-roll binary VDF serialization. | YES |
| 4 | **Test every function in isolation before combining.** Read the existing `shortcuts.vdf`, parse it, re-serialize it, and diff against the original. If the round-trip doesn't produce a byte-identical file, your VDF implementation is broken — stop and fix it. | YES |
| 5 | **Wrap exe and StartDir paths in double quotes** inside the VDF data: `'"C:\\Games\\game.exe"'` not `'C:\\Games\\game.exe'`. Steam expects this. | YES |
| 6 | **Never delete existing shortcuts unless explicitly told to.** The "fix broken entries" step modifies or removes only entries the user confirms are broken. | YES |
| 7 | **SteamGridDB API key is required for artwork.** Prompt for it or read from environment variable. Never hardcode it. | YES |
| 8 | **If ambiguous, ask before acting** — especially about which exe is the "real" game launcher when a folder contains multiple executables. | YES |
| 9 | **Use Python 3.10+** with the `vdf` library for all binary VDF operations. Do not attempt to parse/write binary VDF manually. | YES |
| 10 | **Log every action** — what was added, what was modified, what was skipped, what artwork was downloaded, what failed. Write logs to a file. | YES |

---

## Role

You are building a Python script that manages non-Steam game shortcuts in the Steam client on Windows. The script will scan game directories, add games to Steam's `shortcuts.vdf`, fix broken existing entries, and download artwork from SteamGridDB. This runs on a Windows desktop (not a server, not an enterprise fleet). The user will run it interactively from a terminal.

---

## Context and Requirements

### What the User Needs

1. **Scan drives** `C:\`, `F:\`, and `G:\` for installed non-Steam games
2. **Fix broken entries** — previously added shortcuts that appear incorrectly in Steam (wrong paths, missing data, duplicate entries, garbled names)
3. **Add new games** to Steam as non-Steam shortcuts with correct metadata
4. **Download and apply artwork** — cover images (portrait grid), hero banners, logos, and icons from SteamGridDB

### What Went Wrong Before

The user's previous attempt added games "improperly." Common causes of broken non-Steam shortcuts:

- Exe paths not wrapped in double quotes (`"C:\path\game.exe"` — quotes are part of the stored string)
- StartDir not matching the exe's parent directory
- StartDir not wrapped in double quotes
- Corrupted binary VDF from hand-rolled serialization
- Duplicate entries (same game added multiple times with different indices)
- AppName set incorrectly (blank, wrong name, or containing the full path instead of just the game name)
- Missing required fields (AllowDesktopConfig, AllowOverlay, etc.)
- Appid field conflicts or missing values

---

## Technical Reference — Steam Shortcuts System

### File Locations

```
<SteamInstallPath>\userdata\<SteamUserID>\config\shortcuts.vdf    — Binary VDF, non-Steam shortcuts
<SteamInstallPath>\userdata\<SteamUserID>\config\grid\             — Grid artwork images
```

**Typical Steam install path:** `C:\Program Files (x86)\Steam`

**SteamUserID:** Numeric directory under `userdata\`. There may be multiple — the script must handle this (list them, let user choose, or process all).

### shortcuts.vdf Binary Format

This is a **binary** VDF file — NOT the text-based VDF used elsewhere in Steam. It uses the following type markers:

| Byte | Type | Description |
|------|------|-------------|
| `0x00` | Map/Dict | Start of a nested dictionary. Key is null-terminated string. |
| `0x01` | String | Key is null-terminated string, value is null-terminated string. |
| `0x02` | Int32 | Key is null-terminated string, value is 4 bytes little-endian uint32. |
| `0x08` | EndMap | End of current dictionary level. |

**Structure:**

```
Root Map "shortcuts"
  └─ Map "0"  (first shortcut)
  │    ├─ Int32  "appid"            — Signed 32-bit, little-endian. Steam uses this for grid art filenames.
  │    ├─ String "AppName"          — Display name in Steam library
  │    ├─ String "exe"              — MUST be quoted: '"C:\path\game.exe"'
  │    ├─ String "StartDir"         — MUST be quoted: '"C:\path\"'
  │    ├─ String "icon"             — Path to .ico/.exe/.png for the shortcut icon (optional)
  │    ├─ String "ShortcutPath"     — Usually empty string
  │    ├─ String "LaunchOptions"    — Command-line args (usually empty)
  │    ├─ Int32  "IsHidden"         — 0 or 1
  │    ├─ Int32  "AllowDesktopConfig" — 1 (always set to 1)
  │    ├─ Int32  "AllowOverlay"     — 1 (always set to 1)
  │    ├─ Int32  "openvr"           — 0
  │    ├─ Int32  "Devkit"           — 0
  │    ├─ String "DevkitGameID"     — Empty string
  │    ├─ Int32  "DevkitOverrideAppID" — 0
  │    ├─ Int32  "LastPlayTime"     — Unix timestamp or 0
  │    ├─ String "FlatpakAppID"     — Empty string (Windows, not relevant)
  │    └─ Map    "tags"             — Dictionary of string tags: {"0": "tag1", "1": "tag2"}
  └─ Map "1"  (second shortcut)
       └─ ...
```

### Critical VDF Rules

1. **Shortcut indices are string numbers** — `"0"`, `"1"`, `"2"`, etc. They must be sequential with no gaps.
2. **The `exe` field MUST have the path wrapped in double quotes** — this is the single most common cause of broken shortcuts. The stored string itself contains the quote characters: `'"C:\\Games\\MyGame\\game.exe"'`
3. **The `StartDir` field MUST also be quoted** — same rule: `'"C:\\Games\\MyGame\\"'`
4. **When Steam starts, it reads and sanitizes shortcuts.vdf.** Unknown keys are removed. Missing keys get default values. Malformed files get reset to empty.
5. **Use the Python `vdf` library** (`pip install vdf`) — it handles binary VDF reading/writing correctly.

### Python VDF Library Usage

```python
import vdf

# Reading
with open(shortcuts_path, 'rb') as f:
    data = vdf.binary_loads(f.read())
# data = {"shortcuts": {"0": {"appid": ..., "AppName": ..., ...}, "1": {...}}}

# Writing
with open(shortcuts_path, 'wb') as f:
    f.write(vdf.binary_dumps(data))
```

### AppID and Grid Art Filename Calculation

Steam assigns non-Steam shortcuts an `appid` (stored as a signed 32-bit int in shortcuts.vdf). When writing shortcuts programmatically, you can write a deterministic appid using CRC32:

```python
import binascii
import struct

def generate_shortcut_id(exe: str, app_name: str) -> int:
    """Generate a deterministic appid for a non-Steam shortcut.
    
    Args:
        exe: The exe field value exactly as stored in shortcuts.vdf (with quotes)
        app_name: The AppName field value
    
    Returns:
        Signed 32-bit integer appid
    """
    unique_id = exe + app_name
    crc = binascii.crc32(unique_id.encode('utf-8')) & 0xFFFFFFFF
    shortcut_id = crc | 0x80000000
    # Convert to signed 32-bit int (how Steam stores it)
    return struct.unpack('i', struct.pack('I', shortcut_id))[0]


def get_unsigned_id(signed_appid: int) -> int:
    """Convert signed appid from shortcuts.vdf to unsigned for grid filenames."""
    return struct.unpack('I', struct.pack('i', signed_appid))[0]
```

### Grid Art File Naming

Grid artwork goes in `<Steam>/userdata/<userid>/config/grid/` with these filenames:

| Art Type | Filename Pattern | Typical Dimensions | Used In |
|----------|------------------|--------------------|---------|
| Vertical grid (boxart/cover) | `<unsigned_appid>p.png` or `.jpg` | 600×900 | Library grid view |
| Horizontal grid | `<unsigned_appid>.png` or `.jpg` | 460×215 or 920×430 | Library list / detail |
| Hero banner | `<unsigned_appid>_hero.png` or `.jpg` | 1920×620 | Game detail page header |
| Logo | `<unsigned_appid>_logo.png` | 960×540 (transparent) | Overlaid on hero banner |
| Icon | `<unsigned_appid>_icon.png` or `.jpg` | 64×64 or higher | Library sidebar / task bar |

**The `icon` field in shortcuts.vdf** is a separate concept — it's the path to an `.ico` or `.exe` file used as the shortcut icon in the Steam UI's sidebar. The grid images above are placed as files in the `grid/` directory and Steam picks them up automatically.

---

## SteamGridDB API Reference

**Base URL:** `https://www.steamgriddb.com/api/v2`

**Authentication:** Bearer token in Authorization header.

```python
headers = {
    "Authorization": f"Bearer {api_key}"
}
```

**Get an API key:** User must register at https://www.steamgriddb.com, go to Preferences → API, and generate a key.

### Key Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/search/autocomplete/{term}` | GET | Search for a game by name. Returns list of games with SteamGridDB `id`. |
| `/grids/game/{id}` | GET | Get grid images (vertical/horizontal covers) for a game. |
| `/heroes/game/{id}` | GET | Get hero banner images. |
| `/logos/game/{id}` | GET | Get logo images (transparent). |
| `/icons/game/{id}` | GET | Get icon images. |

### Search Response Shape

```json
{
  "success": true,
  "data": [
    {
      "id": 2254,
      "name": "Half-Life 2",
      "types": ["steam"],
      "verified": true
    }
  ]
}
```

### Image Response Shape

```json
{
  "success": true,
  "data": [
    {
      "id": 80,
      "score": 1,
      "style": "alternate",
      "width": 600,
      "height": 900,
      "nsfw": false,
      "humor": false,
      "url": "https://cdn2.steamgriddb.com/grid/...",
      "thumb": "https://cdn2.steamgriddb.com/thumb/..."
    }
  ]
}
```

### Query Parameters for Filtering

| Parameter | Values | Use |
|-----------|--------|-----|
| `styles` | `alternate`, `blurred`, `white_logo`, `material`, `no_logo` | Filter grid/hero style |
| `dimensions` | `600x900` (portrait), `920x430` (horizontal), `1920x620` (hero) | Filter by size |
| `mimes` | `image/png`, `image/jpeg` | Filter by format |
| `types` | `static`, `animated` | Filter static vs animated |
| `nsfw` | `true`, `false` | Filter adult content |

**Prefer:** `styles=alternate`, `types=static`, `nsfw=false` for a clean library.

---

## Game Discovery — How to Find Games

### Scan Strategy

The script must scan `C:\`, `F:\`, and `G:\` for game executables. Do NOT blindly scan every directory — that would take forever. Use a targeted approach:

#### 1. Known Game Store Locations (check these first)

```python
KNOWN_GAME_DIRS = [
    # GOG Galaxy
    r"C:\Program Files (x86)\GOG Galaxy\Games",
    r"C:\GOG Games",
    # Epic Games
    r"C:\Program Files\Epic Games",
    # EA / Origin
    r"C:\Program Files (x86)\Origin Games",
    r"C:\Program Files\EA Games",
    # Ubisoft
    r"C:\Program Files (x86)\Ubisoft\Ubisoft Game Launcher\games",
    # Battle.net
    r"C:\Program Files (x86)\Battle.net",
    # Riot
    r"C:\Riot Games",
    # Generic
    r"C:\Games",
    r"F:\Games",
    r"G:\Games",
    r"F:\SteamLibrary",
    r"G:\SteamLibrary",
]
```

#### 2. Common Game Directory Patterns

Scan the root of each target drive for directories that look like game folders. Heuristics:

- Contains one or more `.exe` files
- Does NOT contain system files (`ntldr`, `bootmgr`, `pagefile.sys`)
- Is NOT a Windows system directory (`Windows`, `Program Files`, `ProgramData`, `Users`, `$Recycle.Bin`, `System Volume Information`, `Recovery`)
- Contains common game files: `steam_api.dll`, `UnityCrashHandler.exe`, `UnityPlayer.dll`, `UE4-*.dll`, `d3d*.dll`, `.uproject`, `gameinfo.txt`, etc.
- Has a subdirectory depth limit (don't recurse more than 3 levels from the scan root)

#### 3. Executable Selection Logic

When a game directory contains multiple `.exe` files, the script must pick the right one. Priority order:

1. Exe name closely matches the directory name (fuzzy match)
2. Exe is in the root of the game directory (not a subdirectory like `bin/`, `_CommonRedist/`, `support/`, `__Installer/`)
3. Exe is NOT a known non-game executable (skip list below)
4. Exe has the largest file size among candidates (game exes are usually the largest)

#### 4. Executables to SKIP (not game launchers)

```python
SKIP_EXES = {
    # Redistributables and installers
    "unins000.exe", "uninstall.exe", "setup.exe", "install.exe",
    "vcredist_x64.exe", "vcredist_x86.exe", "dxsetup.exe", "dxwebsetup.exe",
    "dotnetfx.exe", "ndp*.exe", "oalinst.exe",
    # Crash reporters and utilities
    "unitycrashhandler64.exe", "unitycrashhandler32.exe",
    "crashreporter.exe", "bugreporter.exe", "reporter.exe",
    "ue4prereqsetup_x64.exe", "ue4prereqsetup_x86.exe",
    # Launchers from other stores (don't add the launcher, add the game)
    "epicgameslauncher.exe", "origin.exe", "galaxyclient.exe",
    "ubisoftconnect.exe", "ubisoftgamelauncher.exe",
    "battlenet.exe", "battle.net.exe",
    # Updaters
    "updater.exe", "patcher.exe", "update.exe",
    # UE4/UE5 build tools
    "crashreportclient.exe",
}

SKIP_DIRS = {
    # Directories inside game folders that contain non-game exes
    "_commonredist", "directx", "redist", "vcredist",
    "__installer", "__support", "support", "tools",
    "dotnet", "prerequisites",
}
```

#### 5. Avoid Adding Steam Games

Cross-reference discovered games against Steam's existing library. Parse `libraryfolders.vdf` (text VDF, not binary) to find Steam library paths, then check `steamapps/common/` directories. If a game exe lives inside a Steam library's `common/` folder, skip it — it's already a Steam game.

```
<SteamInstallPath>\steamapps\libraryfolders.vdf  — lists all Steam library folders
<LibraryPath>\steamapps\common\                  — installed Steam games
```

---

## Script Architecture

### Module Structure

```
steam-game-manager/
├── main.py                    # Entry point — CLI interface
├── config.py                  # Configuration (paths, constants, skip lists)
├── steam_paths.py             # Find Steam install, userdata dirs, library folders
├── vdf_manager.py             # Read/write/backup shortcuts.vdf using vdf library
├── game_scanner.py            # Scan drives for game executables
├── shortcut_builder.py        # Build shortcut entries with correct field formatting
├── artwork_manager.py         # SteamGridDB API client + image download
├── fixer.py                   # Diagnose and fix broken existing shortcuts
├── logger_setup.py            # Configure logging to file + console
├── requirements.txt           # vdf, requests
└── README.md
```

### Execution Flow

```
1. PREFLIGHT CHECKS
   ├─ Verify Python version >= 3.10
   ├─ Verify required packages installed (vdf, requests)
   ├─ Find Steam installation path
   ├─ Find userdata directories (list Steam user IDs)
   ├─ Check if Steam is running — REFUSE to continue if it is
   └─ Prompt for SteamGridDB API key (or read from env STEAMGRIDDB_API_KEY)

2. LOAD EXISTING STATE
   ├─ Back up current shortcuts.vdf (timestamped copy)
   ├─ Parse existing shortcuts.vdf
   ├─ Parse Steam library folders (to exclude installed Steam games)
   └─ Build set of already-added exe paths (to avoid duplicates)

3. FIX BROKEN ENTRIES (interactive)
   ├─ For each existing shortcut, validate:
   │   ├─ exe path exists on disk
   │   ├─ exe path is wrapped in double quotes
   │   ├─ StartDir path is wrapped in double quotes
   │   ├─ StartDir matches exe's parent directory
   │   ├─ AppName is non-empty and reasonable (not a path, not garbled)
   │   ├─ No duplicate entries (same exe path)
   │   └─ Required fields present with valid values
   ├─ Report issues found
   ├─ For each issue, offer: Fix / Remove / Skip
   └─ Apply fixes

4. SCAN FOR NEW GAMES
   ├─ Scan known game directories on C:\, F:\, G:\
   ├─ Scan root-level directories on F:\ and G:\ for game folders
   ├─ Filter out Steam games, already-added games, system dirs
   ├─ For each candidate game:
   │   ├─ Select best exe (heuristics above)
   │   ├─ Derive AppName from directory name (cleaned up)
   │   └─ Present to user: "Found: Cyberpunk 2077 → G:\Games\Cyberpunk 2077\bin\x64\Cyberpunk2077.exe"
   ├─ User confirms which games to add (interactive list, select all / select individual)
   └─ Build shortcut entries for confirmed games

5. DOWNLOAD ARTWORK (for both fixed and new entries)
   ├─ For each shortcut (new + existing without art):
   │   ├─ Search SteamGridDB by AppName
   │   ├─ If multiple results, pick the best match (exact name match preferred, then highest-scored)
   │   ├─ Download: portrait grid, hero, logo, icon
   │   ├─ Save to <Steam>/userdata/<userid>/config/grid/ with correct filenames
   │   └─ Log success/failure per image type
   └─ Handle rate limiting (add delay between requests, respect 429 responses)

6. WRITE AND VERIFY
   ├─ Re-index all shortcuts sequentially ("0", "1", "2", ...)
   ├─ Serialize to binary VDF using vdf library
   ├─ Write to shortcuts.vdf
   ├─ VERIFY: re-read the file, parse it, compare shortcut count and data against expected
   └─ Print summary: X added, Y fixed, Z artwork downloaded, N errors

7. POST-RUN
   ├─ Print: "Start Steam to see your changes."
   └─ Write full log to steam-game-manager.log
```

---

## Validation Tests — Run These Before Any Modifications

The local model MUST run these validation steps to verify VDF handling is correct before touching the real `shortcuts.vdf`:

### Test 1: Round-Trip Integrity

```python
"""Read shortcuts.vdf, parse it, re-serialize it, compare bytes."""
with open(shortcuts_path, 'rb') as f:
    original_bytes = f.read()

data = vdf.binary_loads(original_bytes)
reserialized = vdf.binary_dumps(data)

if original_bytes == reserialized:
    print("PASS: Round-trip produces identical bytes")
else:
    print("FAIL: Round-trip mismatch!")
    print(f"  Original size:     {len(original_bytes)} bytes")
    print(f"  Reserialized size: {len(reserialized)} bytes")
    # Find first differing byte
    for i, (a, b) in enumerate(zip(original_bytes, reserialized)):
        if a != b:
            print(f"  First diff at byte {i}: original=0x{a:02x}, reserialized=0x{b:02x}")
            break
    sys.exit(1)
```

**If this test fails, DO NOT proceed. The VDF library version may have a bug, or the file format has changed. Debug this first.**

### Test 2: Field Quoting Verification

```python
"""Verify exe and StartDir fields are properly quoted."""
data = vdf.binary_loads(original_bytes)
for idx, shortcut in data.get("shortcuts", {}).items():
    exe = shortcut.get("exe", "")
    start_dir = shortcut.get("StartDir", "")
    
    if exe and not (exe.startswith('"') and exe.endswith('"')):
        print(f"WARNING: Shortcut '{shortcut.get('AppName')}' exe not quoted: {exe}")
    if start_dir and not (start_dir.startswith('"') and start_dir.endswith('"')):
        print(f"WARNING: Shortcut '{shortcut.get('AppName')}' StartDir not quoted: {start_dir}")
```

### Test 3: Add-One-and-Verify

```python
"""Add a single test shortcut, write, re-read, verify it exists, then remove it and restore."""
# 1. Parse existing
# 2. Add one dummy shortcut
# 3. Write to a TEMPORARY copy (not the real file)
# 4. Re-read the temp copy
# 5. Verify the dummy shortcut is present with correct fields
# 6. Verify all original shortcuts are still intact
# 7. Delete the temp copy
```

### Test 4: Steam Running Check

```python
"""Verify Steam detection works."""
import subprocess

def is_steam_running() -> bool:
    result = subprocess.run(
        ["tasklist", "/FI", "IMAGENAME eq steam.exe"],
        capture_output=True, text=True
    )
    return "steam.exe" in result.stdout.lower()
```

---

## Error Handling Requirements

| Scenario | Action |
|----------|--------|
| Steam is running | Print error message with instructions to close Steam. Exit. |
| `shortcuts.vdf` doesn't exist | Create a new empty one: `{"shortcuts": {}}` |
| `shortcuts.vdf` is 0 bytes | Treat as empty, create fresh structure |
| Backup fails (disk full, permissions) | Abort entirely — do not modify without backup |
| VDF round-trip test fails | Abort — print diagnostic info and stop |
| SteamGridDB API returns 401 | Invalid API key — prompt user to check it |
| SteamGridDB API returns 404 for a game | Skip artwork for that game, log it, continue |
| SteamGridDB API returns 429 | Rate limited — wait and retry with exponential backoff |
| Game exe path doesn't exist on disk | Flag as broken entry during fix phase |
| Multiple Steam user IDs found | List them with last-modified dates, let user pick or process all |
| Network error during artwork download | Log it, skip that image, continue with others |
| Duplicate shortcut detected (same exe) | Keep the one with more complete data, remove the other |

---

## Field Formatting Reference

### Building a New Shortcut Entry

```python
def build_shortcut(app_name: str, exe_path: str, icon_path: str = "") -> dict:
    """Build a properly formatted shortcut dictionary.
    
    Args:
        app_name: Display name (e.g., "Cyberpunk 2077")
        exe_path: Full path to exe (e.g., r"G:\Games\Cyberpunk 2077\bin\x64\Cyberpunk2077.exe")
        icon_path: Optional path to .ico file
    """
    start_dir = os.path.dirname(exe_path)
    
    # Generate deterministic appid
    quoted_exe = f'"{exe_path}"'
    appid = generate_shortcut_id(quoted_exe, app_name)
    
    return {
        "appid": appid,
        "AppName": app_name,
        "exe": quoted_exe,                    # MUST be quoted
        "StartDir": f'"{start_dir}\\"',       # MUST be quoted, trailing backslash
        "icon": icon_path,
        "ShortcutPath": "",
        "LaunchOptions": "",
        "IsHidden": 0,
        "AllowDesktopConfig": 1,
        "AllowOverlay": 1,
        "openvr": 0,
        "Devkit": 0,
        "DevkitGameID": "",
        "DevkitOverrideAppID": 0,
        "LastPlayTime": 0,
        "FlatpakAppID": "",
        "tags": {},
    }
```

### AppName Cleaning

Derive a clean game name from the folder name:

```python
def clean_game_name(folder_name: str) -> str:
    """Clean up a folder name into a presentable game name.
    
    Examples:
        "Cyberpunk.2077-GOG"     → "Cyberpunk 2077"
        "TheWitcher3_GOTY"       → "The Witcher 3 GOTY"
        "Half-Life 2"            → "Half-Life 2"  (preserve hyphens in real names)
        "game-v1.2.3"            → "Game"  (strip version numbers)
    """
    name = folder_name
    # Remove common suffixes
    for suffix in ["-GOG", "-CODEX", "-PLAZA", "-FitGirl", "-Repack", 
                   " (GOG)", " (Epic)", " [GOG]"]:
        name = name.replace(suffix, "")
    # Replace dots and underscores with spaces (but not in version-like patterns first)
    name = re.sub(r'[-_.]v?\d+\.\d+.*$', '', name)  # Strip version strings
    name = name.replace('.', ' ').replace('_', ' ')
    # Clean up whitespace
    name = ' '.join(name.split())
    return name.strip()
```

---

## Artwork Download Procedure

### Per-Game Artwork Flow

```
1. Search SteamGridDB: GET /search/autocomplete/{clean_app_name}
2. Pick best match from results:
   - Exact name match (case-insensitive) → use immediately
   - Closest fuzzy match with highest score
   - If no match found → log and skip artwork for this game
3. Using the SteamGridDB game ID, fetch artwork:
   a. GET /grids/game/{id}?dimensions=600x900&types=static&nsfw=false  → portrait cover
   b. GET /grids/game/{id}?dimensions=920x430&types=static&nsfw=false  → horizontal grid
   c. GET /heroes/game/{id}?types=static&nsfw=false                     → hero banner
   d. GET /logos/game/{id}?types=static&nsfw=false                      → logo overlay
   e. GET /icons/game/{id}?types=static&nsfw=false                      → icon
4. For each art type, download the highest-scored image
5. Save to grid directory with correct filename:
   - Portrait:   <unsigned_appid>p.png  (or .jpg based on source)
   - Horizontal: <unsigned_appid>.png
   - Hero:       <unsigned_appid>_hero.png
   - Logo:       <unsigned_appid>_logo.png
   - Icon:       <unsigned_appid>_icon.png
6. Also set the shortcut's "icon" field to the downloaded icon path
```

### Rate Limiting

- Add a 0.5-second delay between API requests
- On 429 response: wait 5 seconds, retry up to 3 times
- Log all API failures with the game name and endpoint

---

## CLI Interface

The script should present an interactive terminal UI. No GUI. No web interface. Keep it simple.

### Main Menu

```
Steam Non-Steam Game Manager
═══════════════════════════════

Steam path:  C:\Program Files (x86)\Steam
User ID:     12345678
Shortcuts:   14 existing entries

[1] Scan for broken entries and fix them
[2] Scan drives for new games to add
[3] Download artwork for all shortcuts (existing + new)
[4] Full run (fix → add → artwork)
[5] List all current non-Steam shortcuts
[0] Exit

Choose an option:
```

### Game Selection UI

```
Found 23 games to add:

 [x]  1. Cyberpunk 2077          → G:\Games\Cyberpunk 2077\bin\x64\Cyberpunk2077.exe
 [x]  2. The Witcher 3           → G:\Games\The Witcher 3\bin\x64\witcher3.exe
 [ ]  3. Unknown Game             → F:\Games\SomeFolder\launcher.exe
 [x]  4. Hades                   → G:\Games\Hades\Hades.exe
 ...

Commands: [a] Select all  [n] Select none  [1-23] Toggle  [c] Confirm  [q] Quit
```

---

## Dependencies

```
# requirements.txt
vdf>=3.4
requests>=2.31
```

**Only two external dependencies.** The `vdf` library handles binary VDF. `requests` handles HTTP for SteamGridDB. Everything else is stdlib.

### Install Check at Startup

```python
def check_dependencies():
    missing = []
    try:
        import vdf
    except ImportError:
        missing.append("vdf")
    try:
        import requests
    except ImportError:
        missing.append("requests")
    
    if missing:
        print(f"Missing required packages: {', '.join(missing)}")
        print(f"Install them with: pip install {' '.join(missing)}")
        sys.exit(1)
```

---

## Deliverables Checklist

Before presenting the finished script, verify:

- [ ] `pip install vdf requests` installs cleanly
- [ ] Script detects Steam installation path correctly
- [ ] Script detects and lists Steam user IDs
- [ ] Script refuses to run if Steam is open
- [ ] Round-trip test passes (read → parse → serialize → write produces identical bytes)
- [ ] Backup of shortcuts.vdf is created before any modification
- [ ] Broken entries are detected and reported with actionable descriptions
- [ ] Fix operations correctly re-quote exe and StartDir paths
- [ ] Duplicate shortcuts are detected
- [ ] Game scanner finds games in known directories
- [ ] Game scanner skips system directories and non-game executables
- [ ] Game scanner skips games already in Steam (both Steam games and existing shortcuts)
- [ ] New shortcuts have all required fields with correct types and formatting
- [ ] Exe and StartDir are double-quoted in the stored strings
- [ ] AppID is generated deterministically
- [ ] SteamGridDB search returns relevant results
- [ ] Artwork downloads to correct filenames in the grid directory
- [ ] Final shortcuts.vdf is valid (passes round-trip test)
- [ ] All shortcuts are sequentially indexed ("0", "1", "2", ...)
- [ ] Log file captures all actions, decisions, and errors
- [ ] Script runs without errors on Python 3.10+ on Windows

---

## Known Gotchas

| Gotcha | Solution |
|--------|----------|
| `vdf.binary_loads()` may return different key casing than expected | Always access keys case-sensitively as documented: `AppName`, `exe`, `StartDir`, `IsHidden` |
| Steam randomizes appid when adding via the UI | Our script writes a deterministic CRC-based appid, which is fine — Steam accepts whatever appid is in the file |
| Grid art filenames use the **unsigned** representation of the appid | Convert the signed int32 from shortcuts.vdf to unsigned before building filenames |
| Some `vdf` library versions handle the `appid` field differently | Verify the library stores it as a signed int. Test with a known shortcut. |
| Steam may not show new artwork until restarted | Expected behavior — document in post-run output |
| SteamGridDB may not have artwork for obscure/indie games | Gracefully skip, log the miss, don't error out |
| Some games have launchers (GOG Galaxy, EA App) as the exe | Detect store launchers in the skip list — add the actual game exe, not the store |
| `shortcuts.vdf` may not exist at all if no non-Steam games have ever been added | Create the file with an empty shortcuts structure |
| Windows paths with spaces need careful quoting | The double-quote wrapping in exe/StartDir handles this |
| Re-running the script should be idempotent | Check for existing shortcuts by exe path before adding duplicates |

---

## REINFORCEMENT — Critical Rules Restated

> **Re-read before finalizing.**

1. **Back up `shortcuts.vdf` before ANY modification** — timestamped copy, abort if backup fails
2. **Steam must be closed** — check `tasklist` for `steam.exe`, refuse to write if running
3. **Use the `vdf` Python library** — never hand-roll binary VDF serialization
4. **Round-trip test first** — read, parse, re-serialize, byte-compare. If it fails, stop.
5. **Double-quote exe and StartDir** — the stored string includes the quote characters
6. **Sequential shortcut indices** — `"0"`, `"1"`, `"2"` with no gaps
7. **Deterministic appid via CRC32** — `crc32(exe + AppName) | 0x80000000`, stored as signed int32
8. **Grid art uses unsigned appid** — convert before building filenames
9. **SteamGridDB API key from env or prompt** — never hardcoded
10. **Idempotent** — running twice doesn't create duplicates; check exe paths before adding
11. **Log everything** — every add, fix, skip, download, and error goes to the log file
12. **Test before touching real data** — run all validation tests first, use temp copies for initial testing