import os
from pathlib import Path

from clutter_coach.core import category_for, format_bytes, scan_folder


def test_format_bytes() -> None:
    assert format_bytes(0) == "0 B"
    assert format_bytes(1024) == "1.0 KB"
    assert format_bytes(5 * 1024 * 1024) == "5.0 MB"


def test_category_for() -> None:
    assert category_for(Path("photo.JPG")) == "Images"
    assert category_for(Path("notes.unknown")) == "Other"


def test_scan_finds_duplicates_and_protects_oldest(tmp_path: Path) -> None:
    older = tmp_path / "older.txt"
    newer = tmp_path / "newer.txt"
    unique = tmp_path / "unique.txt"
    older.write_text("same content", encoding="utf-8")
    newer.write_text("same content", encoding="utf-8")
    unique.write_text("different", encoding="utf-8")
    os.utime(older, (100, 100))
    os.utime(newer, (200, 200))

    result = scan_folder(tmp_path)

    assert len(result.files) == 3
    assert len(result.duplicate_groups) == 1
    assert result.duplicate_groups[0][0].path == older.resolve()
    assert result.duplicate_groups[0][1].path == newer.resolve()
    assert result.reclaimable_size == len("same content")


def test_same_size_different_content_is_not_duplicate(tmp_path: Path) -> None:
    (tmp_path / "one.bin").write_bytes(b"abc")
    (tmp_path / "two.bin").write_bytes(b"xyz")
    assert scan_folder(tmp_path).duplicate_groups == []


def test_symlinks_are_skipped(tmp_path: Path) -> None:
    target = tmp_path / "target.txt"
    target.write_text("hello", encoding="utf-8")
    link = tmp_path / "link.txt"
    try:
        link.symlink_to(target)
    except (OSError, NotImplementedError):
        return
    assert [item.path.name for item in scan_folder(tmp_path).files] == ["target.txt"]
