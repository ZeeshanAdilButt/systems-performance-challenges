"""Run every gate and print one report.

    ./verify            everything: lint, types, tests, and every lab in full
    ./verify --quick    the labs in their short form

Works the same on Windows, macOS and Linux: nothing here needs more than Python. Reports
land in .cache/reports/: verify.md, plus one report per lab. (A lab run on its own writes
results.md next to its script instead; verify leaves those alone.)
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORTS = ROOT / ".cache" / "reports"
PYTHON = sys.executable
LABS = [
    ("01 the knee", "labs/01-the-knee/knee.py"),
    ("02 averages lie", "labs/02-averages-lie/averages_lie.py"),
    ("03 tail at scale", "labs/03-tail-at-scale/tail_at_scale.py"),
    ("04 adaptive hedging", "labs/04-adaptive-hedging/adaptive_hedging.py"),
]


@dataclass
class Gate:
    name: str
    passed: bool
    seconds: float
    summary: str
    details: str = ""


@dataclass
class Report:
    gates: list[Gate] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(g.passed for g in self.gates)

    def markdown(self) -> str:
        lines = ["| gate | result | time | summary |", "|---|---|---|---|"]
        for g in self.gates:
            mark = "pass" if g.passed else "FAIL"
            lines.append(f"| {g.name} | {mark} | {g.seconds:.0f}s | {g.summary} |")
        for g in self.gates:
            if g.details:
                lines += ["", f"### {g.name}", "", g.details]
        return "\n".join(lines)


def run(argv: Sequence[str]) -> tuple[int, str]:
    proc = subprocess.run(
        argv, cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=False
    )
    return proc.returncode, proc.stdout + proc.stderr


def timed(name: str, body: Callable[[], tuple[bool, str, str]]) -> Gate:
    print(f"-> {name}", flush=True)
    started = time.monotonic()
    try:
        passed, summary, details = body()
    except Exception as exc:  # a crashed gate is a failed gate, with the reason
        passed, summary, details = False, f"crashed: {exc}", ""
    gate = Gate(name, passed, time.monotonic() - started, summary, details)
    print(f"   {'pass' if passed else 'FAIL'}: {summary}", flush=True)
    return gate


def last_line(output: str) -> str:
    lines = [line for line in output.strip().splitlines() if line.strip()]
    return lines[-1] if lines else ""


def ruff() -> tuple[bool, str, str]:
    code_check, out_check = run([PYTHON, "-m", "ruff", "check", "."])
    code_fmt, out_fmt = run([PYTHON, "-m", "ruff", "format", "--check", "."])
    passed = code_check == 0 and code_fmt == 0
    summary = f"{last_line(out_check)}; {last_line(out_fmt)}"
    return passed, summary, "" if passed else f"```\n{out_check}\n{out_fmt}\n```"


def mypy() -> tuple[bool, str, str]:
    """One run per project: each toolkit package and each lab is checked on its own."""
    groups = [[str(d / "src"), str(d / "tests")] for d in sorted(ROOT.glob("toolkit/jiffy-*"))]
    groups += [[str(d)] for d in sorted(ROOT.glob("labs/*")) if d.is_dir()]
    groups.append([str(ROOT / "tools")])
    files = 0
    failures = []
    for group in groups:
        code, out = run([PYTHON, "-m", "mypy", "--strict", "--explicit-package-bases", *group])
        found = re.search(r"in (\d+) source files?", out)
        files += int(found.group(1)) if found else 0
        if code != 0:
            failures.append(out[-3000:])
    summary = f"{len(groups)} projects, {files} files" + (", errors" if failures else ", clean")
    return not failures, summary, "\n".join(f"```\n{f}\n```" for f in failures)


def pytest() -> tuple[bool, str, str]:
    junit = REPORTS / "pytest.xml"
    code, out = run([PYTHON, "-m", "pytest", "-q", f"--junitxml={junit}"])
    suites: dict[str, list[int]] = {}
    failures: list[str] = []
    for case in ET.parse(junit).getroot().iter("testcase"):
        path = case.get("classname", "")
        tally = suites.setdefault(path.split(".")[0], [0, 0])
        problem = case.find("failure")
        if problem is None:
            problem = case.find("error")
        tally[0 if problem is None else 1] += 1
        if problem is not None:
            reason = (problem.get("message") or "").splitlines()[:1]
            failures.append(f"- {path}::{case.get('name')}: {' '.join(reason)[:300]}")
    details = "\n".join(
        f"- {area}: {ok} passed" + (f", {bad} failed" if bad else "")
        for area, (ok, bad) in sorted(suites.items())
    )
    if failures:
        details += "\n\nFailed:\n\n" + "\n".join(failures)
    return code == 0, last_line(out), details


def lab(script: str, quick: bool) -> Callable[[], tuple[bool, str, str]]:
    def body() -> tuple[bool, str, str]:
        report = REPORTS / f"{Path(script).stem}.md"
        args = [PYTHON, script, "--out", str(report)] + (["--quick"] if quick else [])
        code, out = run(args)
        text = report.read_text(encoding="utf-8") if report.exists() else out[-3000:]
        return code == 0, f"report in .cache/reports/{report.name}", text

    return body


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="verify")
    parser.add_argument("--quick", action="store_true", help="short lab runs")
    parser.add_argument("--skip", action="append", default=[], help="gate name prefix to skip")
    args = parser.parse_args(argv)
    REPORTS.mkdir(parents=True, exist_ok=True)
    plan: list[tuple[str, Callable[[], tuple[bool, str, str]]]] = [
        ("ruff (lint and format)", ruff),
        ("mypy --strict", mypy),
        ("tests (unit, property, real server)", pytest),
    ]
    plan += [(f"lab {name}", lab(script, args.quick)) for name, script in LABS]
    report = Report()
    for name, body in plan:
        if any(name.startswith(s) for s in args.skip):
            continue
        report.gates.append(timed(name, body))

    text = report.markdown()
    (REPORTS / "verify.md").write_text(text + "\n", encoding="utf-8")
    (REPORTS / "verify.json").write_text(json.dumps([asdict(g) for g in report.gates], indent=2))
    print("\n" + text)
    verdict = "ALL GATES PASSED" if report.passed else "SOME GATES FAILED"
    print(f"\n{verdict} (.cache/reports/verify.md)")
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
