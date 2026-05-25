#!/usr/bin/env python3
"""
agent-radar :: agent_radar.session_scanner
==========================================
量測「實際運用度」(dynamic usage)。

``agent_radar.scanner`` 量的是配置 (靜態指紋);本工具讀取 Claude Code 本機
session 紀錄 (~/.claude/projects/*/*.jsonl),量化使用者真實用了 Claude Code
多少功能。

設計理念
--------
配置完整度與實際運用度是兩件事。寫了 CLAUDE.md 不代表它有在指導 session,
裝了 MCP server 不代表真的被呼叫,定義了 skill 不代表 description 觸發得到。
本工具讀取 JSONL 把這些「真正發生的事」量化成六大運用維度分數,
與 ``agent_radar.scanner`` 配置分數疊起來,落差即為改善空間。

七大運用維度
-----------
  1. tool_diversity      - 工具呼叫多樣性 (用了幾種工具?)
  2. skill_triggered     - Skills 是否真的觸發 (Skill tool call 次數)
  3. mcp_triggered       - MCP server 是否真的被呼叫 (mcp__ prefix tool)
  4. subagent_triggered  - Subagent 是否真的被派遣 (Agent tool call 次數)
  5. low_correction      - 使用者糾正頻率低 = CLAUDE.md 指導力佳 (反向計分)
  6. context_efficiency  - 重複讀同檔比例低 = context 利用率高
  7. session_volume      - Session 量 (基準曝光度,過低時其他分數參考價值低)

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

USAGE_DIMENSION_KEYS = [
    "tool_diversity", "skill_triggered", "mcp_triggered", "subagent_triggered",
    "low_correction", "context_efficiency", "session_volume",
]

# 使用者糾正訊號 (中英雙語)。匹配 user 訊息開頭的糾正性語句。
CORRECTION_PATTERNS = [
    r"^\s*no\b", r"^\s*don't\b", r"^\s*stop\b", r"^\s*wait\b", r"^\s*actually\b",
    r"^\s*that's wrong", r"^\s*wrong\b", r"^\s*revert\b", r"^\s*undo\b",
    r"^\s*not (that|this)", r"^\s*you should not", r"\bdon't do that\b",
    r"^\s*不對", r"^\s*不是", r"^\s*停\b", r"^\s*別\b", r"^\s*錯\b",
    r"^\s*等等", r"^\s*等一下", r"還原", r"撤銷", r"^\s*不要",
]
CORRECTION_RE = re.compile("|".join(CORRECTION_PATTERNS), re.IGNORECASE)


@dataclass
class UsageReport:
    name: str
    project_dir: str
    sessions: int = 0
    total_messages: int = 0
    tool_calls: int = 0
    unique_tools: list = field(default_factory=list)
    skill_calls: int = 0
    mcp_calls: int = 0
    subagent_calls: int = 0
    user_messages: int = 0
    corrections: int = 0
    reads_total: int = 0
    reads_repeat: int = 0
    findings: list = field(default_factory=list)
    scores: dict = field(default_factory=dict)
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
                if text and CORRECTION_RE.search(text):
                    rep.corrections += 1
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
                    # Subagent dispatch tool in current Claude Code JSONL is
                    # ``Agent``. (Older OTel collectors saw ``Task`` with a
                    # ``subagent_type`` param; JSONL exposes the tool name
                    # directly, so we just match by name.)
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

    findings = []

    # 1. tool_diversity
    n_tools = len(rep.unique_tools)
    score = _clamp(n_tools * 12.5, 0, 100)
    top_str = ", ".join(f"{k}({v})" for k, v in tool_counter.most_common(5))
    findings.append({
        "dimension": "tool_diversity",
        "label_key": "session.tool_diversity",
        "weight": 100, "score": round(score, 1),
        "detail_key": "session.tool_diversity.detail",
        "detail_args": {"n": n_tools, "top": top_str},
    })

    # 2. skill_triggered
    score = _clamp(rep.skill_calls * 12, 0, 100)
    findings.append({
        "dimension": "skill_triggered",
        "label_key": "session.skill_calls",
        "weight": 100, "score": round(score, 1),
        "detail_key": ("session.skill_calls.have" if rep.skill_calls
                       else "session.skill_calls.none"),
        "detail_args": ({"n": rep.skill_calls} if rep.skill_calls else {}),
    })

    # 3. mcp_triggered
    score = _clamp(rep.mcp_calls * 8, 0, 100)
    findings.append({
        "dimension": "mcp_triggered",
        "label_key": "session.mcp_calls",
        "weight": 100, "score": round(score, 1),
        "detail_key": ("session.mcp_calls.have" if rep.mcp_calls
                       else "session.mcp_calls.none"),
        "detail_args": ({"n": rep.mcp_calls} if rep.mcp_calls else {}),
    })

    # 4. subagent_triggered
    # Same shape as skill/mcp: each dispatch is rare-but-valuable, so 10 pts
    # per call (≥10 calls saturates). Discourages over-fitting to one prolific
    # session while still rewarding any real adoption.
    score = _clamp(rep.subagent_calls * 10, 0, 100)
    findings.append({
        "dimension": "subagent_triggered",
        "label_key": "session.subagent_calls",
        "weight": 100, "score": round(score, 1),
        "detail_key": ("session.subagent_calls.have" if rep.subagent_calls
                       else "session.subagent_calls.none"),
        "detail_args": ({"n": rep.subagent_calls} if rep.subagent_calls else {}),
    })

    # 5. low_correction (反向)
    if rep.user_messages == 0:
        score = 0
        detail_key = "session.low_correction.empty"
        detail_args: dict = {}
    else:
        rate = rep.corrections / rep.user_messages
        score = _clamp(100 - rate * 700, 0, 100)
        detail_key = "session.low_correction.detail"
        detail_args = {"c": rep.corrections, "m": rep.user_messages,
                       "pct": rate * 100}
    findings.append({
        "dimension": "low_correction",
        "label_key": "session.low_correction",
        "weight": 100, "score": round(score, 1),
        "detail_key": detail_key,
        "detail_args": detail_args,
    })

    # 6. context_efficiency
    if rep.reads_total == 0:
        score = 50
        detail_key = "session.read_repeat.empty"
        detail_args = {}
    else:
        repeat_rate = rep.reads_repeat / rep.reads_total
        score = _clamp(100 - repeat_rate * 200, 0, 100)
        detail_key = "session.read_repeat.detail"
        detail_args = {"r": rep.reads_repeat, "t": rep.reads_total,
                       "pct": repeat_rate * 100}
    findings.append({
        "dimension": "context_efficiency",
        "label_key": "session.read_repeat",
        "weight": 100, "score": round(score, 1),
        "detail_key": detail_key,
        "detail_args": detail_args,
    })

    # 7. session_volume
    if rep.sessions == 0:
        score = 0
    elif rep.sessions < 3:
        score = 30
    elif rep.sessions < 10:
        score = 60
    else:
        score = 100
    findings.append({
        "dimension": "session_volume",
        "label_key": "session.session_volume",
        "weight": 100, "score": round(score, 1),
        "detail_key": "session.session_volume.detail",
        "detail_args": {"s": rep.sessions, "m": rep.total_messages},
    })

    rep.findings = findings
    rep.scores = {f["dimension"]: f["score"] for f in findings}
    rep.overall = round(sum(rep.scores.values()) / len(rep.scores), 1)
    return rep


def main():
    ap = argparse.ArgumentParser(description="Claude Code 運用度 (session) 掃描器")
    ap.add_argument("paths", nargs="*",
                    help="篩選某幾個 repo 路徑 (對應 projects/ 編碼名);留空則掃所有 project")
    ap.add_argument("--projects-dir", default=None,
                    help="自訂 ~/.claude/projects 路徑 (跨 OS 時手動指定)")
    ap.add_argument("-o", "--output", default="-", help="輸出 JSON 路徑 (預設 stdout)")
    args = ap.parse_args()

    if args.projects_dir:
        projects_root = Path(args.projects_dir).expanduser().resolve()
    else:
        projects_root = Path.home() / ".claude" / "projects"

    if not projects_root.exists():
        print(f"[err] projects 目錄不存在: {projects_root}", file=sys.stderr)
        print("      (Cygwin 環境提示: 試 --projects-dir /c/Users/<you>/.claude/projects)",
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
        "targets": [asdict(t) for t in targets],
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
        print(f"[ok] 已寫入 {args.output} ({len(targets)} project)", file=sys.stderr)


if __name__ == "__main__":
    main()
