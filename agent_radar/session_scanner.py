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

六大運用維度
-----------
  1. tool_diversity   - 工具呼叫多樣性 (用了幾種工具?)
  2. skill_triggered  - Skills 是否真的觸發 (Skill tool call 次數)
  3. mcp_triggered    - MCP server 是否真的被呼叫 (mcp__ prefix tool)
  4. low_correction   - 使用者糾正頻率低 = CLAUDE.md 指導力佳 (反向計分)
  5. context_efficiency - 重複讀同檔比例低 = context 利用率高
  6. session_volume   - Session 量 (基準曝光度,過低時其他分數參考價值低)

用法
----
  # 掃 user-space 所有 projects
  agent-radar session -o session.json

  # 只統計某幾個 project (用原始 repo 路徑)
  agent-radar session /path/to/repo -o session.json

  # 自訂 projects 根目錄
  agent-radar session --projects-dir /custom/.claude/projects -o session.json
"""

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path

USAGE_DIMENSIONS = {
    "tool_diversity": "工具多樣性",
    "skill_triggered": "Skills 實際觸發",
    "mcp_triggered": "MCP 實際呼叫",
    "low_correction": "低糾正率",
    "context_efficiency": "Context 效率",
    "session_volume": "Session 量",
}

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
    project_dir: str          # 編碼後的 projects/ 子目錄名
    sessions: int = 0
    total_messages: int = 0
    tool_calls: int = 0
    unique_tools: list = field(default_factory=list)
    skill_calls: int = 0
    mcp_calls: int = 0
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
    """模擬 Claude Code 把 absolute path 編碼為 projects/ 子目錄名的規則。
    觀察結果: drive ':' / 路徑分隔符 → '-'。例: C:\\foo\\bar → C--foo-bar"""
    s = str(p.resolve())
    return s.replace(":", "-").replace("\\", "-").replace("/", "-")


def _iter_jsonl(path: Path):
    """逐行 yield JSONL,跳過解析失敗的行 (session JSONL 可能有截斷)。"""
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
    """從 message.content 抓出純文字 (可能是 string 或 list-of-blocks)。"""
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
    """從 assistant message.content 抓出 tool_use blocks。"""
    if not isinstance(content, list):
        return
    for block in content:
        if isinstance(block, dict) and block.get("type") == "tool_use":
            yield block


def analyze_project(proj_dir: Path) -> UsageReport:
    """分析單一 project (對應一個 cwd) 的所有 JSONL session。"""
    # 從編碼路徑回推 display name (取最後一段)
    name = proj_dir.name.rsplit("-", 1)[-1] or proj_dir.name
    rep = UsageReport(name=name, project_dir=proj_dir.name)

    jsonl_files = sorted(proj_dir.glob("*.jsonl"))
    rep.sessions = len(jsonl_files)

    tool_counter: Counter = Counter()
    file_reads: dict = defaultdict(lambda: defaultdict(int))  # session_id -> path -> count

    for jf in jsonl_files:
        session_id = jf.stem
        for entry in _iter_jsonl(jf):
            t = entry.get("type")
            # Claude Code JSONL 頂層 type 是 'user' / 'assistant' / 'system' /
            # 'attachment' / 'last-prompt' / 'permission-mode' 等
            if t not in ("user", "assistant"):
                continue
            rep.total_messages += 1
            msg = entry.get("message", {}) or {}
            content = msg.get("content")
            if t == "user":
                rep.user_messages += 1
                text = _extract_text(content)
                # 排除 tool_result wrapper (content 為 list 且只有 tool_result block)
                if text and CORRECTION_RE.search(text):
                    rep.corrections += 1
            else:  # assistant
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
                    # context efficiency: Read 同檔重複
                    if name_ == "Read":
                        inp = tu.get("input") or {}
                        fp = inp.get("file_path")
                        if isinstance(fp, str):
                            file_reads[session_id][fp] += 1
                            rep.reads_total += 1

    # 重複讀取統計: 同 session 同檔 read > 1 次,超出部分算重複
    for sess, paths in file_reads.items():
        for fp, n in paths.items():
            if n > 1:
                rep.reads_repeat += (n - 1)

    rep.unique_tools = sorted(tool_counter.keys())

    # ----- findings & scores -----
    findings = []

    # 1. tool_diversity: 用過幾種不同工具 (8 種以上滿分)
    n_tools = len(rep.unique_tools)
    score = _clamp(n_tools * 12.5, 0, 100)
    findings.append({
        "dimension": "tool_diversity", "label": "Tool 多樣性",
        "weight": 100, "score": round(score, 1),
        "detail": f"{n_tools} 種工具,前 5: " +
                  ", ".join(f"{k}({v})" for k, v in tool_counter.most_common(5)),
    })

    # 2. skill_triggered: 任何 skill call > 0 即得基本分,多次更高
    score = _clamp(rep.skill_calls * 12, 0, 100)
    findings.append({
        "dimension": "skill_triggered", "label": "Skill tool 呼叫",
        "weight": 100, "score": round(score, 1),
        "detail": f"{rep.skill_calls} 次 Skill 觸發" if rep.skill_calls
                  else "Skill 從未觸發 (description 可能寫不夠好,或無安裝 skills)",
    })

    # 3. mcp_triggered
    score = _clamp(rep.mcp_calls * 8, 0, 100)
    findings.append({
        "dimension": "mcp_triggered", "label": "MCP tool 呼叫",
        "weight": 100, "score": round(score, 1),
        "detail": f"{rep.mcp_calls} 次 MCP server 呼叫" if rep.mcp_calls
                  else "MCP server 從未被呼叫",
    })

    # 4. low_correction (反向): 糾正率低 = 高分。
    if rep.user_messages == 0:
        score = 0
        detail = "無 user 訊息可評估"
    else:
        rate = rep.corrections / rep.user_messages
        # 糾正率 0% → 100;5% → ~60;10% → ~20;>15% → 0
        score = _clamp(100 - rate * 700, 0, 100)
        detail = f"{rep.corrections}/{rep.user_messages} user 訊息含糾正 ({rate*100:.1f}%)"
    findings.append({
        "dimension": "low_correction", "label": "低糾正率",
        "weight": 100, "score": round(score, 1),
        "detail": detail,
    })

    # 5. context_efficiency: 重複讀檔比例低 = 高分
    if rep.reads_total == 0:
        score = 50  # 沒讀過檔案,中性分
        detail = "無 Read 行為"
    else:
        repeat_rate = rep.reads_repeat / rep.reads_total
        score = _clamp(100 - repeat_rate * 200, 0, 100)
        detail = f"{rep.reads_repeat}/{rep.reads_total} 為重複讀檔 ({repeat_rate*100:.1f}%)"
    findings.append({
        "dimension": "context_efficiency", "label": "Read 重複率 (反向)",
        "weight": 100, "score": round(score, 1),
        "detail": detail,
    })

    # 6. session_volume: 曝光度
    if rep.sessions == 0:
        score = 0
    elif rep.sessions < 3:
        score = 30
    elif rep.sessions < 10:
        score = 60
    else:
        score = 100
    findings.append({
        "dimension": "session_volume", "label": "Session 量",
        "weight": 100, "score": round(score, 1),
        "detail": f"{rep.sessions} 個 session, {rep.total_messages} 則訊息",
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
        print(f"      (Cygwin 環境提示: 試 --projects-dir /c/Users/<you>/.claude/projects)",
              file=sys.stderr)
        sys.exit(1)

    # 篩選: 若指定 paths,把它們編碼成 projects/ 子目錄名
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
        "usage_dimensions": USAGE_DIMENSIONS,
        "targets": [asdict(t) for t in targets],
        "blind_spots": [
            "本工具讀取本機 JSONL,無法觀測雲端 / 其他機器的 session;"
            "若團隊跨機器使用,建議搭配 OpenTelemetry 中央化收集。",
            "糾正率僅匹配字面 pattern,語意級糾正 (例如冗長解釋為什麼錯) 偵測不到。",
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
