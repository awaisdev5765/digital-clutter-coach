"""Build Digital Clutter Coach for the current operating system."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def main() -> None:
    icon = ROOT / "assets" / ("app-icon.ico" if sys.platform == "win32" else "app-icon.icns")
    if not icon.exists():
        raise SystemExit(f"Missing application icon: {icon}")

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        "Digital Clutter Coach",
        "--icon",
        str(icon),
        "--add-data",
        f"{ROOT / 'assets' / 'app-icon.png'}{os.pathsep}assets",
        str(ROOT / "run.py"),
    ]
    subprocess.run(command, cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
