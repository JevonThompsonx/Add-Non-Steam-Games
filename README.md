# Steam Non-Steam Game Manager

Interactive Windows CLI for managing non-Steam shortcuts in Steam.

Current readiness: READY for validated local interactive use on a Windows machine where the built-in checks pass. Broader production-style readiness still NEEDS WORK until the project has wider multi-user and multi-library validation.

Core features:

- inspect existing non-Steam shortcuts without editing them
- scan configured game locations and drive roots for addable Windows executables
- fix malformed Steam shortcut fields before writing them back
- create backups and verify `shortcuts.vdf` after each write
- download SteamGridDB artwork when an API key is configured
- run diagnostics and dry-run validation modes with no data changes

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
- Write access to each target Steam `userdata/<id>/config` directory
- Network access and a valid SteamGridDB API key for artwork downloads

## Installation

```powershell
py -m pip install -r requirements.txt
```

Dependencies are pinned in `requirements.txt` for more reproducible installs.

## Configuration

Prefer real environment variables for secrets. If you want local-only configuration, create a `.env` file in the project folder by copying `.env.example`.

Example:

```env
STEAMGRIDDB_API_KEY="your-key-here"
SCAN_DRIVES="C:\\,F:\\,G:\\"
```

Supported values:

- `STEAMGRIDDB_API_KEY`: preferred SteamGridDB API key variable
- `API_KEY`: alternate key name supported for compatibility
- `SCAN_DRIVES`: comma- or semicolon-separated drive roots to scan for games

Notes:

- environment variables override `.env` values
- `.env` is for local use only and should never be committed
- if `SCAN_DRIVES` is omitted, the script defaults to scanning `C:\` only

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
- if `SCAN_DRIVES` is omitted, the script defaults to `C:\` only

## Run

From PowerShell:

```powershell
py .\main.py
```

For a non-destructive startup check:

```powershell
py .\main.py --diagnose
```

For a broader non-interactive dry run that validates the environment, shortcut access, scan configuration, and artwork key presence without making any changes:

```powershell
py .\main.py --dry-run-check
```

For a deeper non-interactive workflow validation that checks the `fix`, `add`, `artwork`, and `full run` paths without writing changes:

```powershell
py .\main.py --validate-flows
```

Or double-click:

```text
Run Steam Game Manager.cmd
```

The launcher now preserves the Python exit code and does not bypass PowerShell execution policy.
If startup fails, the launcher pauses so you can read the error before the window closes.

## Tests

Run the current regression checks with:

```powershell
python -m unittest discover -s tests -v
```

GitHub Actions also runs these checks on Windows across supported Python versions.

## Readiness Status

- local interactive status: READY when `--dry-run-check` and `--validate-flows` both pass and Steam is closed before mutation operations
- broader deployment status: NEEDS WORK because validation is still centered on a single real-world Steam environment and a focused regression suite
- current evidence: launcher failure handling, dry-run validation, workflow validation, real fix/artwork/full-run runs, rollback protections, 10 automated regression tests, and Windows CI coverage

## Recommended Validation Order

Before changing `shortcuts.vdf`, use this order:

1. `py .\main.py --diagnose`
2. `py .\main.py --dry-run-check`
3. `py .\main.py --validate-flows`
4. `py .\main.py`

## Validation Modes

- `--diagnose`: quick startup and environment summary
- `--dry-run-check`: non-interactive readiness check for the local environment
- `--validate-flows`: non-interactive workflow check for fix/add/artwork/full-run paths

## Menu Options

- `1` Fix broken shortcuts
- `2` Scan for new games to add
- `3` Download artwork for existing shortcuts
- `4` Full run: fix, scan, add, and download artwork
- `5` List current non-Steam shortcuts

## Notes

- the script refuses to write while Steam is running
- read-only startup checks no longer create missing Steam config folders
- write paths are validated before `shortcuts.vdf` or artwork changes are attempted
- existing shortcuts are only removed with your confirmation
- artwork filenames use the unsigned app ID Steam expects
- artwork downloads are cleaned up if the matching `shortcuts.vdf` update fails
- some SteamGridDB CDN assets may still fail even when search works
- start Steam after the script finishes to see updated shortcuts and artwork

## Safety And Limitations

- this project performs preflight validation, backups, and post-write verification before changing `shortcuts.vdf`
- corrupt or unreadable Steam shortcut data now stops the affected operation instead of silently continuing
- wildcard-based shortcut executables cannot be auto-fixed safely; they must be skipped or removed manually
- some SteamGridDB entries still legitimately return missing artwork for specific asset types
- the repository now includes a focused regression test suite and Windows CI, but it still needs broader real-library validation before it can be called broadly production-ready

## GitHub Upload Checklist

Before uploading, make sure you do not include:

- `.env`
- `steam-game-manager.log`
- `__pycache__`

This repository already includes a `.gitignore` for those files.

## License

This project is licensed under the MIT License. See `LICENSE`.
