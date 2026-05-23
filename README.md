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

### Option A · Install from PyPI / source (recommended)

Works with `pip`, `uv`, and `poetry`. Once installed, the `agent-radar`
console command is on your `PATH`.

```bash
# pip
pip install agent-radar

# uv
uv pip install agent-radar
# or, as a uv-managed tool
uv tool install agent-radar

# poetry
poetry add agent-radar

# Local / editable install while hacking on the source
git clone <repo-url> agent-radar
cd agent-radar
pip install -e .
agent-radar --help
```

You can also run it without installing:

```bash
python -m agent_radar --help     # from a checkout of the repo
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
`pip install`-ed first (or you must launch it via `python -m agent_radar`
from inside the skill directory).

## Run

### 30-second quick start

Scan the current repo + your user-space, generate the full HTML report
including the actual-usage radar:

```bash
agent-radar scan --include-home . -o scan.json
agent-radar session -o session.json
agent-radar report scan.json --session session.json -o report.html
open report.html        # macOS
xdg-open report.html    # Linux
start report.html       # Windows (PowerShell / cmd)
```

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
