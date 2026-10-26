from __future__ import annotations

import hashlib
import os
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable


CATEGORY_EXTENSIONS = {
    "Images": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".svg", ".bmp", ".tiff"},
    "Videos": {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"},
    "Audio": {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"},
    "Documents": {".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt", ".pages", ".md"},
    "Spreadsheets": {".xls", ".xlsx", ".csv", ".ods", ".numbers"},
    "Presentations": {".ppt", ".pptx", ".key", ".odp"},
    "Archives": {".zip", ".rar", ".7z", ".tar", ".gz", ".dmg", ".iso"},
    "Code": {".py", ".js", ".ts", ".html", ".css", ".java", ".c", ".cpp", ".go", ".rs", ".json"},
    "Applications": {".exe", ".msi", ".app", ".pkg", ".deb", ".apk"},
}


def category_for(path: Path) -> str:
    suffix = path.suffix.lower()
    for category, extensions in CATEGORY_EXTENSIONS.items():
        if suffix in extensions:
            return category
    return "Other"


def format_bytes(value: int) -> str:
    size = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


@dataclass(frozen=True)
class FileInfo:
    path: Path
    size: int
    modified: float
    category: str


@dataclass
class ScanResult:
    root: Path
    files: list[FileInfo] = field(default_factory=list)
    duplicate_groups: list[list[FileInfo]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def total_size(self) -> int:
        return sum(item.size for item in self.files)

    @property
    def reclaimable_size(self) -> int:
        return sum(item.size for group in self.duplicate_groups for item in group[1:])

    @property
    def category_sizes(self) -> Counter[str]:
        totals: Counter[str] = Counter()
        for item in self.files:
            totals[item.category] += item.size
        return totals


ProgressCallback = Callable[[int, str], None]


def _iter_files(root: Path, errors: list[str], is_cancelled: Callable[[], bool]) -> Iterable[FileInfo]:
    pending = [root]
    while pending and not is_cancelled():
        current = pending.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    if is_cancelled():
                        return
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            pending.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False):
                            stat = entry.stat(follow_symlinks=False)
                            path = Path(entry.path)
                            yield FileInfo(path, stat.st_size, stat.st_mtime, category_for(path))
                    except (OSError, PermissionError) as exc:
                        errors.append(f"{entry.path}: {exc}")
        except (OSError, PermissionError) as exc:
            errors.append(f"{current}: {exc}")


def _digest(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def scan_folder(
    root: str | Path,
    progress: ProgressCallback | None = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> ScanResult:
    root_path = Path(root).expanduser().resolve()
    if not root_path.is_dir():
        raise ValueError("Please choose a folder that exists.")

    cancelled = is_cancelled or (lambda: False)
    result = ScanResult(root=root_path)
    by_size: dict[int, list[FileInfo]] = defaultdict(list)

    for count, item in enumerate(_iter_files(root_path, result.errors, cancelled), start=1):
        result.files.append(item)
        if item.size > 0:
            by_size[item.size].append(item)
        if progress and (count == 1 or count % 100 == 0):
            progress(count, str(item.path))

    if cancelled():
        return result

    possible = [items for items in by_size.values() if len(items) > 1]
    checked = 0
    for same_size in possible:
        by_hash: dict[str, list[FileInfo]] = defaultdict(list)
        for item in same_size:
            if cancelled():
                return result
            try:
                by_hash[_digest(item.path)].append(item)
            except (OSError, PermissionError) as exc:
                result.errors.append(f"{item.path}: {exc}")
            checked += 1
            if progress and checked % 25 == 0:
                progress(len(result.files), f"Checking duplicates: {item.path.name}")
        for matches in by_hash.values():
            if len(matches) > 1:
                # Keep the oldest copy by default; every cleanup candidate remains user-reviewable.
                result.duplicate_groups.append(sorted(matches, key=lambda f: (f.modified, str(f.path))))

    result.duplicate_groups.sort(key=lambda group: group[0].size * (len(group) - 1), reverse=True)
    if progress:
        progress(len(result.files), "Scan complete")
    return result
