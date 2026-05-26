"""agent-radar :: agent_radar.install_skill
========================================
Copy the bundled Claude Code skills into the user's skills directory so
``/agent-radar-coach`` and ``/agent-radar-feedback`` become available in any
Claude Code session.

The skill bodies live under ``agent_radar/_skill_template/<skill-name>/`` and
ship as package data inside the wheel. This module resolves where each
template is on disk and copies it to ``~/.claude/skills/<skill-name>/``.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from typing import List

# Tuple of bundled skills. Order matters for CLI output / install order.
SKILL_NAMES: tuple = ("agent-radar-coach", "agent-radar-feedback")
_TEMPLATE_ROOT = Path(__file__).parent / "_skill_template"


def _default_dest() -> Path:
    return Path.home() / ".claude" / "skills"


def _copy_tree(src: Path, dst: Path) -> None:
    """Plain recursive copy. shutil.copytree refuses if dst exists on <3.8."""
    dst.mkdir(parents=True, exist_ok=True)
    for item in src.iterdir():
        target = dst / item.name
        if item.is_dir():
            _copy_tree(item, target)
        else:
            shutil.copy2(item, target)


def install(dest_root: Path, force: bool = False, dry_run: bool = False) -> List[Path]:
    """Install every skill in ``SKILL_NAMES`` under ``dest_root``.

    Returns the list of destination directories. Raises ``FileExistsError`` on
    the first target that already exists when ``force`` is false — so callers
    get an all-or-nothing install rather than a half-applied state.
    """
    sources = []
    for name in SKILL_NAMES:
        src = _TEMPLATE_ROOT / name
        if not src.is_dir():
            raise FileNotFoundError(
                f"skill template missing in this install: {src} "
                "(reinstall claude-agent-radar)")
        sources.append((name, src))

    # Conflict-check ALL targets first so we don't partially install before
    # erroring on the second skill.
    targets = []
    for name, src in sources:
        dst = dest_root / name
        if dst.exists() and not force:
            raise FileExistsError(
                f"{dst} already exists. Re-run with --force to overwrite.")
        targets.append((src, dst))

    if dry_run:
        return [dst for _, dst in targets]

    installed: List[Path] = []
    for src, dst in targets:
        if dst.exists():
            shutil.rmtree(dst)
        _copy_tree(src, dst)
        installed.append(dst)
    return installed


def main() -> int:
    ap = argparse.ArgumentParser(
        description=("Install the bundled Claude Code skills so "
                     "/agent-radar-coach and /agent-radar-feedback are "
                     "available in any session."))
    ap.add_argument(
        "--dest", default=None,
        help=("Skills root directory (default: ~/.claude/skills). "
              "Each skill goes in <dest>/<skill-name>/."))
    ap.add_argument(
        "--force", action="store_true",
        help="Overwrite existing skill directories at the destination.")
    ap.add_argument(
        "--dry-run", action="store_true",
        help="Print what would happen without copying.")
    args = ap.parse_args()

    dest_root = Path(args.dest).expanduser().resolve() if args.dest else _default_dest()

    try:
        installed = install(dest_root, force=args.force, dry_run=args.dry_run)
    except FileExistsError as exc:
        print(f"[err] {exc}", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(f"[err] {exc}", file=sys.stderr)
        return 2

    verb = "would install" if args.dry_run else "installed"
    for dst in installed:
        print(f"[ok] {verb} {dst.name} -> {dst}")
    if not args.dry_run:
        print("     Open any Claude Code session and try:")
        print("       /agent-radar-coach    — diagnose + close gaps")
        print("       /agent-radar-feedback — share what you learned")
    return 0


if __name__ == "__main__":
    sys.exit(main())
