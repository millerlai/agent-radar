#!/usr/bin/env python3
"""
agent-radar :: agent_radar.session_scanner
==========================================
Quantify "activation" — what actually fires inside Claude Code sessions —
on the same five axes as ``agent_radar.scanner``.

Design (0.2.0 — activation-gap framing)
----------------------------------------
For each capability axis we compute a 0-100 *activated* score from the
local JSONL session logs (``~/.claude/projects/*/*.jsonl``). The companion
``scanner`` reports *configured* on the same axes; ``merge`` produces the
Activation Gap (Configured − Activated) which is the product's main view.

Per-axis activation signals
---------------------------
  claude_md       - (1 - correction_rate) × 100
                    Low correction rate ⇒ CLAUDE.md is effectively guiding.
  skills          - min(100, skill_calls × 10)
  mcp             - min(100, mcp_calls × 8)
  automation      - min(100, agent_calls × 10)
                    Agent tool dispatches; hooks/commands not visible in JSONL.
  context_hygiene - blends two signals:
                      (1 - read_repeat_rate) × 50    [efficiency half]
                      mention_rate × 50              [@-reference half]

Auxiliary stats (not axes, kept for the coach):
  - tool_diversity / tool_counter top-5 (per-target metadata)
  - sessions / total_messages (volume baseline)

JSON shape
----------
Findings carry i18n keys (``label_key`` / ``detail_key`` + ``detail_args``);
``blind_spots`` are ``{"key": ..., "args": ...}`` dicts. Rendering is done by
``agent_radar.report`` via ``agent_radar.i18n``.
"""

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path


# Five axes — must match agent_radar.scanner.DIMENSION_KEYS for merge alignment.
USAGE_DIMENSION_KEYS = [
    "claude_md", "skills", "mcp", "automation", "context_hygiene",
]

# Correction signals (en + zh) — matches at start of user messages.
CORRECTION_PATTERNS = [
    r"^\s*no\b", r"^\s*don't\b", r"^\s*stop\b", r"^\s*wait\b", r"^\s*actually\b",
    r"^\s*that's wrong", r"^\s*wrong\b", r"^\s*revert\b", r"^\s*undo\b",
    r"^\s*not (that|this)", r"^\s*you should not", r"\bdon't do that\b",
    r"^\s*不對", r"^\s*不是", r"^\s*停\b", r"^\s*別\b", r"^\s*錯\b",
    r"^\s*等等", r"^\s*等一下", r"還原", r"撤銷", r"^\s*不要",
]
CORRECTION_RE = re.compile("|".join(CORRECTION_PATTERNS), re.IGNORECASE)

# @path mentions in user messages — Claude Code's "explicit context" idiom.
MENTION_RE = re.compile(r"(^|\s)@[\w./\-]+")


@dataclass
class UsageReport:
    name: str
    project_dir: str
    sessions: int = 0
    total_messages: int = 0
    user_messages: int = 0
    # Tool-call counters
    tool_calls: int = 0
    unique_tools: list = field(default_factory=list)
    tool_top5: str = ""
    skill_calls: int = 0
    mcp_calls: int = 0
    subagent_calls: int = 0   # `Agent` tool dispatches
    # Quality signals
    corrections: int = 0
    mentions: int = 0
    reads_total: int = 0
    reads_repeat: int = 0
    # Output
    findings: list = field(default_factory=list)
    scores: dict = field(default_factory=dict)        # axis -> 0..100 activated
    overall: float = 0.0


def _clamp(v: float, lo=0.0, hi=100.0) -> float:
    return max(lo, min(hi, v))


def _encode_path(p: Path) -> str:
    s = str(p.resolve())
    return s.replace(":", "-").replace("\\", "-").replace("/", "-")


def _iter_jsonl(path: Path):
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except Exception:
                    continue
    except Exception:
        return


def _extract_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text" and isinstance(block.get("text"), str):
                    parts.append(block["text"])
        return "\n".join(parts)
    return ""


def _walk_tool_uses(content):
    if not isinstance(content, list):
        return
    for block in content:
        if isinstance(block, dict) and block.get("type") == "tool_use":
            yield block


def analyze_project(proj_dir: Path) -> UsageReport:
    name = proj_dir.name.rsplit("-", 1)[-1] or proj_dir.name
    rep = UsageReport(name=name, project_dir=proj_dir.name)

    jsonl_files = sorted(proj_dir.glob("*.jsonl"))
    rep.sessions = len(jsonl_files)

    tool_counter: Counter = Counter()
    file_reads: dict = defaultdict(lambda: defaultdict(int))

    for jf in jsonl_files:
        session_id = jf.stem
        for entry in _iter_jsonl(jf):
            t = entry.get("type")
            if t not in ("user", "assistant"):
                continue
            rep.total_messages += 1
            msg = entry.get("message", {}) or {}
            content = msg.get("content")
            if t == "user":
                rep.user_messages += 1
                text = _extract_text(content)
                if text:
                    if CORRECTION_RE.search(text):
                        rep.corrections += 1
                    rep.mentions += len(MENTION_RE.findall(text))
            else:
                for tu in _walk_tool_uses(content):
                    name_ = tu.get("name", "")
                    if not name_:
                        continue
                    tool_counter[name_] += 1
                    rep.tool_calls += 1
                    if name_ == "Skill":
                        rep.skill_calls += 1
                    if name_.startswith("mcp__"):
                        rep.mcp_calls += 1
                    # Agent is the current Claude Code subagent-launcher tool
                    # (older OTel collectors saw "Task" + subagent_type param;
                    # JSONL exposes the tool name directly).
                    if name_ == "Agent":
                        rep.subagent_calls += 1
                    if name_ == "Read":
                        inp = tu.get("input") or {}
                        fp = inp.get("file_path")
                        if isinstance(fp, str):
                            file_reads[session_id][fp] += 1
                            rep.reads_total += 1

    for sess, paths in file_reads.items():
        for fp, n in paths.items():
            if n > 1:
                rep.reads_repeat += (n - 1)

    rep.unique_tools = sorted(tool_counter.keys())
    rep.tool_top5 = ", ".join(f"{k}({v})" for k, v in tool_counter.most_common(5))

    # ---- Per-axis activated scores ----------------------------------------
    findings = []

    # claude_md: low correction rate ⇒ CLAUDE.md is effectively guiding.
    if rep.user_messages == 0:
        cm_score = 0
        cm_detail_key = "session.claude_md.empty"
        cm_args: dict = {}
    else:
        rate = rep.corrections / rep.user_messages
        cm_score = _clamp(100 - rate * 700, 0, 100)
        cm_detail_key = "session.claude_md.detail"
        cm_args = {"c": rep.corrections, "m": rep.user_messages,
                   "pct": rate * 100}
    findings.append({
        "dimension": "claude_md",
        "label_key": "session.claude_md.guidance",
        "weight": 100, "score": round(cm_score, 1),
        "detail_key": cm_detail_key, "detail_args": cm_args,
    })

    # skills: Skill tool dispatches
    sk_score = _clamp(rep.skill_calls * 10, 0, 100)
    findings.append({
        "dimension": "skills",
        "label_key": "session.skills.calls",
        "weight": 100, "score": round(sk_score, 1),
        "detail_key": ("session.skills.calls.have" if rep.skill_calls
                       else "session.skills.calls.none"),
        "detail_args": ({"n": rep.skill_calls} if rep.skill_calls else {}),
    })

    # mcp: mcp__* invocations
    mcp_score = _clamp(rep.mcp_calls * 8, 0, 100)
    findings.append({
        "dimension": "mcp",
        "label_key": "session.mcp.calls",
        "weight": 100, "score": round(mcp_score, 1),
        "detail_key": ("session.mcp.calls.have" if rep.mcp_calls
                       else "session.mcp.calls.none"),
        "detail_args": ({"n": rep.mcp_calls} if rep.mcp_calls else {}),
    })

    # automation: Agent subagent dispatches
    # (hooks/commands fire silently in JSONL; only subagent dispatch is visible)
    auto_score = _clamp(rep.subagent_calls * 10, 0, 100)
    findings.append({
        "dimension": "automation",
        "label_key": "session.automation.subagent_calls",
        "weight": 100, "score": round(auto_score, 1),
        "detail_key": ("session.automation.subagent_calls.have" if rep.subagent_calls
                       else "session.automation.subagent_calls.none"),
        "detail_args": ({"n": rep.subagent_calls} if rep.subagent_calls else {}),
    })

    # context_hygiene: blend of efficient reads (low repetition) + @-mention rate
    if rep.reads_total == 0:
        eff_half = 50.0  # neutral when there's no read activity to grade
        eff_detail_key = "session.context.efficiency.empty"
        eff_args: dict = {}
    else:
        repeat_rate = rep.reads_repeat / rep.reads_total
        eff_half = _clamp((1 - repeat_rate) * 50, 0, 50)
        eff_detail_key = "session.context.efficiency.detail"
        eff_args = {"r": rep.reads_repeat, "t": rep.reads_total,
                    "pct": repeat_rate * 100}

    if rep.user_messages == 0:
        ment_half = 0.0
        ment_detail_key = "session.context.mention.empty"
        ment_args: dict = {}
    else:
        # 0.5 mentions per user msg counts as full credit (cap aggressively low —
        # most users hit this naturally once they form the habit).
        rate = rep.mentions / rep.user_messages
        ment_half = _clamp(rate * 100, 0, 50)
        ment_detail_key = "session.context.mention.detail"
        ment_args = {"n": rep.mentions, "m": rep.user_messages,
                     "rate": rate}

    findings.append({
        "dimension": "context_hygiene",
        "label_key": "session.context.efficiency",
        "weight": 50, "score": round(eff_half, 1),
        "detail_key": eff_detail_key, "detail_args": eff_args,
    })
    findings.append({
        "dimension": "context_hygiene",
        "label_key": "session.context.mention",
        "weight": 50, "score": round(ment_half, 1),
        "detail_key": ment_detail_key, "detail_args": ment_args,
    })

    rep.findings = findings

    # Roll up per-axis scores
    for dim in USAGE_DIMENSION_KEYS:
        fs = [f for f in findings if f["dimension"] == dim]
        got = sum(f["score"] for f in fs)
        cap = sum(f["weight"] for f in fs)
        rep.scores[dim] = round((got / cap * 100) if cap else 0, 1)

    rep.overall = round(sum(rep.scores.values()) / len(rep.scores), 1)
    return rep


def main():
    ap = argparse.ArgumentParser(
        description="Claude Code activation scanner — JSONL session telemetry (0.2.0)")
    ap.add_argument("paths", nargs="*",
                    help="Filter to specific repo paths (encoded names under projects/). "
                         "Empty = scan all projects.")
    ap.add_argument("--projects-dir", default=None,
                    help="Override ~/.claude/projects path (cross-OS / multi-account).")
    ap.add_argument("-o", "--output", default="-", help="Output JSON path (default stdout)")
    args = ap.parse_args()

    if args.projects_dir:
        projects_root = Path(args.projects_dir).expanduser().resolve()
    else:
        projects_root = Path.home() / ".claude" / "projects"

    if not projects_root.exists():
        print(f"[err] projects directory missing: {projects_root}", file=sys.stderr)
        print("      (Cygwin tip: try --projects-dir /c/Users/<you>/.claude/projects)",
              file=sys.stderr)
        sys.exit(1)

    filter_dirs = None
    if args.paths:
        filter_dirs = {_encode_path(Path(p)) for p in args.paths}

    targets = []
    for child in sorted(projects_root.iterdir()):
        if not child.is_dir():
            continue
        if filter_dirs is not None and child.name not in filter_dirs:
            continue
        if not any(child.glob("*.jsonl")):
            continue
        targets.append(analyze_project(child))

    result = {
        "usage_dimensions": USAGE_DIMENSION_KEYS,
        # Merge requires a name-keyed map; provide both shapes for convenience.
        "targets": [asdict(t) for t in targets],
        "targets_by_name": {t.name: asdict(t) for t in targets},
        "blind_spots": [
            {"key": "session.blind.local_only", "args": {}},
            {"key": "session.blind.pattern_only", "args": {}},
        ],
    }

    out = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output == "-":
        print(out)
    else:
        Path(args.output).write_text(out, encoding="utf-8")
        print(f"[ok] wrote {args.output} ({len(targets)} project)", file=sys.stderr)


if __name__ == "__main__":
    main()
