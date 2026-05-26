---
name: agent-radar-feedback
description: Generate an LLM-authored improvement proposal for the /agent-radar-coach skill itself, let the user augment it via multi-select + free-text, and (with explicit consent) file it as a GitHub issue at millerlai/agent-radar. Feedback is about the tool's workflow and features — NEVER about the user's repo content, paths, or PII. Use when the user says "回饋 agent-radar-coach", "想給 agent-radar 建議", "agent-radar-coach 哪裡可以改", "submit feedback for agent-radar", "improve agent-radar", or just "/agent-radar-feedback".
---

# agent-radar-feedback

You — the LLM — already understand how `/agent-radar-coach` works. So **you** draft the improvement proposal first. The user's job is to steer and augment, not to be interviewed from scratch.

The output is one of: (a) a saved `Improvement.MD` plus a filed GitHub issue at `millerlai/agent-radar`, or (b) just the saved `Improvement.MD`, or (c) nothing — user's call at each gate.

## Hard privacy rules — non-negotiable

The proposal MUST be **about the coach skill itself**, not about any user setup. Concretely:

- **Never include**: absolute paths, repo names, org names, branch names, file contents from the user's repo, contents of `scan.json` / `session.json` / `merged.json`, session IDs, JSONL filenames, email, username, machine name.
- **Allowed**: coach axis names (`claude_md`, `skills`, `mcp`, `automation`, `context_hygiene`), generic mechanics descriptions, abstract dimensions ("gap calculation could weigh recency"), proposed new features.
- If the user's free-text augmentation slips a path or repo name in, **show them the redacted version and ask to approve** before saving. Redact, never silently scrub or refuse.

## Workflow

### 1. Auto-draft Improvement.MD

**Read** `~/.claude/skills/agent-radar-coach/SKILL.md` (the coach skill body). Reason about its design and synthesize an improvement proposal organized into these themes:

| Theme | What goes here |
|---|---|
| **A. Workflow / interaction model** | The state machine: gather → pick targets → coach one gap → wait → edit → re-scan. Where does it stall? What could be batched, parallelized, or made interruptible? |
| **B. Per-axis playbook depth** | The five axis playbooks (`claude_md`, `skills`, `mcp`, `automation`, `context_hygiene`). Which ones feel thin, generic, or under-specified? |
| **C. Diagnosis / scoring** | The `gap = configured − activated` model and the `gap > 15` threshold. Are there false positives, false negatives, missing dimensions (recency, severity)? |
| **D. Discoverability & trigger phrases** | The skill `description:` frontmatter — how it gets matched against user prompts. Missing trigger surfaces, language coverage, etc. |
| **E. Output & iteration loop** | What coach hands back after an edit ("old gap → new gap"). Is there a richer artifact, dashboard, or git-trail that would help? |
| **F. New features** | Axes / fix recipes / integrations that don't exist yet (e.g. hook-fire-rate axis, subagent-quality axis, CI integration). |

For each theme, write **2–4 concrete bullets**. Each bullet should be a **specific, actionable change**, not a vague aspiration. Examples of good vs bad:

- ✓ "Coach's `skills` playbook only ranks `description` strength — add a check for `progressive disclosure` (does the SKILL.md cite subordinate files via `Read` rather than inlining everything)."
- ✗ "Make the skills playbook better."

Aim for **8–16 total bullets** across themes. Skip a theme entirely if you have nothing concrete to say — better empty than padded.

Save this draft to `~/.claude/skills/agent-radar-feedback/Improvement.MD` using the template in §3.

### 2. Show the draft + ask the user to steer

Display the draft to the user verbatim. Then call `AskUserQuestion` with TWO questions:

1. **Multi-select**: "Which of these themes should we prioritize?" — list the themes that have bullets in the draft (A–F). The user picks the ones they care about most (multi-select).
2. **Free-text** (via the implicit "Other" / notes field, or a second AskUserQuestion with a single open option): "Anything we missed? Any specific change you want to add or remove?" The user types free-form input.

If the user adds free-text that contains a path, repo name, or PII, redact it and show the cleaned version before merging.

### 3. Merge user input → final Improvement.MD

Final structure (overwrite the draft from §1):

```markdown
# /agent-radar-coach — Improvement Proposal

> LLM-authored proposal for improving the `/agent-radar-coach` skill workflow
> and features. Augmented by user via /agent-radar-feedback.
> Tool-level only — no user PII, no repo content, no session data.

**Date:** YYYY-MM-DD
**Coach skill version reviewed:** <from coach SKILL.md frontmatter, or "—">
**User-prioritized themes:** <subset of A–F the user selected>

---

## A. Workflow / interaction model
- <bullet>
- <bullet>

## B. Per-axis playbook depth
- <bullet>

## C. Diagnosis / scoring
- ...

## D. Discoverability & trigger phrases
- ...

## E. Output & iteration loop
- ...

## F. New features
- ...

## User-added items
<the user's free-text input, redacted, verbatim — or "—" if none>
```

Themes the user did NOT prioritize stay in the document but get a **`(deprioritized)`** tag in the heading, so the maintainer sees the full thinking without losing the user's signal.

### 4. Review-or-send gate

Show the merged Improvement.MD path + the full content. Ask one explicit question:

> "Review the content (you can edit), or send as a GitHub issue as-is?"

Three valid responses:
- **review** → open `Improvement.MD` for the user to edit; wait until they say "ready"
- **send** → proceed to §5
- **save-only** → stop here; do not file an issue

### 5. File the GitHub issue

Only on explicit "send" approval:

1. Check `gh auth status`. If not logged in, tell the user to run `gh auth login` and stop — do not bypass.
2. Choose a title: extract the **single most concrete bullet** from the user's prioritized themes (or from the user's free-text if non-empty). Prefix with `coach proposal: `. Example: `coach proposal: add hook-fire-rate axis`.
3. Run:
   ```bash
   gh issue create \
     --repo millerlai/agent-radar \
     --title "<title>" \
     --label "feedback,agent-radar-coach" \
     --body-file ~/.claude/skills/agent-radar-feedback/Improvement.MD
   ```
4. If `gh` errors on `--label` (labels don't exist on the repo), retry once **without** the `--label` flag. Do not create labels yourself.
5. If `gh` is not installed (`gh: command not found`), do NOT attempt to install it. Print the equivalent prefilled-URL form for the user to click:
   ```
   https://github.com/millerlai/agent-radar/issues/new?title=<urlencoded>&body=<urlencoded>
   ```
6. On success, print the issue URL and stop.

## What this skill is NOT for

- It does **not** ask the user to debrief their session or share `scan.json` / `session.json` / `merged.json`. If the user wants to attach JSON evidence, they do it on the GitHub issue UI themselves.
- It does **not** diagnose new gaps — that is `/agent-radar-coach`.
- It does **not** triage or comment on existing issues — only files new ones.

## Principles

- **LLM drafts first, user steers second.** Do not interview from scratch — you have the context.
- **Specific > vague.** Every bullet is an actionable change, not an aspiration.
- **Tool-level only.** The proposal must apply equally to every coach user — if a bullet would only make sense given a specific user's setup, it doesn't belong here.
- **Consent twice.** Once before disk write, once before issue file.
- **Redact, do not refuse.** If user's free-text adds private content, scrub and show, do not reject.
