# agent-radar · AI Agent Capability Boundary Diagnostic

Detects the *capability boundary* of how an individual or a team uses the Claude Code
ecosystem. It scans filesystem fingerprints and quantifies a person's mastery of
CLAUDE.md, skills, MCP, hooks, subagents, and so on into six dimensions of maturity
score (0–100), then outputs an HTML radar-chart report.

**Two-layer measurement:**

- `agent-radar scan` measures *configuration completeness* (static fingerprints, six config dimensions)
- `agent-radar session` reads local `~/.claude/projects/*.jsonl` to measure *actual usage*
  (which tools, Skills, MCP servers actually fire, plus user correction rate)

The gap between the two is the most concrete improvement checklist. The repo itself
is also a Claude Code skill (see `SKILL.md`) — drop it into `~/.claude/skills/agent-radar/`
and it works out of the box.

## Core Idea

How well someone uses Claude Code gets imprinted into their filesystem and session
logs. This tool reads those fingerprints rather than monitoring conversation content.

- **Configuration completeness** (static) reflects how much you've *written down*: CLAUDE.md, skills, MCP.
- **Actual usage** (dynamic) reflects whether those configs *actually fire* during sessions.

Plenty of people write a thorough CLAUDE.md and install five MCP servers, but nothing
in those configs gets exercised during real sessions. That gap is exactly what
agent-radar visualizes — two overlaid radar polygons make it obvious.

## Six Config Dimensions (agent-radar scan)

| Dimension | What it detects |
|---|---|
| CLAUDE.md maturity | Presence, user/project layering, structured sections, imperative tone, concision, `@import` modularization, **size lint** |
| Skills usage | Whether skills exist, SKILL.md `description` trigger quality, progressive disclosure, **frontmatter & token-hygiene lint** |
| MCP integration | Number of MCP servers and breadth of types (data / saas / cloud / search / files) |
| Automation | hooks, subagents, custom slash commands, plugins |
| Context hygiene | user/project settings separation, shared vs. personal config distinction (gitignore), modular references |
| Iteration & maintenance | Whether configs have been repeatedly tuned over time (via git history) |

**Lint signals** are borrowed from [`felixgeelhaar/cclint`](https://github.com/felixgeelhaar/cclint)
and the agentskills.io Skill Linter (required frontmatter fields, line-count limits,
ASCII-art / decorative-content detection, oversized-CLAUDE.md warnings). They are
reimplemented in pure Python — no external dependencies.

The total score maps onto five levels: L0 (unaware) → L4 (mastery).

## Six Usage Dimensions (agent-radar session)

| Dimension | What it measures |
|---|---|
| tool_diversity | How many distinct tools have been called in the session |
| skill_triggered | How many times the `Skill` tool actually fired (signal that skill descriptions trigger) |
| mcp_triggered | How many `mcp__*` tool calls happened (signal that MCP is really used) |
| low_correction | Rate of corrective user messages (inverted — lower is better) |
| context_efficiency | Rate of repeated reads of the same file in one session (inverted) |
| session_volume | Session count and message volume (exposure baseline) |

## Install

**Prerequisites**: Python 3.8+ (standard library only — zero external deps).

### Option A · Install from PyPI (recommended)

The PyPI distribution name is **`claude-agent-radar`** (PyPI rejected
the shorter `agent-radar` because of a name collision with an unrelated
package). The CLI command and module are still `agent-radar` and
`agent_radar` respectively.

The two recommended install methods put `agent-radar.exe` on your
`PATH` automatically — no manual edits needed.

```bash
# Recommended · pipx (works out-of-the-box on every OS)
pipx install claude-agent-radar

# Recommended · uv tool (if you already use uv)
uv tool install claude-agent-radar

# Inside an activated virtualenv
python -m venv .venv
.venv\Scripts\activate           # Windows
source .venv/bin/activate        # macOS / Linux
pip install claude-agent-radar

# Editable install while hacking on the source
git clone https://github.com/millerlai/agent-radar
cd agent-radar
pip install -e .
```

After install, verify:

```bash
agent-radar --version   # prints e.g. `agent-radar 0.1.3`
agent-radar --help
```

If `--version` looks older than the [latest PyPI release](https://pypi.org/project/claude-agent-radar/),
upgrade with `pipx upgrade claude-agent-radar` or `uv tool upgrade claude-agent-radar`.

If `pipx` / `uv tool install` succeeded but `agent-radar` is still
`command not found`, your shell hasn't picked up the tool-bin dir yet
— run `pipx ensurepath` or `uv tool update-shell`, then reopen the
shell.

> ⚠️ **Avoid `pip install --user claude-agent-radar` on Windows.** The
> executable lands in `%APPDATA%\Python\Python3XX\Scripts\`, which is
> not on `PATH` by default, so `agent-radar` will print
> `command not found` immediately after install. Use `pipx` instead.

If for any reason the CLI isn't on `PATH`, `python -m agent_radar` is
a drop-in replacement (same arguments):

```bash
python -m agent_radar --help
python -m agent_radar scan ...     # same args as `agent-radar scan ...`
```

### Option B · Install as a Claude Code skill (recommended for daily use)

The repo itself is a Claude Code skill (the root contains `SKILL.md`). Copy
it into your user-space skills directory:

```bash
# macOS / Linux / Cygwin
cp -r /path/to/agent-radar ~/.claude/skills/agent-radar

# Windows PowerShell
Copy-Item -Recurse C:\path\to\agent-radar $env:USERPROFILE\.claude\skills\agent-radar
```

After that, in any Claude Code session, just say something like the
following — Claude will load the skill and walk you through the scan:

- "audit my Claude Code maturity"
- "scan this repo's Claude Code setup"
- "find the blind spots in my agent config"
- "benchmark our team's Claude Code adoption"

The skill invokes the same `agent-radar` CLI, so the package must be
installed first (`pipx install claude-agent-radar` is the path of
least resistance), or you must launch it via `python -m agent_radar`
from inside the skill directory.

## Run

### 30-second quick start

Scan the current repo + your user-space, generate the full HTML report
including the actual-usage radar. Run from the repo you want to scan:

```bash
agent-radar scan --include-home . -o scan.json
agent-radar session -o session.json
agent-radar report scan.json --session session.json -o report.html

# Open the report
open report.html        # macOS
xdg-open report.html    # Linux
start report.html       # Windows (PowerShell / cmd)
```

If `agent-radar` is not found, swap every `agent-radar` for
`python -m agent_radar` (same arguments). See the install notes above.

### Subcommands

| Subcommand | Purpose |
|---|---|
| `agent-radar scan` | Scan filesystem fingerprints (six config dimensions) |
| `agent-radar session` | Scan local `~/.claude/projects/*.jsonl` for actual-usage metrics |
| `agent-radar report` | Build single-file HTML radar report |
| `agent-radar usage` | Score OTel events into `usage.json` |
| `agent-radar merge` | Merge `scan.json` + `usage.json` into `merged.json` |

Each subcommand has its own `--help`. Long form: `python -m agent_radar <sub> ...`.

### Three scan scenarios

**Scenario 1 · Single repo (simplest)**

```bash
agent-radar scan /path/to/repo -o scan.json
agent-radar report scan.json -o report.html
```

**Scenario 2 · Personal full-body scan (includes user-space)**

Pulls `~/.claude/` into the scan so you can see user-level vs project-level
config separation:

```bash
agent-radar scan --include-home /path/to/repo -o scan.json
agent-radar report scan.json -o report.html
```

**Scenario 3 · Team benchmark (multi-repo)**

Scan many repos at once. The report auto-generates a ranking table:

```bash
agent-radar scan /repos/a /repos/b /repos/c -o scan.json
agent-radar report scan.json -o report.html
```

### Add actual-usage measurement (full two-layer analysis)

`agent-radar session` reads local `~/.claude/projects/*.jsonl` and emits
usage metrics — actual tool invocations, Skill firings, MCP calls, and
user-correction rate. Pair it with `agent-radar report --session` to get a
second radar in the HTML:

```bash
# 1. Scan all projects (defaults to ~/.claude/projects/)
agent-radar session -o session.json

# Or restrict to specific repos
agent-radar session /path/to/repo -o session.json

# 2. Cygwin / cross-OS: point at the actual projects dir
agent-radar session --projects-dir /c/Users/<you>/.claude/projects -o session.json

# 3. Build the two-layer radar report
agent-radar report scan.json --session session.json -o report.html
```

### Output files

| File | Produced by | Contents |
|---|---|---|
| `scan.json` | `agent-radar scan` | Config completeness: six dimension scores + per-signal detail |
| `session.json` | `agent-radar session` | Actual usage: per-project tool calls, Skill / MCP triggers, correction rate |
| `report.html` | `agent-radar report` | Single-file, offline-viewable HTML report with radars + ranking + accordions |

### Full CLI flags

```bash
agent-radar --help                  # list subcommands + version
agent-radar scan --help             # paths, --include-home, -o
agent-radar session --help          # paths, --projects-dir, -o
agent-radar report --help           # input, --session, --merged, --lang, -o
agent-radar usage --help            # --otel-log, --scan, --target, --account, ...
agent-radar merge --help            # scan.json, usage.json, -o
```

## Limitations

- Only effective for targets you have filesystem access to (your own / your team's repos).
- For strangers with only code or a conversation, reliable detection is impossible,
  and it edges into the gray area of surveilling others — not recommended.
- `agent-radar session` only reads local JSONL; cross-machine measurement needs OpenTelemetry (`agent-radar usage`).
- Correction rate is matched on literal patterns (no/don't/stop/不對/還原…); semantic
  corrections (a long explanation of why Claude was wrong) are not detected.
- The scoring weights are tunable heuristics — calibrate them against your team's
  reality before doing cross-person comparisons.

## License

Apache License 2.0 — see [LICENSE](LICENSE).

Copyright 2026 Miller Lai.
