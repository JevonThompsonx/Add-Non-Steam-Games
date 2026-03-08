# Steam Non-Steam Game Manager

Interactive Windows CLI for managing non-Steam shortcuts in Steam.

## Features

- Finds your Steam install and Steam user IDs automatically
- Reads and writes Steam's binary `shortcuts.vdf` using the `vdf` library
- Creates a timestamped backup before every write
- Scans common install locations and selected drive roots for Windows games
- Fixes broken shortcut fields like unquoted `Exe` and invalid `StartDir`
- Adds new non-Steam shortcuts with deterministic app IDs
- Downloads SteamGridDB artwork into Steam's `grid` directory
- Logs activity to `steam-game-manager.log`

## Requirements

- Windows
- Python 3.10+
- Steam closed before any write operation

## Installation

```powershell
py -m pip install -r requirements.txt
```

## Configuration

Create a `.env` file in the project folder. You can copy `.env.example`.

Example:

```env
STEAMGRIDDB_API_KEY="your-key-here"
SCAN_DRIVES="C:\\,F:\\,G:\\"
```

Supported values:

- `STEAMGRIDDB_API_KEY`: preferred SteamGridDB API key variable
- `API_KEY`: alternate key name supported for compatibility
- `SCAN_DRIVES`: comma- or semicolon-separated drive roots to scan for games

## Choosing Which Drives To Scan

Set `SCAN_DRIVES` in `.env` to control which drive roots are scanned.

Examples:

```env
SCAN_DRIVES="C:\\,D:\\,E:\\"
```

```env
SCAN_DRIVES="F:\\;G:\\"
```

Notes:

- use drive roots like `D:\\` or `F:\\`
- commas and semicolons are both supported
- if `SCAN_DRIVES` is omitted, the script defaults to `C:\`, `F:\`, and `G:\`

## Run

From PowerShell:

```powershell
py .\main.py
```

Or double-click:

```text
Run Steam Game Manager.bat
```

## Menu Options

- `1` Fix broken shortcuts
- `2` Scan for new games to add
- `3` Download artwork for existing shortcuts
- `4` Full run: fix, scan, add, and download artwork
- `5` List current non-Steam shortcuts

## Notes

- the script refuses to write while Steam is running
- existing shortcuts are only removed with your confirmation
- artwork filenames use the unsigned app ID Steam expects
- some SteamGridDB CDN assets may still fail even when search works
- start Steam after the script finishes to see updated shortcuts and artwork

## GitHub Upload Checklist

Before uploading, make sure you do not include:

- `.env`
- `steam-game-manager.log`
- `__pycache__`

This repository already includes a `.gitignore` for those files.

## License

This project is licensed under the MIT License. See `LICENSE`.
