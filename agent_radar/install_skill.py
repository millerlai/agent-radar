"""agent-radar :: agent_radar.install_skill
========================================
Copy the bundled Claude Code skill template into the user's skills directory
so that ``/agent-radar-coach`` becomes available in any Claude Code session.

The skill itself lives under ``agent_radar/_skill_template/<skill-name>/`` and
is shipped as package data inside the wheel. This module just resolves where
the template is on disk and copies it to ``~/.claude/skills/<skill-name>/``.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

SKILL_NAME = "agent-radar-coach"
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


def install(dest_root: Path, force: bool = False, dry_run: bool = False) -> Path:
    """Install ``SKILL_NAME`` into ``<dest_root>/<SKILL_NAME>``.

    Returns the destination directory. Raises ``FileExistsError`` if the
    target exists and ``force`` is false.
    """
    src = _TEMPLATE_ROOT / SKILL_NAME
    if not src.is_dir():
        raise FileNotFoundError(
            f"skill template missing in this install: {src} "
            "(reinstall claude-agent-radar)")

    dst = dest_root / SKILL_NAME
    if dst.exists() and not force:
        raise FileExistsError(
            f"{dst} already exists. Re-run with --force to overwrite.")

    if dry_run:
        return dst

    if dst.exists():
        shutil.rmtree(dst)
    _copy_tree(src, dst)
    return dst


def main() -> int:
    ap = argparse.ArgumentParser(
        description=("Install the bundled Claude Code coach skill so "
                     "/agent-radar-coach is available in any session."))
    ap.add_argument(
        "--dest", default=None,
        help=("Skills root directory (default: ~/.claude/skills). "
              "The skill itself goes in <dest>/agent-radar-coach/."))
    ap.add_argument(
        "--force", action="store_true",
        help="Overwrite an existing agent-radar-coach skill at the destination.")
    ap.add_argument(
        "--dry-run", action="store_true",
        help="Print what would happen without copying.")
    args = ap.parse_args()

    dest_root = Path(args.dest).expanduser().resolve() if args.dest else _default_dest()

    try:
        dst = install(dest_root, force=args.force, dry_run=args.dry_run)
    except FileExistsError as exc:
        print(f"[err] {exc}", file=sys.stderr)
        return 1
    except FileNotFoundError as exc:
        print(f"[err] {exc}", file=sys.stderr)
        return 2

    verb = "would install" if args.dry_run else "installed"
    print(f"[ok] {verb} {SKILL_NAME} -> {dst}")
    if not args.dry_run:
        print("     Open any Claude Code session and try:  /agent-radar-coach")
    return 0


if __name__ == "__main__":
    sys.exit(main())
