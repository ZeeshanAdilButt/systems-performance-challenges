"""Find the parts: every ``challenges/challenge-*/part-*/`` folder with exactly one script
that isn't a test.

The title and the question come from the part's own README, so a new part (or a whole new
challenge) shows up on the dashboard without touching this code.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Part:
    id: str  # "challenge-1-latency-under-load/part-1-the-knee"
    title: str  # the README's first heading, "Part 1 · The knee"
    question: str  # the README's **Question:** line
    script: Path


def find_root(start: Path) -> Path:
    """The repository: the first folder, from ``start`` upwards, with a ``challenges/``."""
    for folder in [start, *start.parents]:
        if (folder / "challenges").is_dir():
            return folder
    raise FileNotFoundError(f"no challenges/ folder in {start} or above it")


def find_parts(root: Path) -> list[Part]:
    parts = []
    for folder in sorted(root.glob("challenges/challenge-*/part-*")):
        if not folder.is_dir():
            continue
        scripts = [p for p in folder.glob("*.py") if not p.name.startswith("test_")]
        if len(scripts) != 1:
            continue
        part_id = f"{folder.parent.name}/{folder.name}"
        title, question = folder.name, ""
        readme = folder / "README.md"
        if readme.exists():
            for line in readme.read_text(encoding="utf-8").splitlines():
                if line.startswith("# ") and title == folder.name:
                    title = line[2:].strip()
                elif line.startswith("**Question:**"):
                    question = line.removeprefix("**Question:**").strip()
                    break
        parts.append(Part(part_id, title, question, scripts[0]))
    return parts
