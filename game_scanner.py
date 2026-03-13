from __future__ import annotations

import fnmatch
import os
from dataclasses import dataclass, field
from pathlib import Path

from config import (
    GENERIC_CONTAINER_DIRS,
    GAME_HINT_FILES,
    GAME_HINT_PREFIXES,
    KNOWN_GAME_DIRS,
    MAX_EXECUTABLE_SCAN_DEPTH,
    MAX_SCAN_DEPTH,
    SKIP_CANDIDATE_APP_NAMES,
    SKIP_DIRS,
    SKIP_EXE_PATTERNS,
    SKIP_EXE_STEMS,
    SKIP_PATH_KEYWORDS,
    SYSTEM_ROOT_SKIP_DIRS,
    TARGET_DRIVES,
)
from shortcut_builder import clean_game_name, normalize_lookup_text, normalized_exe_identity, prettify_exe_stem, similarity_score
from steam_paths import path_is_in_steam_library


@dataclass(slots=True)
class DiscoveredGame:
    app_name: str
    exe_path: Path
    source_dir: Path
    score: float
    ambiguous: bool = False
    candidates: list[Path] = field(default_factory=list)


def _is_skip_exe(file_name: str) -> bool:
    lowered = file_name.lower()
    stem = Path(lowered).stem
    return stem in SKIP_EXE_STEMS or any(fnmatch.fnmatch(lowered, pattern) for pattern in SKIP_EXE_PATTERNS)


def _is_skip_dir(directory_name: str) -> bool:
    lowered = directory_name.lower()
    return lowered in SKIP_DIRS or lowered in SYSTEM_ROOT_SKIP_DIRS


def _path_contains_skip_keyword(path: Path) -> bool:
    lowered_parts = [part.lower() for part in path.parts]
    return any(keyword in part for part in lowered_parts for keyword in SKIP_PATH_KEYWORDS)


def _has_game_hints(files: list[str]) -> bool:
    lowered = {file_name.lower() for file_name in files}
    if lowered.intersection(GAME_HINT_FILES):
        return True
    return any(file_name.lower().startswith(GAME_HINT_PREFIXES) for file_name in files)


def _depth(root: Path, current: Path) -> int:
    try:
        return len(current.relative_to(root).parts)
    except ValueError:
        return MAX_SCAN_DEPTH + 1


def _iter_candidate_directories(scan_root: Path, max_depth: int) -> list[Path]:
    candidates: list[Path] = []
    for current_root, dir_names, file_names in os.walk(scan_root):
        current_path = Path(current_root)
        current_depth = _depth(scan_root, current_path)

        dir_names[:] = [name for name in dir_names if not _is_skip_dir(name)]
        if current_depth >= max_depth:
            dir_names[:] = []

        exe_files = [name for name in file_names if name.lower().endswith(".exe") and not _is_skip_exe(name)]
        if exe_files or _has_game_hints(file_names):
            candidates.append(current_path)
    return candidates


def _scan_drive_roots() -> list[Path]:
    roots: list[Path] = []
    for drive in TARGET_DRIVES:
        if drive.drive.upper() == "C:":
            continue
        if not drive.exists():
            continue
        try:
            for child in drive.iterdir():
                if child.is_dir() and child.name.lower() not in SYSTEM_ROOT_SKIP_DIRS:
                    roots.append(child)
        except OSError:
            continue
    return roots


def _candidate_score(game_dir: Path, exe_path: Path) -> float:
    score = 0.0
    dir_name = clean_game_name(game_dir.name)
    exe_name = clean_game_name(exe_path.stem)
    score += similarity_score(dir_name, exe_name) * 100

    try:
        relative_parts = exe_path.relative_to(game_dir).parts
    except ValueError:
        relative_parts = ()

    if len(relative_parts) == 1:
        score += 25
    elif len(relative_parts) == 2:
        score += 10

    if any(part.lower() in SKIP_DIRS for part in relative_parts[:-1]):
        score -= 25

    if _path_contains_skip_keyword(exe_path):
        score -= 100

    if exe_path.stem.lower() in SKIP_EXE_STEMS:
        score -= 120

    try:
        size_mb = exe_path.stat().st_size / (1024 * 1024)
    except OSError:
        size_mb = 0.0
    score += min(size_mb, 50.0)
    return score


def _derive_display_name(game_dir: Path, exe_path: Path) -> str:
    exe_name = prettify_exe_stem(exe_path.stem)
    if exe_name.strip().lower() not in SKIP_CANDIDATE_APP_NAMES and len(exe_name.strip()) >= 6:
        if similarity_score(clean_game_name(game_dir.name), exe_name) >= 0.6:
            return exe_name

    for parent in [exe_path.parent, *exe_path.parents[1:]]:
        if parent == game_dir.parent:
            break
        name = parent.name.strip()
        if not name:
            continue
        lowered = name.lower()
        if lowered in GENERIC_CONTAINER_DIRS or lowered in SKIP_DIRS:
            continue
        if any(keyword in lowered for keyword in SKIP_PATH_KEYWORDS):
            continue
        return clean_game_name(name)
    return clean_game_name(game_dir.name or exe_path.stem)


def _is_valid_candidate(game_dir: Path, exe_path: Path, app_name: str, score: float) -> bool:
    if score <= 0:
        return False
    if app_name.strip().lower() in SKIP_CANDIDATE_APP_NAMES:
        return False
    if len(app_name.strip()) <= 3:
        return False
    if exe_path.stem.lower() in SKIP_EXE_STEMS:
        return False
    if _path_contains_skip_keyword(exe_path) and app_name.strip().lower() not in {"horizon - zero down ce"}:
        return False
    return True


def _select_best_executable(game_dir: Path, steam_common_dirs: list[Path]) -> tuple[Path | None, bool, list[Path], float]:
    candidates: list[tuple[float, Path]] = []

    for current_root, dir_names, file_names in os.walk(game_dir):
        current_path = Path(current_root)
        if _depth(game_dir, current_path) > MAX_EXECUTABLE_SCAN_DEPTH:
            dir_names[:] = []
            continue

        dir_names[:] = [name for name in dir_names if not _is_skip_dir(name)]
        for file_name in file_names:
            if not file_name.lower().endswith(".exe") or _is_skip_exe(file_name):
                continue
            exe_path = current_path / file_name
            if path_is_in_steam_library(exe_path, steam_common_dirs):
                continue
            candidates.append((_candidate_score(game_dir, exe_path), exe_path))

    if not candidates:
        return None, False, [], 0.0

    candidates.sort(key=lambda item: item[0], reverse=True)
    best_score, best_path = candidates[0]
    top_paths = [path for _, path in candidates[:3]]

    ambiguous = False
    if len(candidates) > 1:
        second_score = candidates[1][0]
        ambiguous = (best_score - second_score) < 15 or best_score < 55

    return best_path, ambiguous, top_paths, best_score


def discover_games(
    existing_exe_paths: set[str],
    steam_common_dirs: list[Path],
    logger,
    existing_app_names: set[str] | None = None,
) -> list[DiscoveredGame]:
    candidate_dirs: list[Path] = []
    seen_dirs: set[str] = set()

    for known_dir in KNOWN_GAME_DIRS:
        if not known_dir.exists():
            continue
        for candidate in _iter_candidate_directories(known_dir, MAX_SCAN_DEPTH):
            identity = os.path.normcase(str(candidate))
            if identity not in seen_dirs:
                seen_dirs.add(identity)
                candidate_dirs.append(candidate)

    for root_dir in _scan_drive_roots():
        if os.path.normcase(str(root_dir)) in seen_dirs:
            continue
        for candidate in _iter_candidate_directories(root_dir, MAX_SCAN_DEPTH - 1):
            identity = os.path.normcase(str(candidate))
            if identity not in seen_dirs:
                seen_dirs.add(identity)
                candidate_dirs.append(candidate)

    discovered: list[DiscoveredGame] = []
    seen_exes = set(existing_exe_paths)
    seen_app_names = set(existing_app_names or set())

    for game_dir in sorted(candidate_dirs, key=lambda path: str(path).lower()):
        best_exe, ambiguous, candidates, score = _select_best_executable(game_dir, steam_common_dirs)
        if best_exe is None:
            continue

        exe_identity = normalized_exe_identity(str(best_exe))
        if not exe_identity or exe_identity in seen_exes:
            continue

        app_name = _derive_display_name(game_dir, best_exe)
        normalized_app_name = normalize_lookup_text(app_name)
        if normalized_app_name in seen_app_names:
            continue
        if not _is_valid_candidate(game_dir, best_exe, app_name, score):
            continue
        discovered.append(
            DiscoveredGame(
                app_name=app_name,
                exe_path=best_exe,
                source_dir=game_dir,
                score=score,
                ambiguous=ambiguous,
                candidates=candidates,
            )
        )
        seen_exes.add(exe_identity)
        seen_app_names.add(normalized_app_name)
        logger.info("Discovered candidate game '%s' at %s", app_name, best_exe)

    return sorted(discovered, key=lambda item: item.app_name.lower())
