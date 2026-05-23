# agent-radar · AI Agent Capability Boundary Diagnostic

Detects the *capability boundary* of how an individual or a team uses the Claude Code
ecosystem. It scans filesystem fingerprints and quantifies a person's mastery of
CLAUDE.md, skills, MCP, hooks, subagents, and so on into six dimensions of maturity
score (0–100), then outputs an HTML radar-chart report.

**Two-layer measurement:**

- `scanner.py` measures *configuration completeness* (static fingerprints, six config dimensions)
- `session_scanner.py` reads local `~/.claude/projects/*.jsonl` to measure *actual usage*
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

## Six Config Dimensions (scanner.py)

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

## Six Usage Dimensions (session_scanner.py)

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

### Option A · Clone and run directly

For people who want to run scans themselves, read the source, or tune the
scoring weights.

```bash
git clone <repo-url> agent-radar
cd agent-radar
python3 scanner.py --help   # smoke-test
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

### Python command cheat-sheet (cross-OS)

| Environment | Python command |
|---|---|
| macOS / Linux | `python3 scanner.py ...` |
| Windows (PowerShell / cmd) | `python scanner.py ...` |
| Cygwin (no native cygwin python) | `/c/Python313/python.exe scanner.py ...` or switch to PowerShell |

Examples below use `python3`; Windows users substitute `python`.

## Run

### 30-second quick start

Scan the current repo + your user-space, generate the full HTML report
including the actual-usage radar:

```bash
python3 scanner.py --include-home . -o scan.json
python3 session_scanner.py -o session.json
python3 report.py scan.json --session session.json -o report.html
open report.html        # macOS
xdg-open report.html    # Linux
start report.html       # Windows (PowerShell / cmd)
```

### Three scan scenarios

**Scenario 1 · Single repo (simplest)**

```bash
python3 scanner.py /path/to/repo -o scan.json
python3 report.py scan.json -o report.html
```

**Scenario 2 · Personal full-body scan (includes user-space)**

Pulls `~/.claude/` into the scan so you can see user-level vs project-level
config separation:

```bash
python3 scanner.py --include-home /path/to/repo -o scan.json
python3 report.py scan.json -o report.html
```

**Scenario 3 · Team benchmark (multi-repo)**

Scan many repos at once. The report auto-generates a ranking table:

```bash
python3 scanner.py /repos/a /repos/b /repos/c -o scan.json
python3 report.py scan.json -o report.html
```

### Add actual-usage measurement (full two-layer analysis)

`session_scanner.py` reads local `~/.claude/projects/*.jsonl` and emits
usage metrics — actual tool invocations, Skill firings, MCP calls, and
user-correction rate. Pair it with `report.py --session` to get a second
radar in the HTML:

```bash
# 1. Scan all projects (defaults to ~/.claude/projects/)
python3 session_scanner.py -o session.json

# Or restrict to specific repos
python3 session_scanner.py /path/to/repo -o session.json

# 2. Cygwin / cross-OS: point at the actual projects dir
python3 session_scanner.py --projects-dir /c/Users/<you>/.claude/projects -o session.json

# 3. Build the two-layer radar report
python3 report.py scan.json --session session.json -o report.html
```

### Output files

| File | Produced by | Contents |
|---|---|---|
| `scan.json` | `scanner.py` | Config completeness: six dimension scores + per-signal detail |
| `session.json` | `session_scanner.py` | Actual usage: per-project tool calls, Skill / MCP triggers, correction rate |
| `report.html` | `report.py` | Single-file, offline-viewable HTML report with radars + ranking + accordions |

### Full CLI flags

```bash
python3 scanner.py --help          # paths, --include-home, -o
python3 session_scanner.py --help  # paths, --projects-dir, -o
python3 report.py --help           # input, --session, -o
```

## Limitations

- Only effective for targets you have filesystem access to (your own / your team's repos).
- For strangers with only code or a conversation, reliable detection is impossible,
  and it edges into the gray area of surveilling others — not recommended.
- `session_scanner.py` only reads local JSONL; cross-machine measurement needs OpenTelemetry.
- Correction rate is matched on literal patterns (no/don't/stop/不對/還原…); semantic
  corrections (a long explanation of why Claude was wrong) are not detected.
- The scoring weights are tunable heuristics — calibrate them against your team's
  reality before doing cross-person comparisons.
