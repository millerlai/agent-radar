---
name: agent-radar-coach
description: Diagnose and close the Activation Gap in the user's Claude Code setup using agent-radar. Five axes — CLAUDE.md, Skills, MCP, Automation, Context Hygiene — each compared as Configured (filesystem fingerprint) vs Activated (session JSONL telemetry). Gap = configured but unused = improvement headroom. Use when the user says "improve my Claude Code setup", "fix my agent-radar gaps", "coach me through this report", "tune my CLAUDE.md / skills / MCP / hooks", "raise my activation rate", "what should I do about this report", or hands you a scan.json / session.json / merged.json / report.html and asks what to change next. Also triggers on Chinese phrases: "幫我改善 Claude Code 設定 / agent-radar 報告 / CLAUDE.md / skills / MCP".
---

# agent-radar-coach

The user's `agent-radar` output is in front of you. Your job is **not** to lecture about maturity scores — they don't exist in 0.2.0. Your job is to turn one specific gap number into one specific edit in their repo.

The product thesis is: **agent-radar uniquely sees both what you configured AND what actually fires in sessions. The gap is the improvement.** Coach against that gap.

## Workflow

1. **Gather data.** If the user hasn't produced JSON, run:
   ```bash
   agent-radar scan <repo-path> -o scan.json
   agent-radar session -o session.json
   agent-radar merge scan.json session.json -o merged.json
   ```
   If `merged.json` exists, read it directly — don't re-run.

2. **Pick targets.** Read `targets[*].top_gaps` from `merged.json` directly — `merge` already applied the noise floor (`|gap| > 10` *and* `gap_ratio > 0.3`, where `gap_ratio = |gap| / max(config, usage, 1)`). Take the first 3 rows. Each row carries `direction`:
   - `direction = "under"` → configured > activated → the canonical underused axis (most common case).
   - `direction = "over"` → activated > configured → user is doing something heavily that isn't represented in config (often a sign that a repeated manual pattern could be sunk into a command/subagent).
   Skip axes where:
   - Not in `top_gaps` (filtered by the relative threshold — already aligned).
   - `usage` is `null` (no session data — flag it but don't coach).
   - `sessions < 3` in the source `session.json` (too thin to judge — tell the user to come back).

3. **Coach one gap at a time.** For each chosen axis:
   - State **the specific number**: "Configured X, Activated Y, Gap = X−Y".
   - Quote **specific evidence** from the findings (file path, count, tool name — straight from JSON; never invent).
   - Propose **the smallest edit** that moves the activated side up.
   - Wait for user "go".
   - Make the edit (Edit / Write).
   - Re-run `agent-radar scan` + `session` + `merge` on the affected target.
   - Report the new gap. One line. No fluff.

## Principles

- **Evidence over advice.** Never "consider adding skills"; instead "your `skills.configured = 70` (5 SKILL.md installed) but `skills.activated = 0` over 47 sessions — `<name>` has a 12-char description, that's almost certainly why it never triggers."
- **Smallest viable change.** A 3-line addition to CLAUDE.md beats a rewrite. A description tweak beats authoring a new skill.
- **One change per turn.** Re-scan between changes so the user sees cause-and-effect.
- **Ask before editing.** This is the user's config; you propose, they approve, you apply.
- **Don't invent.** If a number isn't in the JSON, you cannot use it. No vibes.

## Per-axis playbook

For each axis, the goal is to move the **activated** number up (rarely: lower the configured number when the user wants to remove dead config).

### 1. `claude_md`

| | Source |
|---|---|
| Configured | scan findings: `scan.claude_md.exists`, `.import`, `.lint_size`, `.iteration` |
| Activated | session finding `session.claude_md.guidance` = `(1 - correction_rate) × 100` |

**Gap means**: CLAUDE.md exists but Claude keeps getting corrected in sessions — CLAUDE.md isn't doing its job.

**Fix flow**:
1. Pull the actual user-correction messages from `~/.claude/projects/<encoded>/<session>.jsonl` (filter by `CORRECTION_RE` or just `^no\b` / `不對` patterns).
2. Bucket them — typical groups: tone/style, missing facts, repeated tool-misuse.
3. Pick the **most frequent bucket**. Propose 1-3 imperative lines to add to CLAUDE.md addressing it.
4. Apply, re-scan, show the new correction-rate prediction.

If `scan.claude_md.iteration.detail` shows `commits: 0, hits: 0`, also flag: **no iteration evidence at all** — this CLAUDE.md was written once and never refined. Coach them to add a "Lessons learned" or "Mistakes to avoid" section seeded from the corrections you just found.

**If `direction = over`** (configured side thin, but correction rate already low): the user is keeping Claude on track via in-session prompting instead of CLAUDE.md. Pull 5–10 substantive user messages from recent JSONL that read like guidance ("always use X", "don't do Y", "we use snake_case here"). Propose folding the recurring ones into CLAUDE.md so they stop having to be re-typed every session.

### 2. `skills`

| | Source |
|---|---|
| Configured | scan: count of SKILL.md found + lint hygiene |
| Activated | session: `Skill` tool dispatches × 10, capped 100 |

**Gap means**: skills are installed but rarely / never triggered. The almost-always-cause is a weak `description:` field that the model can't match against user prompts.

**Fix flow**:
1. List the installed skills (glob `~/.claude/skills/*/SKILL.md` + `.claude/skills/*/SKILL.md`).
2. Read each skill's frontmatter `description`. Rank by trigger phrase concreteness:
   - Strong: lists 3+ specific user phrases ("when the user says X / asks for Y / hands you Z")
   - Weak: vague verbs only ("manages files", "helps with code")
3. Pick the weakest one. Rewrite its description with explicit trigger phrases borrowed from real user-message patterns in the JSONL.
4. Apply, suggest the user start one test session that should trigger it, re-measure.

**If `direction = over`** (few skills installed but Skill tool fires often): the existing skills are pulling weight. Two productive moves: (a) audit lint debt on the active skill — `scan.skills.lint_*` findings — and clean them; (b) look at the user-message patterns that trigger the working skill, and propose authoring 1 more skill in an adjacent category that those patterns hint at.

### 3. `mcp`

| | Source |
|---|---|
| Configured | scan: server count + category breadth |
| Activated | session: `mcp__*` tool calls × 8, capped 100 |

**Gap means**: you configured MCP servers but they're not being invoked.

**Fix flow**:
1. List configured servers from `.mcp.json` / `.claude/settings.json` `mcpServers`.
2. Cross-reference against actual `mcp__*` tool names seen in JSONL — flag the **configured-but-unused** servers by name.
3. Two paths:
   - **Remove**: if the server isn't useful to the user's actual workflow, suggest pruning it from config (reduces noise, frees connection limits).
   - **Activate**: if it should be useful, the user usually doesn't know it can be called. Add a 1-line CLAUDE.md hint like "Use mcp__linear__list_issues to check ticket status".

**If `direction = over`** (few servers configured but `mcp__*` calls heavy): the user has 1–2 high-value MCP integrations already firing. Usually fine — affirm. If they want more leverage, look at the tool prefixes in JSONL (`mcp__<server>__<tool>`) and suggest exploring one more server in the same category (e.g. they're using `mcp__linear` heavily → suggest `mcp__github` or `mcp__sentry` if the rest of their stack hints at it).

### 4. `automation`

| | Source |
|---|---|
| Configured | scan: hooks_present + subagent count + commands count + plugins flag |
| Activated | session: `Agent` tool dispatches × 10, capped 100 (hooks/commands not visible in JSONL) |

**Gap means**: most often, subagents are defined under `.claude/agents/*.md` but never dispatched.

**Fix flow**:
1. List `.claude/agents/*.md` — read the `description:` field of each.
2. Subagent dispatch requires the parent agent to recognize when to delegate. Common failure: subagent description is too generic for Claude to know when to call it.
3. Rewrite the weakest subagent description with concrete trigger conditions: "Use this subagent when [specific situation], NOT for [common confusion]".
4. Note that hook firings and command invocations don't appear in JSONL — for those, recommend the user wire up OTel later if they want telemetry.

**If `direction = over`** (heavy `Agent` tool dispatch but few subagents/commands defined): this is the most actionable over-direction signal. The user is **manually re-describing the same task to Claude over and over** instead of capturing it as config. Fix flow:
1. From recent JSONL, find the top 3 most-repeated `Agent` tool invocations — group by first ~80 chars of the subagent prompt.
2. For the most frequent one, propose extracting it into `.claude/commands/<verb>.md` (custom slash command) so the user types `/<verb>` instead of re-explaining the task each time.
3. If the pattern is more about *delegated reasoning* than a recipe, propose `.claude/agents/<name>.md` (subagent) instead, with a description that names the trigger phrases pulled from the repeated prompts.

### 5. `context_hygiene`

| | Source |
|---|---|
| Configured | scan: user/project split + gitignore + @import count |
| Activated | session: blend of `(1 - read_repeat_rate) × 50` + `mention_rate × 50` |

**Gap means**: settings look modular, but inside sessions Claude is re-reading the same files or the user isn't using `@path` mentions.

**Fix flow**:
1. From `session.json`, find the most-repeated read file paths (the JSON doesn't directly emit this — you may need to re-read the JSONL counting Read tool calls per file_path).
2. The two interventions:
   - **High repeat**: same file read N times in one session. Coach the user to use `Read` with `offset` / `limit` once, or use `@file` to mention it explicitly so it stays in context.
   - **Low @-mention rate**: the user types raw paths or descriptions instead of `@path`. Show them an example: instead of "look at scanner.py", type `@agent_radar/scanner.py — what's the iteration logic doing?`.

**If `direction = over`** (in-session hygiene already good — high @-mention rate or low repeat-reads — but config side is sparse): the user has internalized good context discipline, but it isn't propagated to CLAUDE.md. Look at the most-`@`-mentioned files / dirs in JSONL; propose adding the top 2–3 as `@import` lines in CLAUDE.md so they're auto-included next session.

## Closing the loop

After every accepted edit:
1. Re-run the relevant scanner.
2. Show old gap → new gap. One line.
3. Move to the next gap, or stop if the user is satisfied.

If a gap can't be closed without the user changing their actual workflow (e.g. they genuinely don't use MCP and don't want to), respect that — propose removing the configured side instead of forcing activation. Activation Gap is bidirectional: closing it by deletion is valid.
