"""agent-radar console entry point.

Dispatches ``agent-radar <subcommand> [options]`` to the per-tool ``main()``
in each module. Each subcommand keeps its own argparse spec — this file is
deliberately just a thin router so per-tool help (``--help``) keeps working
verbatim.
"""

from __future__ import annotations

import importlib
import sys
from typing import Sequence

from . import __version__


SUBCOMMANDS: dict[str, tuple[str, str]] = {
    "scan":          ("agent_radar.scanner",
                      "Scan filesystem fingerprints (CLAUDE.md / skills / MCP / hooks / ...)"),
    "session":       ("agent_radar.session_scanner",
                      "Scan local session JSONL for actual-usage metrics"),
    "report":        ("agent_radar.report",
                      "Build HTML radar report from scan / session / merged JSON"),
    "usage":         ("agent_radar.usage.__main__",
                      "Score OTel events into usage.json"),
    "merge":         ("agent_radar.usage.merge",
                      "Merge scan.json + usage.json into merged.json"),
    "install-skill": ("agent_radar.install_skill",
                      "Install the /agent-radar-coach Claude Code skill into ~/.claude/skills/"),
}


def _print_help() -> None:
    print("usage: agent-radar <subcommand> [options]")
    print()
    print(f"agent-radar {__version__} — AI Agent capability boundary diagnostic.")
    print()
    print("Subcommands:")
    width = max(len(name) for name in SUBCOMMANDS)
    for name, (_, desc) in SUBCOMMANDS.items():
        print(f"  {name.ljust(width)}  {desc}")
    print()
    print("Run `agent-radar <subcommand> --help` for per-command options.")


def main(argv: Sequence[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)

    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        _print_help()
        return 0
    if argv[1] in ("-V", "--version"):
        print(f"agent-radar {__version__}")
        return 0

    sub = argv[1]
    if sub not in SUBCOMMANDS:
        print(f"agent-radar: unknown subcommand {sub!r}", file=sys.stderr)
        print(file=sys.stderr)
        _print_help()
        return 2

    module_name = SUBCOMMANDS[sub][0]
    module = importlib.import_module(module_name)

    # Hand the delegated parser a clean prog name + args.
    sys.argv = [f"agent-radar {sub}", *argv[2:]]
    rv = module.main()
    return 0 if rv is None else int(rv)


if __name__ == "__main__":
    sys.exit(main())
