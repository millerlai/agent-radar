#!/usr/bin/env python3
"""
agent-radar :: agent_radar.scanner
==================================
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

JSON shape
----------
Findings carry language-neutral keys (``label_key`` / ``detail_key`` +
``detail_args``); ``agent-radar report --lang`` renders them via
``agent_radar.i18n``. Same for ``blind_spots``.
"""

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path


# ----------------------------------------------------------------------------
# 維度定義 (keys; labels are resolved at render time via i18n.DIMENSIONS)
# ----------------------------------------------------------------------------

DIMENSION_KEYS = [
    "claude_md", "skills", "mcp", "automation", "context_hygiene", "iteration",
]


# ----------------------------------------------------------------------------
# 偵測結果資料結構
# ----------------------------------------------------------------------------

@dataclass
class Finding:
    """One evidence signal, carrying i18n keys (rendered at report time)."""
    dimension: str
    label_key: str
    weight: float
    score: float
    detail_key: str = ""
    detail_args: dict = field(default_factory=dict)

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
    level_threshold: int = 0  # threshold (0/20/40/60/80) — label rendered by report
    blind_spots: list = field(default_factory=list)  # list of {"key": str, "args": dict}


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
        return len([line for line in out.stdout.splitlines() if line.strip()])
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

SECTION_HINTS = [
    "command", "build", "test", "lint", "code style", "convention",
    "architecture", "workflow", "do not", "never", "always", "important",
    "指令", "建置", "測試", "風格", "規範", "架構", "禁止", "務必", "注意",
]

IMPERATIVE_HINTS = [
    r"\buse\b", r"\bdo not\b", r"\bnever\b", r"\balways\b", r"\bprefer\b",
    r"\brun\b", r"\bavoid\b", r"\bensure\b", r"請", r"務必", r"禁止", r"避免",
]

CLAUDE_MD_SOFT_LIMIT_CHARS = 8_000
CLAUDE_MD_HARD_LIMIT_CHARS = 20_000
SKILL_MD_SOFT_LIMIT_LINES = 250
SKILL_MD_HARD_LIMIT_LINES = 500

DECORATIVE_PATTERNS = [
    r"[=\-_*#~`]{20,}",
    r"[─━│┃┄┅┆┇┈┉┊┋┌┍┎┏┐┑┒┓└┕┖┗┘┙┚┛├┝┞┟┠┡┢┣┤┥┦┧┨┩┪┫┬┭┮┯┰┱┲┳┴┵┶┷┸┹┺┻┼┽┾┿╀╁╂╃╄╅╆╇╈╉╊╋╌╍╎╏═║╒╓╔╕╖╗╘╙╚╛╜╝╞╟╠╡╢╣╤╥╦╧╨╩╪╫╬╭╮╯╰╱╲╳╴╵╶╷╸╹╺╻╼╽╾╿]{8,}",
    r"^\s*[▀▁▂▃▄▅▆▇█▉▊▋▌▍▎▏▐░▒▓▔▕]{4,}",
]
DECORATIVE_RE = re.compile("|".join(DECORATIVE_PATTERNS), re.MULTILINE)


def detect_claude_md(repo: Path, is_home: bool) -> list:
    """評估 CLAUDE.md 成熟度。"""
    findings = []
    candidates = [repo / "CLAUDE.md", repo / ".claude" / "CLAUDE.md"]
    found = [p for p in candidates if _exists(p)]

    if found:
        paths_str = ", ".join(str(p.relative_to(repo)) for p in found)
        findings.append(Finding(
            "claude_md", "scan.claude_md.exists", weight=25, score=25,
            detail_key="scan.claude_md.exists.found",
            detail_args={"paths": paths_str},
        ))
    else:
        findings.append(Finding(
            "claude_md", "scan.claude_md.exists", weight=25, score=0,
            detail_key="scan.claude_md.exists.none",
        ))
        # 後面的訊號都 0 分，但仍列出讓報告完整
        for lbl_key, w in [
            ("scan.claude_md.structure", 20),
            ("scan.claude_md.imperative", 15),
            ("scan.claude_md.concise", 15),
            ("scan.claude_md.import", 10),
        ]:
            findings.append(Finding(
                "claude_md", lbl_key, weight=w, score=0,
                detail_key="scan.claude_md.placeholder",
            ))
        return findings

    text = "\n\n".join(_read(p) for p in found)
    lower = text.lower()

    headers = re.findall(r"^#{1,4}\s+.+$", text, flags=re.MULTILINE)
    hint_hits = sum(1 for h in SECTION_HINTS if h in lower)
    struct_score = _clamp(len(headers) * 4 + hint_hits * 2, 0, 20)
    findings.append(Finding(
        "claude_md", "scan.claude_md.structure", weight=20, score=struct_score,
        detail_key="scan.claude_md.structure.detail",
        detail_args={"headers": len(headers), "hints": hint_hits},
    ))

    imp_hits = sum(len(re.findall(p, lower)) for p in IMPERATIVE_HINTS)
    imp_score = _clamp(imp_hits * 1.5, 0, 15)
    findings.append(Finding(
        "claude_md", "scan.claude_md.imperative", weight=15, score=imp_score,
        detail_key="scan.claude_md.imperative.detail",
        detail_args={"hits": imp_hits},
    ))

    words = len(text.split())
    if words == 0:
        concise = 0
    elif words < 80:
        concise = 7
    elif words <= 600:
        concise = 15
    elif words <= 1200:
        concise = 10
    else:
        concise = 5
    findings.append(Finding(
        "claude_md", "scan.claude_md.concise", weight=15, score=concise,
        detail_key="scan.claude_md.concise.detail",
        detail_args={"words": words},
    ))

    imports = len(re.findall(r"(^|\s)@[\w./\-]+", text))
    imp_ref_score = _clamp(imports * 5, 0, 10)
    findings.append(Finding(
        "claude_md", "scan.claude_md.import", weight=10, score=imp_ref_score,
        detail_key=("scan.claude_md.import.have" if imports
                    else "scan.claude_md.import.none"),
        detail_args=({"n": imports} if imports else {}),
    ))

    total_chars = len(text)
    if total_chars <= CLAUDE_MD_SOFT_LIMIT_CHARS:
        size_score = 15
        detail_key = "scan.claude_md.lint_size.ok"
    elif total_chars <= CLAUDE_MD_HARD_LIMIT_CHARS:
        ratio = (CLAUDE_MD_HARD_LIMIT_CHARS - total_chars) / (
            CLAUDE_MD_HARD_LIMIT_CHARS - CLAUDE_MD_SOFT_LIMIT_CHARS)
        size_score = round(15 * max(ratio, 0) * 0.5 + 4, 1)
        detail_key = "scan.claude_md.lint_size.soft"
    else:
        size_score = 0
        detail_key = "scan.claude_md.lint_size.hard"
    findings.append(Finding(
        "claude_md", "scan.claude_md.lint_size", weight=15, score=size_score,
        detail_key=detail_key, detail_args={"chars": total_chars},
    ))

    return findings


def detect_skills(repo: Path, is_home: bool) -> list:
    findings = []
    skill_dirs = [repo / ".claude" / "skills", repo / "skills"]
    skill_files = []
    for d in skill_dirs:
        if _exists(d):
            skill_files.extend(d.rglob("SKILL.md"))

    if skill_files:
        findings.append(Finding(
            "skills", "scan.skills.exists", weight=35, score=35,
            detail_key="scan.skills.exists.have",
            detail_args={"n": len(skill_files)},
        ))
    else:
        findings.append(Finding(
            "skills", "scan.skills.exists", weight=35, score=0,
            detail_key="scan.skills.exists.none",
        ))
        for lbl_key, w in [
            ("scan.skills.description", 35),
            ("scan.skills.progressive", 30),
            ("scan.skills.lint_hygiene", 20),
        ]:
            findings.append(Finding(
                "skills", lbl_key, weight=w, score=0,
                detail_key="scan.skills.placeholder",
            ))
        return findings

    desc_quality = 0.0
    pd_quality = 0.0
    frontmatter_ok = 0
    decor_violations = 0
    oversize_violations = 0
    for sf in skill_files:
        t = _read(sf)
        m = re.search(r"description:\s*(.+)", t)
        if m:
            desc_len = len(m.group(1).split())
            trigger = any(k in m.group(1).lower()
                          for k in ["use this", "use when", "trigger", "when the user"])
            desc_quality += min(15, desc_len * 0.4) + (10 if trigger else 0)
        sibling = list(sf.parent.glob("*"))
        body_words = len(t.split())
        if body_words and body_words < 500 and len(sibling) > 1:
            pd_quality += 15
        elif len(sibling) > 1:
            pd_quality += 8

        has_name = bool(re.search(r"^name:\s*\S", t, re.MULTILINE))
        has_desc = bool(m and m.group(1).strip())
        if has_name and has_desc:
            frontmatter_ok += 1

        n_lines = t.count("\n") + 1
        if n_lines > SKILL_MD_HARD_LIMIT_LINES:
            oversize_violations += 1
        elif n_lines > SKILL_MD_SOFT_LIMIT_LINES:
            oversize_violations += 0.5

        if DECORATIVE_RE.search(t):
            decor_violations += 1

    desc_score = _clamp(desc_quality / len(skill_files), 0, 35)
    pd_score = _clamp(pd_quality, 0, 30)

    findings.append(Finding(
        "skills", "scan.skills.description", weight=35, score=desc_score,
        detail_key="scan.skills.description.detail",
    ))
    findings.append(Finding(
        "skills", "scan.skills.progressive", weight=30, score=pd_score,
        detail_key="scan.skills.progressive.detail",
    ))

    n = len(skill_files)
    fm_ratio = frontmatter_ok / n
    lint_score = 20 * fm_ratio
    lint_score -= min(lint_score, decor_violations * 3 + oversize_violations * 4)
    lint_score = max(0, lint_score)
    suffixes = []
    if decor_violations:
        suffixes.append(["scan.skills.lint.decor_suffix", {"n": decor_violations}])
    if oversize_violations:
        suffixes.append(["scan.skills.lint.oversize_suffix", {"n": oversize_violations}])
    findings.append(Finding(
        "skills", "scan.skills.lint_hygiene", weight=20, score=lint_score,
        detail_key="scan.skills.lint.detail",
        detail_args={"fm": frontmatter_ok, "n": n, "_suffixes": suffixes},
    ))
    return findings


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
        "mcp", "scan.mcp.server_count", weight=50,
        score=_clamp(n * 18, 0, 50),
        detail_key=("scan.mcp.server_count.have" if n
                    else "scan.mcp.server_count.none"),
        detail_args=({"n": n} if n else {}),
    ))

    blob = " ".join(servers.keys()).lower() + " " + json.dumps(servers).lower()
    cats = [c for c, kw in MCP_CATEGORY_HINTS.items() if any(k in blob for k in kw)]
    findings.append(Finding(
        "mcp", "scan.mcp.category_breadth", weight=50,
        score=_clamp(len(cats) * 17, 0, 50),
        detail_key=("scan.mcp.category_breadth.have" if cats
                    else "scan.mcp.category_breadth.none"),
        detail_args=({"cats": ", ".join(cats)} if cats else {}),
    ))
    return findings


def detect_automation(repo: Path, is_home: bool) -> list:
    findings = []
    cc = repo / ".claude"

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

    if settings_invalid:
        detail_key = "scan.automation.hooks.invalid"
        score = 0
    elif hooks_present:
        detail_key = "scan.automation.hooks.have"
        score = 30
    else:
        detail_key = "scan.automation.hooks.none"
        score = 0
    findings.append(Finding(
        "automation", "scan.automation.hooks", weight=30, score=score,
        detail_key=detail_key,
    ))

    agents_dir = cc / "agents"
    n_agents = len(list(agents_dir.glob("*.md"))) if _exists(agents_dir) else 0
    findings.append(Finding(
        "automation", "scan.automation.subagents", weight=30,
        score=_clamp(n_agents * 15, 0, 30),
        detail_key=("scan.automation.subagents.have" if n_agents
                    else "scan.automation.subagents.none"),
        detail_args=({"n": n_agents} if n_agents else {}),
    ))

    cmd_dir = cc / "commands"
    n_cmd = len(list(cmd_dir.glob("*.md"))) if _exists(cmd_dir) else 0
    findings.append(Finding(
        "automation", "scan.automation.commands", weight=25,
        score=_clamp(n_cmd * 9, 0, 25),
        detail_key=("scan.automation.commands.have" if n_cmd
                    else "scan.automation.commands.none"),
        detail_args=({"n": n_cmd} if n_cmd else {}),
    ))

    plugin_signal = _exists(cc / "plugins") or (
        _exists(settings) and "plugin" in _read(settings).lower())
    findings.append(Finding(
        "automation", "scan.automation.plugins", weight=15,
        score=15 if plugin_signal else 0,
        detail_key=("scan.automation.plugins.have" if plugin_signal
                    else "scan.automation.plugins.none"),
    ))
    return findings


def detect_context_hygiene(repo: Path, is_home: bool, home_seen: bool) -> list:
    findings = []

    proj_md = _exists(repo / "CLAUDE.md") or _exists(repo / ".claude" / "CLAUDE.md")
    if proj_md and home_seen:
        split_score = 40
        detail_key = "scan.context.split.full"
    elif proj_md:
        split_score = 20
        detail_key = "scan.context.split.project_only"
    elif home_seen:
        split_score = 20
        detail_key = "scan.context.split.user_only"
    else:
        split_score = 0
        detail_key = "scan.context.split.none"
    findings.append(Finding(
        "context_hygiene", "scan.context.split", weight=40,
        score=split_score, detail_key=detail_key,
    ))

    gi = _read(repo / ".gitignore").lower()
    gi_score = 30 if ("settings.local" in gi or ".claude/settings.local" in gi) else 0
    findings.append(Finding(
        "context_hygiene", "scan.context.shared_personal", weight=30,
        score=gi_score,
        detail_key=("scan.context.shared_personal.ok" if gi_score
                    else "scan.context.shared_personal.no"),
    ))

    md_text = ""
    for p in [repo / "CLAUDE.md", repo / ".claude" / "CLAUDE.md"]:
        if _exists(p):
            md_text += _read(p)
    imports = len(re.findall(r"(^|\s)@[\w./\-]+", md_text))
    findings.append(Finding(
        "context_hygiene", "scan.context.modular", weight=30,
        score=_clamp(imports * 15, 0, 30),
        detail_key=("scan.context.modular.have" if imports
                    else "scan.context.modular.none"),
        detail_args=({"n": imports} if imports else {}),
    ))
    return findings


def detect_iteration(repo: Path, is_home: bool) -> list:
    findings = []
    is_git = _exists(repo / ".git")

    if not is_git:
        findings.append(Finding(
            "iteration", "scan.iteration.git", weight=60, score=0,
            detail_key="scan.iteration.non_git",
        ))
        findings.append(Finding(
            "iteration", "scan.iteration.diversity", weight=40, score=0,
            detail_key="scan.iteration.non_git.short",
        ))
        return findings

    counts = {
        "CLAUDE.md": _git_log_count(repo, "CLAUDE.md")
                     + _git_log_count(repo, ".claude/CLAUDE.md"),
        ".claude/": _git_log_count(repo, ".claude"),
        ".mcp.json": _git_log_count(repo, ".mcp.json"),
    }
    total_commits = sum(counts.values())
    parts = ", ".join(f"{k}={v}" for k, v in counts.items() if v)
    findings.append(Finding(
        "iteration", "scan.iteration.git", weight=60,
        score=_clamp(total_commits * 8, 0, 60),
        detail_key="scan.iteration.git.detail",
        detail_args={"parts": parts, "counts": counts},
    ))

    touched = sum(1 for v in counts.values() if v > 0)
    findings.append(Finding(
        "iteration", "scan.iteration.diversity", weight=40,
        score=_clamp(touched * 14, 0, 40),
        detail_key="scan.iteration.diversity.detail",
        detail_args={"n": touched},
    ))
    return findings


# ----------------------------------------------------------------------------
# 彙整
# ----------------------------------------------------------------------------

LEVEL_THRESHOLDS = [0, 20, 40, 60, 80]


def score_target(path: Path, name: str, is_home: bool, home_seen: bool) -> TargetReport:
    rep = TargetReport(name=name, path=str(path), is_home=is_home)

    rep.findings += detect_claude_md(path, is_home)
    rep.findings += detect_skills(path, is_home)
    rep.findings += detect_mcp(path, is_home)
    rep.findings += detect_automation(path, is_home)
    rep.findings += detect_context_hygiene(path, is_home, home_seen)
    rep.findings += detect_iteration(path, is_home)

    for dim in DIMENSION_KEYS:
        fs = [f for f in rep.findings if f.dimension == dim]
        got = sum(f.score for f in fs)
        cap = sum(f.weight for f in fs)
        rep.scores[dim] = round((got / cap * 100) if cap else 0, 1)

    rep.overall = round(sum(rep.scores.values()) / len(rep.scores), 1)

    for threshold in reversed(LEVEL_THRESHOLDS):
        if rep.overall >= threshold:
            rep.level_threshold = threshold
            break

    if rep.scores["mcp"] > 0 or rep.scores["skills"] > 0:
        rep.blind_spots.append({"key": "scan.blind.config_only", "args": {}})
    if not _exists(path / ".git") and not is_home:
        rep.blind_spots.append({"key": "scan.blind.non_git", "args": {}})

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
        # Producers emit only keys + thresholds; report renders text per --lang.
        "dimensions": DIMENSION_KEYS,
        "level_thresholds": LEVEL_THRESHOLDS,
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
