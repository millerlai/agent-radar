#!/usr/bin/env python3
"""
agent-radar :: scanner.py
=========================
偵測「個人 / 團隊使用 Claude Code 生態的能力邊界」。

設計理念
--------
一個人對 Claude Code 的掌握程度，會直接刻在他的檔案系統裡。
本掃描器把這些「指紋」轉換成六大維度的成熟度分數 (0~100)：

  1. CLAUDE_MD     - CLAUDE.md 的有無、層級、結構化程度、迭代痕跡
  2. SKILLS        - skills 的使用與 SKILL.md 品質 (description / progressive disclosure)
  3. MCP           - MCP server 設定的廣度與類型
  4. AUTOMATION    - hooks / subagents / 自訂 slash commands / plugins
  5. CONTEXT_HYGIENE - user-space vs project-space 分工、@import、檔案精簡度
  6. ITERATION     - 透過 git history 看設定是否隨踩坑迭代

「配置完整度」與「實際運用度」是兩件事。本工具偵測的是「配置」(靜態)，
若要量測「運用」需接 OpenTelemetry，scanner 會在報告中標註此落差盲區。

用法
----
  # 掃單一目錄 (個人 / 單一 repo)
  python scanner.py /path/to/repo

  # 掃多個 repo (團隊 benchmark)
  python scanner.py /repos/a /repos/b /repos/c

  # 一併納入 user-space (~/.claude)
  python scanner.py --include-home /path/to/repo

輸出
----
  stdout 印出 JSON。搭配 report.py 產生 HTML 雷達圖報告。
"""

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


# ----------------------------------------------------------------------------
# 維度定義
# ----------------------------------------------------------------------------

DIMENSIONS = {
    "claude_md": "CLAUDE.md 成熟度",
    "skills": "Skills 運用",
    "mcp": "MCP 整合",
    "automation": "自動化",
    "context_hygiene": "情境衛生",
    "iteration": "迭代與維護",
}

# 成熟度層級標籤 (給總分用)
LEVELS = [
    (0, "L0 · 未使用 (Unaware)"),
    (20, "L1 · 萌芽 (Reactive)"),
    (40, "L2 · 結構化 (Structured)"),
    (60, "L3 · 進階 (Advanced)"),
    (80, "L4 · 精煉 (Mastery)"),
]


# ----------------------------------------------------------------------------
# 偵測結果資料結構
# ----------------------------------------------------------------------------

@dataclass
class Finding:
    """單一證據訊號。"""
    dimension: str
    label: str
    weight: float          # 該訊號滿分時對維度貢獻的分數
    score: float           # 實際得分 (0 ~ weight)
    detail: str = ""

    @property
    def ratio(self) -> float:
        return (self.score / self.weight) if self.weight else 0.0


@dataclass
class TargetReport:
    """單一掃描目標 (一個 repo 或 home dir) 的結果。"""
    name: str
    path: str
    is_home: bool = False
    findings: list = field(default_factory=list)
    scores: dict = field(default_factory=dict)   # dimension -> 0..100
    overall: float = 0.0
    level: str = ""
    blind_spots: list = field(default_factory=list)


# ----------------------------------------------------------------------------
# 小工具
# ----------------------------------------------------------------------------

def _read(path: Path, limit: int = 200_000) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")[:limit]
    except Exception:
        return ""


def _exists(path: Path) -> bool:
    try:
        return path.exists()
    except Exception:
        return False


def _git_log_count(repo: Path, pathspec: str) -> int:
    """數某個 pathspec 在 git history 中被 commit 修改的次數。0 表示無 git 或無紀錄。"""
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "log", "--oneline", "--", pathspec],
            capture_output=True, encoding="utf-8", errors="replace", timeout=10,
        )
        if out.returncode != 0:
            return 0
        return len([l for l in out.stdout.splitlines() if l.strip()])
    except Exception:
        return 0


def _clamp(v: float, lo: float = 0.0, hi: float = None) -> float:
    if v < lo:
        return lo
    if hi is not None and v > hi:
        return hi
    return v


# ----------------------------------------------------------------------------
# 各維度偵測邏輯
# ----------------------------------------------------------------------------

# 結構化分區的常見標題關鍵字 (中英)
SECTION_HINTS = [
    "command", "build", "test", "lint", "code style", "convention",
    "architecture", "workflow", "do not", "never", "always", "important",
    "指令", "建置", "測試", "風格", "規範", "架構", "禁止", "務必", "注意",
]

# imperative / 指令式語氣的訊號 (寫得好的 CLAUDE.md 多用祈使句)
IMPERATIVE_HINTS = [
    r"\buse\b", r"\bdo not\b", r"\bnever\b", r"\balways\b", r"\bprefer\b",
    r"\brun\b", r"\bavoid\b", r"\bensure\b", r"請", r"務必", r"禁止", r"避免",
]

# Lint 規則參考 (借自 felixgeelhaar/cclint 與 agentskills.io Skill Linter,
# 不依賴外部工具,純規則重新實作)。
CLAUDE_MD_SOFT_LIMIT_CHARS = 8_000     # 超過此字元數開始扣分 (cclint 預設約 5–10KB)
CLAUDE_MD_HARD_LIMIT_CHARS = 20_000    # 超過此字元數為「傾倒場」,大幅扣分
SKILL_MD_SOFT_LIMIT_LINES = 250        # agentskills.io 建議主檔精簡
SKILL_MD_HARD_LIMIT_LINES = 500

# ASCII art / 裝飾性內容 → token 浪費
DECORATIVE_PATTERNS = [
    r"[=\-_*#~`]{20,}",          # ===== / ----- / ##### 等
    r"[─━│┃┄┅┆┇┈┉┊┋┌┍┎┏┐┑┒┓└┕┖┗┘┙┚┛├┝┞┟┠┡┢┣┤┥┦┧┨┩┪┫┬┭┮┯┰┱┲┳┴┵┶┷┸┹┺┻┼┽┾┿╀╁╂╃╄╅╆╇╈╉╊╋╌╍╎╏═║╒╓╔╕╖╗╘╙╚╛╜╝╞╟╠╡╢╣╤╥╦╧╨╩╪╫╬╭╮╯╰╱╲╳╴╵╶╷╸╹╺╻╼╽╾╿]{8,}",  # box-drawing
    r"^\s*[▀▁▂▃▄▅▆▇█▉▊▋▌▍▎▏▐░▒▓▔▕]{4,}",     # block elements
]
DECORATIVE_RE = re.compile("|".join(DECORATIVE_PATTERNS), re.MULTILINE)


def detect_claude_md(repo: Path, is_home: bool) -> list:
    """評估 CLAUDE.md 成熟度。"""
    findings = []
    # project-space 與 user-space 可能的位置
    candidates = [
        repo / "CLAUDE.md",
        repo / ".claude" / "CLAUDE.md",
    ]
    found = [p for p in candidates if _exists(p)]

    # 1. 存在性
    findings.append(Finding(
        "claude_md", "CLAUDE.md 存在", weight=25,
        score=25 if found else 0,
        detail=("找到 " + ", ".join(str(p.relative_to(repo)) for p in found)) if found
        else "未發現 CLAUDE.md",
    ))

    if not found:
        # 後面的訊號都 0 分，但仍列出讓報告完整
        for lbl, w in [("結構化分區", 20), ("指令式語氣", 15),
                       ("精簡度 (非散文堆疊)", 15), ("@import 引用", 10)]:
            findings.append(Finding("claude_md", lbl, weight=w, score=0,
                                    detail="無 CLAUDE.md 可評估"))
        return findings

    text = "\n\n".join(_read(p) for p in found)
    lower = text.lower()

    # 2. 結構化分區：看 markdown 標題數 + 是否命中分區關鍵字
    headers = re.findall(r"^#{1,4}\s+.+$", text, flags=re.MULTILINE)
    hint_hits = sum(1 for h in SECTION_HINTS if h in lower)
    struct_score = _clamp(len(headers) * 4 + hint_hits * 2, 0, 20)
    findings.append(Finding(
        "claude_md", "結構化分區", weight=20, score=struct_score,
        detail=f"{len(headers)} 個標題, 命中 {hint_hits} 個分區關鍵字",
    ))

    # 3. 指令式語氣
    imp_hits = sum(len(re.findall(p, lower)) for p in IMPERATIVE_HINTS)
    imp_score = _clamp(imp_hits * 1.5, 0, 15)
    findings.append(Finding(
        "claude_md", "指令式語氣", weight=15, score=imp_score,
        detail=f"偵測到約 {imp_hits} 處祈使/規範語句",
    ))

    # 4. 精簡度：好的 CLAUDE.md 精簡且高密度。過長散文扣分。
    words = len(text.split())
    if words == 0:
        concise = 0
    elif words < 80:
        concise = 7          # 太短也不夠 (可能只是佔位)
    elif words <= 600:
        concise = 15         # 黃金區間
    elif words <= 1200:
        concise = 10
    else:
        concise = 5          # 過長，多半是想到什麼塞什麼
    findings.append(Finding(
        "claude_md", "精簡度 (非散文堆疊)", weight=15, score=concise,
        detail=f"約 {words} 字",
    ))

    # 5. @import 引用 (懂得拆檔、保持主檔精簡)
    imports = len(re.findall(r"(^|\s)@[\w./\-]+", text))
    imp_ref_score = _clamp(imports * 5, 0, 10)
    findings.append(Finding(
        "claude_md", "@import 引用", weight=10, score=imp_ref_score,
        detail=f"{imports} 處 @ 引用" if imports else "未使用 @import 拆檔",
    ))

    # 6. Lint: 大小合理 (借自 cclint 的 CLAUDE.md size check)
    total_chars = len(text)
    if total_chars <= CLAUDE_MD_SOFT_LIMIT_CHARS:
        size_score = 15
        size_detail = f"{total_chars} chars (合規)"
    elif total_chars <= CLAUDE_MD_HARD_LIMIT_CHARS:
        ratio = (CLAUDE_MD_HARD_LIMIT_CHARS - total_chars) / (
            CLAUDE_MD_HARD_LIMIT_CHARS - CLAUDE_MD_SOFT_LIMIT_CHARS)
        size_score = round(15 * max(ratio, 0) * 0.5 + 4, 1)
        size_detail = f"{total_chars} chars (偏大,建議拆檔或精簡)"
    else:
        size_score = 0
        size_detail = f"{total_chars} chars (過大,違反 cclint 建議,context 浪費)"
    findings.append(Finding(
        "claude_md", "Lint: 大小合理", weight=15, score=size_score,
        detail=size_detail,
    ))

    return findings


def detect_skills(repo: Path, is_home: bool) -> list:
    findings = []
    skill_dirs = [repo / ".claude" / "skills", repo / "skills"]
    skill_files = []
    for d in skill_dirs:
        if _exists(d):
            skill_files.extend(d.rglob("SKILL.md"))

    findings.append(Finding(
        "skills", "Skills 存在", weight=35,
        score=35 if skill_files else 0,
        detail=f"找到 {len(skill_files)} 個 SKILL.md" if skill_files else "未使用 skills",
    ))

    if not skill_files:
        for lbl, w in [("description 品質", 35), ("Progressive disclosure", 30),
                       ("Lint: frontmatter & token 衛生", 20)]:
            findings.append(Finding("skills", lbl, weight=w, score=0,
                                    detail="無 skills 可評估"))
        return findings

    # description 品質：YAML frontmatter 是否有夠具體的 description
    desc_quality = 0.0
    pd_quality = 0.0
    # Lint 統計
    frontmatter_ok = 0     # 有完整 name + description 的數量
    decor_violations = 0   # ASCII art / 裝飾性內容違規數量
    oversize_violations = 0  # SKILL.md 過大
    for sf in skill_files:
        t = _read(sf)
        m = re.search(r"description:\s*(.+)", t)
        if m:
            desc_len = len(m.group(1).split())
            # 好的 description 描述「何時觸發」，通常較長且含 trigger 字眼
            trigger = any(k in m.group(1).lower()
                          for k in ["use this", "use when", "trigger", "when the user"])
            desc_quality += min(15, desc_len * 0.4) + (10 if trigger else 0)
        # progressive disclosure：主檔精簡 + 旁邊有附屬檔
        sibling = list(sf.parent.glob("*"))
        body_words = len(t.split())
        if body_words and body_words < 500 and len(sibling) > 1:
            pd_quality += 15
        elif len(sibling) > 1:
            pd_quality += 8

        # Lint: frontmatter 完整性 (借自 agentskills.io Skill Linter)
        has_name = bool(re.search(r"^name:\s*\S", t, re.MULTILINE))
        has_desc = bool(m and m.group(1).strip())
        if has_name and has_desc:
            frontmatter_ok += 1

        # Lint: SKILL.md 行數過大 → 違反 progressive disclosure 原則
        n_lines = t.count("\n") + 1
        if n_lines > SKILL_MD_HARD_LIMIT_LINES:
            oversize_violations += 1
        elif n_lines > SKILL_MD_SOFT_LIMIT_LINES:
            oversize_violations += 0.5  # 半個違規

        # Lint: ASCII art / 裝飾性 banner → token 浪費
        if DECORATIVE_RE.search(t):
            decor_violations += 1

    desc_score = _clamp(desc_quality / len(skill_files), 0, 35)
    pd_score = _clamp(pd_quality, 0, 30)

    findings.append(Finding(
        "skills", "description 品質", weight=35, score=desc_score,
        detail="description 平均品質 (含觸發描述)",
    ))
    findings.append(Finding(
        "skills", "Progressive disclosure", weight=30, score=pd_score,
        detail="主檔精簡 + 附屬檔拆分情況",
    ))

    # Lint 綜合分數 (滿分 20)
    n = len(skill_files)
    fm_ratio = frontmatter_ok / n
    lint_score = 20 * fm_ratio
    # 扣分: 每個違規扣 3 分
    lint_score -= min(lint_score, decor_violations * 3 + oversize_violations * 4)
    lint_score = max(0, lint_score)
    detail_parts = [f"frontmatter 合規 {frontmatter_ok}/{n}"]
    if decor_violations:
        detail_parts.append(f"{decor_violations} 處 ASCII art/裝飾性內容")
    if oversize_violations:
        detail_parts.append(f"行數超標 {oversize_violations}")
    findings.append(Finding(
        "skills", "Lint: frontmatter & token 衛生", weight=20, score=lint_score,
        detail=", ".join(detail_parts),
    ))
    return findings


# MCP server 大致分類，用來判斷「廣度」
MCP_CATEGORY_HINTS = {
    "data": ["postgres", "mysql", "sqlite", "mongo", "bigquery", "snowflake"],
    "saas": ["asana", "linear", "jira", "notion", "slack", "github", "gitlab", "sentry"],
    "cloud": ["aws", "gcp", "azure", "cloudflare", "vercel"],
    "search": ["brave", "tavily", "exa", "perplexity", "fetch", "puppeteer", "playwright"],
    "files": ["filesystem", "drive", "gdrive", "dropbox"],
}


def detect_mcp(repo: Path, is_home: bool) -> list:
    findings = []
    candidates = [
        repo / ".mcp.json",
        repo / ".claude" / "settings.json",
        repo / ".claude" / "settings.local.json",
    ]
    servers = {}
    for c in candidates:
        if not _exists(c):
            continue
        try:
            data = json.loads(_read(c))
        except Exception:
            continue
        block = data.get("mcpServers") or data.get("mcp_servers") or {}
        if isinstance(block, dict):
            servers.update(block)

    n = len(servers)
    findings.append(Finding(
        "mcp", "MCP server 數量", weight=50,
        score=_clamp(n * 18, 0, 50),
        detail=f"{n} 個 MCP server" if n else "未設定任何 MCP server",
    ))

    # 廣度：跨越幾種類別
    blob = " ".join(servers.keys()).lower() + " " + json.dumps(servers).lower()
    cats = [c for c, kw in MCP_CATEGORY_HINTS.items() if any(k in blob for k in kw)]
    findings.append(Finding(
        "mcp", "MCP 類型廣度", weight=50,
        score=_clamp(len(cats) * 17, 0, 50),
        detail=("涵蓋類別: " + ", ".join(cats)) if cats else "無法辨識類別",
    ))
    return findings


def detect_automation(repo: Path, is_home: bool) -> list:
    findings = []
    cc = repo / ".claude"

    # hooks
    hooks_present = False
    settings_invalid = False
    settings = cc / "settings.json"
    if _exists(settings):
        try:
            hooks_present = "hooks" in json.loads(_read(settings))
        except Exception:
            settings_invalid = True
    hooks_dir = cc / "hooks"
    if _exists(hooks_dir) and any(hooks_dir.iterdir()):
        hooks_present = True
    detail = "偵測到 hooks 設定" if hooks_present else "未使用 hooks"
    if settings_invalid:
        detail = "Lint: .claude/settings.json 解析失敗 (JSON 格式錯誤)"
    findings.append(Finding(
        "automation", "Hooks", weight=30,
        score=0 if settings_invalid else (30 if hooks_present else 0),
        detail=detail,
    ))

    # subagents
    agents_dir = cc / "agents"
    n_agents = len(list(agents_dir.glob("*.md"))) if _exists(agents_dir) else 0
    findings.append(Finding(
        "automation", "Subagents", weight=30,
        score=_clamp(n_agents * 15, 0, 30),
        detail=f"{n_agents} 個 subagent" if n_agents else "未定義 subagents",
    ))

    # 自訂 slash commands
    cmd_dir = cc / "commands"
    n_cmd = len(list(cmd_dir.glob("*.md"))) if _exists(cmd_dir) else 0
    findings.append(Finding(
        "automation", "自訂 slash commands", weight=25,
        score=_clamp(n_cmd * 9, 0, 25),
        detail=f"{n_cmd} 個自訂命令" if n_cmd else "未建立自訂命令",
    ))

    # plugins (marketplace)
    plugin_signal = _exists(cc / "plugins") or (
        _exists(settings) and "plugin" in _read(settings).lower())
    findings.append(Finding(
        "automation", "Plugins", weight=15,
        score=15 if plugin_signal else 0,
        detail="偵測到 plugin 使用" if plugin_signal else "未使用 plugins",
    ))
    return findings


def detect_context_hygiene(repo: Path, is_home: bool, home_seen: bool) -> list:
    findings = []

    # user-space vs project-space 分工
    proj_md = _exists(repo / "CLAUDE.md") or _exists(repo / ".claude" / "CLAUDE.md")
    split_score = 0
    if proj_md and home_seen:
        split_score = 40
        detail = "同時具備 project 與 user-space 設定 (分工良好)"
    elif proj_md:
        split_score = 20
        detail = "僅 project-space 設定 (建議補 ~/.claude 放個人通用偏好)"
    elif home_seen:
        split_score = 20
        detail = "僅 user-space 設定"
    else:
        detail = "無分工"
    findings.append(Finding(
        "context_hygiene", "User/Project 分工", weight=40,
        score=split_score, detail=detail,
    ))

    # .gitignore 是否處理了 .claude/settings.local.json (代表懂得區分共享 vs 個人設定)
    gi = _read(repo / ".gitignore").lower()
    gi_score = 30 if ("settings.local" in gi or ".claude/settings.local" in gi) else 0
    findings.append(Finding(
        "context_hygiene", "共享/個人設定區分", weight=30,
        score=gi_score,
        detail="settings.local.json 已 gitignore" if gi_score else
               "未區分共享與個人設定",
    ))

    # 是否用 @import / 拆檔避免巨型單檔
    md_text = ""
    for p in [repo / "CLAUDE.md", repo / ".claude" / "CLAUDE.md"]:
        if _exists(p):
            md_text += _read(p)
    imports = len(re.findall(r"(^|\s)@[\w./\-]+", md_text))
    findings.append(Finding(
        "context_hygiene", "模組化引用", weight=30,
        score=_clamp(imports * 15, 0, 30),
        detail=f"{imports} 處模組化引用" if imports else "未模組化拆檔",
    ))
    return findings


def detect_iteration(repo: Path, is_home: bool) -> list:
    findings = []
    is_git = _exists(repo / ".git")

    if not is_git:
        findings.append(Finding(
            "iteration", "設定檔 git 迭代", weight=60, score=0,
            detail="非 git repo，無法評估迭代",
        ))
        findings.append(Finding(
            "iteration", "設定檔多樣性", weight=40, score=0,
            detail="非 git repo",
        ))
        return findings

    # CLAUDE.md / skills / settings 的 commit 次數 → 反映踩坑後是否回頭調整
    counts = {
        "CLAUDE.md": _git_log_count(repo, "CLAUDE.md")
                     + _git_log_count(repo, ".claude/CLAUDE.md"),
        ".claude/": _git_log_count(repo, ".claude"),
        ".mcp.json": _git_log_count(repo, ".mcp.json"),
    }
    total_commits = sum(counts.values())
    findings.append(Finding(
        "iteration", "設定檔 git 迭代", weight=60,
        score=_clamp(total_commits * 8, 0, 60),
        detail="設定相關 commit 次數: " +
               ", ".join(f"{k}={v}" for k, v in counts.items() if v),
    ))

    # 設定檔多樣性：同時動到多種設定 = 全方位掌握
    touched = sum(1 for v in counts.values() if v > 0)
    findings.append(Finding(
        "iteration", "設定檔多樣性", weight=40,
        score=_clamp(touched * 14, 0, 40),
        detail=f"曾迭代 {touched} 類設定檔",
    ))
    return findings


# ----------------------------------------------------------------------------
# 彙整
# ----------------------------------------------------------------------------

def score_target(path: Path, name: str, is_home: bool, home_seen: bool) -> TargetReport:
    rep = TargetReport(name=name, path=str(path), is_home=is_home)

    rep.findings += detect_claude_md(path, is_home)
    rep.findings += detect_skills(path, is_home)
    rep.findings += detect_mcp(path, is_home)
    rep.findings += detect_automation(path, is_home)
    rep.findings += detect_context_hygiene(path, is_home, home_seen)
    rep.findings += detect_iteration(path, is_home)

    # 各維度加總
    for dim in DIMENSIONS:
        fs = [f for f in rep.findings if f.dimension == dim]
        got = sum(f.score for f in fs)
        cap = sum(f.weight for f in fs)
        rep.scores[dim] = round((got / cap * 100) if cap else 0, 1)

    rep.overall = round(sum(rep.scores.values()) / len(rep.scores), 1)

    for threshold, label in reversed(LEVELS):
        if rep.overall >= threshold:
            rep.level = label
            break

    # 盲區提示
    if rep.scores["mcp"] > 0 or rep.scores["skills"] > 0:
        rep.blind_spots.append(
            "本工具只偵測『配置完整度』，無法得知這些設定在實際 session 中"
            "是否真的被觸發。建議接 OpenTelemetry 量測『實際運用度』，"
            "兩者落差即為改善空間。")
    if not _exists(path / ".git") and not is_home:
        rep.blind_spots.append("此目標非 git repo，迭代維度無法評估，分數偏低屬正常。")

    rep.findings = [asdict(f) for f in rep.findings]
    return rep


def main():
    ap = argparse.ArgumentParser(description="Claude Code 使用成熟度掃描器")
    ap.add_argument("paths", nargs="+", help="要掃描的 repo 目錄 (可多個)")
    ap.add_argument("--include-home", action="store_true",
                    help="一併納入 user-space (~/.claude)")
    ap.add_argument("-o", "--output", default="-", help="輸出 JSON 路徑 (預設 stdout)")
    args = ap.parse_args()

    targets = []
    home_seen = False

    # 先判斷 user-space 是否存在 (影響 context_hygiene 評分)
    home_claude = Path.home() / ".claude"
    if args.include_home and _exists(home_claude):
        home_seen = True

    for p in args.paths:
        path = Path(p).expanduser().resolve()
        if not path.exists():
            print(f"[warn] 路徑不存在，略過: {path}", file=sys.stderr)
            continue
        targets.append(score_target(path, path.name, is_home=False, home_seen=home_seen))

    if args.include_home and _exists(home_claude):
        targets.append(score_target(home_claude.parent, "~ (user-space)",
                                    is_home=True, home_seen=True))

    result = {
        "dimensions": DIMENSIONS,
        "levels": LEVELS,
        "targets": [asdict(t) for t in targets],
    }

    out = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output == "-":
        print(out)
    else:
        Path(args.output).write_text(out, encoding="utf-8")
        print(f"[ok] 已寫入 {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
