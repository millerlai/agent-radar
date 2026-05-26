# agent-radar · Activation Gap Diagnostic for Claude Code

**The one thing this tool does that nothing else can:** it sees both what you
*configured* on disk AND what *actually fires* inside your Claude Code sessions
— and the gap between the two is your improvement headroom.

- `agent-radar scan` reads filesystem fingerprints → **configured side** of five axes
- `agent-radar session` reads local `~/.claude/projects/*.jsonl` → **activated side** of the same axes
- `agent-radar merge` + `agent-radar report` → HTML showing the activation gap

The companion `/agent-radar-coach` skill (install via `agent-radar install-skill`)
walks you through closing the biggest gaps one at a time, evidence-driven, ask-before-edit.

## See a sample report

Sample reports rendered from a real repo are checked into this repo —
GitHub doesn't preview HTML inline, so view them through a CDN:

- 🇬🇧 **English** · [report.en.html](https://raw.githack.com/millerlai/agent-radar/main/report.en.html)
- 🇹🇼 **繁體中文** · [report.zh.html](https://raw.githack.com/millerlai/agent-radar/main/report.zh.html)

Each shows the dual-track radar, the bidirectional Top Gaps (click each row
to expand the underlying configured + activated findings), and per-target detail.

## Core Idea

Most "Claude Code health" tools stop at "did you write a CLAUDE.md?" That's
fingerprint detection — necessary but not interesting. What's interesting is
that **plenty of people write a thorough CLAUDE.md and install five MCP servers,
but nothing in those configs gets exercised during real sessions**. That gap
is what agent-radar visualizes — two overlaid radar polygons make it obvious.

agent-radar does NOT try to grade the *quality* of your CLAUDE.md — heuristics
like "count of imperative verbs" don't actually measure quality, they just
pretend to. Quality judgement is interpretive and lives in the coach skill,
where Claude can read the content and reason about it.

## Five Axes

For each axis, scan produces a **Configured** score (0–100) and session produces
an **Activated** score (0–100). The gap is improvement headroom.

| Axis | Configured (`scan`) | Activated (`session`) |
|---|---|---|
| `claude_md` | Presence, size, `@import` refs, **iteration evidence** (git commits + content patterns like "lessons learned / do not repeat / dated rules") | `(1 - correction_rate) × 100` — low correction rate = CLAUDE.md is guiding effectively |
| `skills` | SKILL.md count + lint hygiene (frontmatter compliance, no ASCII-art banners, size limits) | `Skill` tool dispatch count × 10 |
| `mcp` | Configured server count + category breadth (data / saas / cloud / search / files) | `mcp__*` tool call count × 8 |
| `automation` | Hooks, subagents, custom commands, plugins (fact counts) | `Agent` tool dispatches × 10 (hooks/commands aren't visible in JSONL) |
| `context_hygiene` | User/project split + `settings.local.json` gitignore + `@import` modularization | Blend: `(1 - read_repeat_rate) × 50` + `@-mention_rate × 50` |

**Lint signals** are borrowed from [`felixgeelhaar/cclint`](https://github.com/felixgeelhaar/cclint)
and the agentskills.io Skill Linter (required frontmatter fields, line-count limits,
ASCII-art / decorative-content detection, oversized-CLAUDE.md warnings),
reimplemented in pure Python — no external dependencies.

> **Migrating from 0.1.x?** The `iteration` dimension is gone — folded into
> `claude_md` as a fact-based sub-signal (git commit count + content-regex
> patterns). The 0-100 "overall maturity" score is also gone; the same number
> still exists but is now framed as "Configured Coverage" not "Maturity".
> Heuristic sub-checks (imperative-pattern count, structure-headers-score,
> word-count concise bucket, skills description quality grade) were removed —
> they pretended to measure quality the CLI cannot actually evaluate.

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

Compare against the [latest PyPI release](https://pypi.org/project/claude-agent-radar/);
if you're behind, see **Upgrade to the latest version** below.

### Upgrade to the latest version

If you installed previously, these commands force a refresh to the newest
published wheel:

```bash
# pipx
pipx upgrade claude-agent-radar

# uv tool — upgrade in place
uv tool install --upgrade claude-agent-radar
# uv tool — force a clean reinstall (use if --upgrade didn't pick up
# the newest release, or after a yanked / re-published version)
uv tool install --reinstall claude-agent-radar

# pip inside a venv
pip install --upgrade claude-agent-radar
```

Confirm with `agent-radar --version` afterwards.

**One-shot "always latest" via uvx** — if you'd rather not keep a
persistent install at all, run it ephemerally:

```bash
uvx claude-agent-radar@latest --help
uvx claude-agent-radar@latest scan --include-home . -o scan.json
```

The `@latest` suffix bypasses uv's resolver cache so you never end up
pinned to a stale version.

**Refresh the bundled skills after upgrade.** The two skills
(`/agent-radar-coach`, `/agent-radar-feedback`) ship inside the wheel but
were copied into `~/.claude/skills/` at first install — upgrading the
package does **not** overwrite those copies. Re-run:

```bash
agent-radar install-skill --force
```

### Install the bundled skills (optional but recommended)

```bash
agent-radar install-skill
```

This copies two Claude Code skills into `~/.claude/skills/`:

- **`/agent-radar-coach`** walks you through your `scan` / `session` /
  `merged` results and applies targeted fixes one at a time
  (evidence-driven, ask-before-edit).
- **`/agent-radar-feedback`** closes the loop back to **us**. Claude itself
  drafts an `Improvement.MD` of *tool-level* suggestions for the coach skill
  (workflow, scoring, playbook depth, new features), you steer with a
  multi-select + free-text gate, and — only on your explicit "send" — it
  files a GitHub issue at
  [`millerlai/agent-radar`](https://github.com/millerlai/agent-radar/issues).
  The proposal is about **the tool**, never about your repo content, paths,
  or session data; any private content in your free-text is redacted and
  shown back for approval before saving.

Re-run with `--force` to overwrite existing copies, or `--dest <dir>` to
install elsewhere.

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
agent-radar scan --include-home . -o scan.json    # in the current repo
agent-radar session -o session.json
agent-radar report scan.json --session session.json -o report.html

# Open the report
open report.html        # macOS
xdg-open report.html    # Linux
start report.html       # Windows (PowerShell / cmd)
```

**Multi-repo variant** — pass any number of paths to `scan`; the report
auto-generates a per-target comparison so you can benchmark a whole team:

```bash
agent-radar scan --include-home /repos/a /repos/b /repos/c -o scan.json
agent-radar session -o session.json
agent-radar report scan.json --session session.json -o report.html
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

**Scenario 4 · Run in a repos-parent directory (interactive picker)**

If the path you pass is **not** itself a Claude Code project (no
`CLAUDE.md` and no `.claude/` at the top) but contains scannable
subdirectories (any of `.git/`, `.claude/`, or `CLAUDE.md`), agent-radar
opens a keyboard-driven checkbox picker. Dirs that already show Claude
Code signal (`CLAUDE.md` or `.claude/`) are **pre-selected**; pure git
repos with no Claude signal are listed but unchecked, so you decide
whether to include them:

```text
[i] /home/you/projects has 37 candidate dirs (28 selected):
  > [X] agent-radar              (CLAUDE.md, .claude/, git)
    [X] ai-hedge-func-claude-cli (CLAUDE.md, .claude/, git)
    [ ] ai-hedge-fund            (git)
    [X] auto-package-migration   (CLAUDE.md, .claude/, git)
       ↓ 32 more below
  ↑/↓ move | Space toggle | Enter confirm | a all | n none | q quit
```

Keybindings:
- **↑ / ↓** — move cursor (wraps around)
- **Space** — toggle checkbox at cursor
- **Enter** — confirm and scan the currently-selected set
- **a / n** — select all / select none
- **q / Esc** — quit without scanning
- **Ctrl-C** — same as quit

Long lists are paginated to fit your terminal height.

If stdin isn't a TTY (CI, pipes):
- Dirs with Claude Code signal are auto-scanned (with a summary printed to stderr).
- If no candidate has any Claude signal, the path is skipped with a warning
  so the user can pass repos explicitly.

On rare platforms without `msvcrt` / `termios` (the picker's only deps —
both are part of the Python stdlib), agent-radar falls back to a simpler
text-based picker that accepts comma-separated indices.

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

### Advanced · OpenTelemetry path (cross-machine, hooks / plugins)

`agent-radar usage` is the **OpenTelemetry-based** alternative to
`agent-radar session`. It reads a stream of OTel events emitted by Claude
Code and produces `usage.json` with the same shape `merge` expects. Most
people don't need this — `agent-radar session` already covers ~90% of
useful signals from JSONL with zero setup. Use the OTel path only when
you want:

- **Hook trigger telemetry** (JSONL doesn't expose hook firings)
- **Plugin load events**
- **MCP connection health** (connected / failed)
- **Cross-machine aggregation** via a central OTel collector
- **Per-account filtering** on a shared machine

| | `agent-radar session` | `agent-radar usage` |
|---|---|---|
| Setup | None — just run | Enable Claude Code telemetry first |
| Source | `~/.claude/projects/*.jsonl` | OTel events log (console exporter) |
| Hook / plugin signals | ✗ | ✓ |
| Cross-machine | Local only | Yes (via central collector) |

#### Step 1 · Enable Claude Code OTel telemetry

Set these environment variables before launching `claude`. The simplest
setup is the **console exporter** — Claude Code writes a stream of JSON
events to `stderr`, which you redirect to a log file.

**macOS / Linux (bash / zsh):**

```bash
export CLAUDE_CODE_ENABLE_TELEMETRY=1
export OTEL_LOGS_EXPORTER=console
export OTEL_METRICS_EXPORTER=console
export OTEL_LOG_TOOL_DETAILS=1
```

**Windows PowerShell:**

```powershell
$env:CLAUDE_CODE_ENABLE_TELEMETRY = "1"
$env:OTEL_LOGS_EXPORTER          = "console"
$env:OTEL_METRICS_EXPORTER       = "console"
$env:OTEL_LOG_TOOL_DETAILS       = "1"
```

To make this permanent, add the exports to your shell rc file
(`.bashrc`, `.zshrc`, PowerShell `$PROFILE`).

#### Step 2 · Accumulate events into a log file

Telemetry only fires while Claude Code is running. To accumulate signal
worth analyzing, redirect `stderr` to an append-only log:

```bash
mkdir -p ~/.agent-radar

# macOS / Linux — append every Claude Code session into the same log
claude 2>> ~/.agent-radar/otel-events.log
```

```powershell
# Windows PowerShell — same idea
New-Item -ItemType Directory -Force "$env:USERPROFILE\.agent-radar" | Out-Null
claude 2>> "$env:USERPROFILE\.agent-radar\otel-events.log"
```

A single short conversation produces a few KB; meaningful aggregation
usually needs **at least 1-2 weeks of normal usage**. If you only care
about a recent window, use `--since` / `--until` later (see below) to
slice the log without rotating it.

**Log hygiene:** the file grows append-only and is never trimmed by
Claude Code. Rotate periodically (e.g. weekly): `mv otel-events.log
otel-events.$(date +%Y%m%d).log && : > otel-events.log` — and feed the
rotated copy into a fresh `agent-radar usage` run.

**Production-grade alternative:** instead of the console exporter, point
`OTEL_*_EXPORTER` at a real OTel collector (Jaeger, Honeycomb, Grafana
Tempo, …). For team rollups, that collector becomes the single source
agent-radar reads from. The console-to-file path documented here is the
minimum-viable starting point.

#### Step 3 · Score the log into usage.json

Once the log has some events:

```bash
# Recommended: pair with scan.json so ratios get proper denominators
# (e.g. "5 MCP servers configured, 2 actually invoked" instead of "2 invocations")
agent-radar usage \
    --otel-log ~/.agent-radar/otel-events.log \
    --scan scan.json \
    --target my-repo \
    -o usage.json

# Minimal: no scan context — ratios fall back to raw event counts
agent-radar usage --otel-log ~/.agent-radar/otel-events.log -o usage.json
```

Useful optional flags:

| Flag | Effect |
|---|---|
| `--scan scan.json` | Provide configured-side denominators so usage ratios make sense |
| `--target <name>` | Pick the target from `scan.json` to align with (required if scan has >1 target) |
| `--account <email-or-uuid>` | Only count events whose `user.email` / `user.account_uuid` matches — useful on shared machines |
| `--since 2026-05-01T00:00:00Z` | ISO time lower bound (inclusive) |
| `--until 2026-05-25T23:59:59Z` | ISO time upper bound (inclusive) |

#### Step 4 · Merge with scan and render

The OTel path joins back into the standard pipeline — `merge` then
`report` work the same as the JSONL path:

```bash
agent-radar merge scan.json usage.json -o merged.json
agent-radar report --merged merged.json -o report.html
```

The HTML radar now reflects activation as measured via OTel (so the
`automation` axis on the activated side picks up real hook firings,
which `session` can't see).

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

## Feedback

The fastest way to send tool-level improvements back to us is the
`/agent-radar-feedback` skill (installed alongside the coach skill via
`agent-radar install-skill`). It has Claude draft an `Improvement.MD`
proposal targeting the coach skill's workflow, scoring, playbooks, and
feature gaps; you steer with a multi-select + free-text gate; it files
the proposal as a GitHub issue on this repo — **no PII, no repo content,
no session data leaves your machine**.

You can of course also open issues manually:
[github.com/millerlai/agent-radar/issues](https://github.com/millerlai/agent-radar/issues).

## License

Apache License 2.0 — see [LICENSE](LICENSE).

Copyright 2026 Miller Lai.
