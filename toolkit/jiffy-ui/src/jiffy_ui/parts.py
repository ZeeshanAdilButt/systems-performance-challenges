"""Find the labs: every folder in ``labs/`` with exactly one script that isn't a test.

The title and the question come from the lab's own README, so a new lab shows up on the
dashboard without touching this code.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Lab:
    id: str  # the folder name, "01-the-knee"
    title: str  # the README's first heading, "Lab 01 · The knee"
    question: str  # the README's **Question:** line
    script: Path


def find_root(start: Path) -> Path:
    """The repository: the first folder, from ``start`` upwards, that has a ``labs/``."""
    for folder in [start, *start.parents]:
        if (folder / "labs").is_dir():
            return folder
    raise FileNotFoundError(f"no labs/ folder in {start} or above it")


def find_labs(root: Path) -> list[Lab]:
    labs = []
    for folder in sorted(p for p in (root / "labs").iterdir() if p.is_dir()):
        scripts = [p for p in folder.glob("*.py") if not p.name.startswith("test_")]
        if len(scripts) != 1:
            continue
        title, question = folder.name, ""
        readme = folder / "README.md"
        if readme.exists():
            for line in readme.read_text(encoding="utf-8").splitlines():
                if line.startswith("# ") and title == folder.name:
                    title = line[2:].strip()
                elif line.startswith("**Question:**"):
                    question = line.removeprefix("**Question:**").strip()
                    break
        labs.append(Lab(folder.name, title, question, scripts[0]))
    return labs
