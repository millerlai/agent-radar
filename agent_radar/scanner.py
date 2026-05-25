#!/usr/bin/env python3
"""
agent-radar :: agent_radar.scanner
==================================
Detect Claude Code "configuration fingerprints" on the filesystem.

Design (0.2.0 — activation-gap framing)
----------------------------------------
We surface five capability axes, each backed only by *observable facts* (does
this file exist? how many of these are there? did git touch this path?). We
deliberately do **not** grade "quality" of CLAUDE.md content or SKILL.md
descriptions — that interpretive layer belongs to ``/agent-radar-coach``.

Five axes:
  1. claude_md      - CLAUDE.md presence, size, @import refs, iteration signals
  2. skills         - SKILL.md count + lint hygiene
  3. mcp            - configured MCP server count + category breadth
  4. automation     - hooks / subagents / commands / plugins (fact counts)
  5. context_hygiene - user/project split + gitignore + @import modularity

The iteration dimension from 0.1.x is folded into ``claude_md`` as two
sub-signals: git commit count on CLAUDE.md + content regex hits for
"lessons learned / mistakes to avoid / do not repeat / dated rules".

Configured-ness is a 0-100 score per axis representing presence of expected
facts. It does NOT claim to measure quality. The companion
``session_scanner`` reports activated-ness on the same axes; ``merge``
computes Configured − Activated = the Activation Gap, which is the product's
single product thesis.

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
# Five axes (0.2.0). Labels resolved at render time via i18n.DIMENSIONS.
# ----------------------------------------------------------------------------

DIMENSION_KEYS = [
    "claude_md", "skills", "mcp", "automation", "context_hygiene",
]


# ----------------------------------------------------------------------------
# Result data structures
# ----------------------------------------------------------------------------

@dataclass
class Finding:
    """One observable signal, carrying i18n keys (rendered at report time)."""
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
    """Result for one scan target (a repo, or the user home dir)."""
    name: str
    path: str
    is_home: bool = False
    findings: list = field(default_factory=list)
    scores: dict = field(default_factory=dict)   # dimension -> 0..100 (configured-ness)
    overall: float = 0.0  # average across the five axes; "configured coverage", not "maturity"
    blind_spots: list = field(default_factory=list)


# ----------------------------------------------------------------------------
# Small helpers
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
    """Count git commits touching ``pathspec``. 0 if not a git repo / no history."""
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
# Detection logic
# ----------------------------------------------------------------------------

CLAUDE_MD_SOFT_LIMIT_CHARS = 8_000
CLAUDE_MD_HARD_LIMIT_CHARS = 20_000
SKILL_MD_SOFT_LIMIT_LINES = 250
SKILL_MD_HARD_LIMIT_LINES = 500

# "Iteration loop" content signals: phrases / sections that suggest the user
# has been refining CLAUDE.md based on past Claude failures, not just writing
# it once. These are *patterns to detect*, not patterns to judge.
ITERATION_CONTENT_PATTERNS = [
    # Section headers
    r"^#{1,4}\s+.*(lessons?\s+learned|mistakes?|learning\s+from)",
    r"^#{1,4}\s+.*(past\s+(failures?|incidents?)|do\s+not\s+repeat)",
    r"^#{1,4}\s+.*(從錯誤|過去問題|教訓)",
    # Inline phrases
    r"\bdo not repeat\b", r"\bnever again\b", r"\bpreviously\b", r"\blast time\b",
    r"\bwhen I correct(ed)? you\b", r"\bafter the\s+\w+\s+incident\b",
    r"不要再", r"上次", r"曾經\s*(犯|錯)", r"歷史教訓",
    # Dated rule additions (timestamps suggest reactive iteration)
    r"\[\d{4}-\d{2}-\d{2}\]", r"\bAdded\s+\d{4}-\d{2}-\d{2}\b",
    r"\bRule added after\b",
]
ITERATION_CONTENT_RE = re.compile(
    "|".join(ITERATION_CONTENT_PATTERNS), re.IGNORECASE | re.MULTILINE)


DECORATIVE_PATTERNS = [
    r"[=\-_*#~`]{20,}",
    r"[─━│┃┄┅┆┇┈┉┊┋┌┍┎┏┐┑┒┓└┕┖┗┘┙┚┛├┝┞┟┠┡┢┣┤┥┦┧┨┩┪┫┬┭┮┯┰┱┲┳┴┵┶┷┸┹┺┻┼┽┾┿╀╁╂╃╄╅╆╇╈╉╊╋╌╍╎╏═║╒╓╔╕╖╗╘╙╚╛╜╝╞╟╠╡╢╣╤╥╦╧╨╩╪╫╬╭╮╯╰╱╲╳╴╵╶╷╸╹╺╻╼╽╾╿]{8,}",
    r"^\s*[▀▁▂▃▄▅▆▇█▉▊▋▌▍▎▏▐░▒▓▔▕]{4,}",
]
DECORATIVE_RE = re.compile("|".join(DECORATIVE_PATTERNS), re.MULTILINE)


def detect_claude_md(repo: Path, is_home: bool) -> list:
    """Observable facts about CLAUDE.md presence + iteration evidence.

    Sub-signals (all factual, no quality judgement):
      - exists (presence)
      - lint_size (over the chars limit?)
      - @import refs (count)
      - iteration: git commit count on CLAUDE.md + content-regex hits for
        lessons-learned / mistakes / do-not-repeat / dated-rule patterns
    """
    findings = []
    candidates = [repo / "CLAUDE.md", repo / ".claude" / "CLAUDE.md"]
    found = [p for p in candidates if _exists(p)]

    if not found:
        findings.append(Finding(
            "claude_md", "scan.claude_md.exists", weight=50, score=0,
            detail_key="scan.claude_md.exists.none",
        ))
        # Nothing else to evaluate. No fake-zero placeholder findings.
        return findings

    paths_str = ", ".join(str(p.relative_to(repo)) for p in found)
    findings.append(Finding(
        "claude_md", "scan.claude_md.exists", weight=50, score=50,
        detail_key="scan.claude_md.exists.found",
        detail_args={"paths": paths_str},
    ))

    text = "\n\n".join(_read(p) for p in found)

    # @import modular references
    imports = len(re.findall(r"(^|\s)@[\w./\-]+", text))
    findings.append(Finding(
        "claude_md", "scan.claude_md.import", weight=10,
        score=_clamp(imports * 5, 0, 10),
        detail_key=("scan.claude_md.import.have" if imports
                    else "scan.claude_md.import.none"),
        detail_args=({"n": imports} if imports else {}),
    ))

    # Lint: size limits (penalty when oversized)
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

    # Iteration evidence (folded in from the 0.1.x "iteration" dimension)
    # Two sub-signals: git commits + content regex hits.
    git_commits = (
        _git_log_count(repo, "CLAUDE.md")
        + _git_log_count(repo, ".claude/CLAUDE.md")
    )
    content_hits = len(ITERATION_CONTENT_RE.findall(text))
    # Either signal alone is weak; the combination of both is what we reward.
    iter_score = _clamp(git_commits * 3 + content_hits * 4, 0, 25)
    findings.append(Finding(
        "claude_md", "scan.claude_md.iteration", weight=25, score=iter_score,
        detail_key="scan.claude_md.iteration.detail",
        detail_args={"commits": git_commits, "hits": content_hits},
    ))

    return findings


def detect_skills(repo: Path, is_home: bool) -> list:
    """Facts about installed SKILL.md files (no quality grading).

    Sub-signals:
      - count (how many SKILL.md exist)
      - lint hygiene (frontmatter compliance, decorative banners, oversize)
    """
    findings = []
    skill_dirs = [repo / ".claude" / "skills", repo / "skills"]
    skill_files = []
    for d in skill_dirs:
        if _exists(d):
            skill_files.extend(d.rglob("SKILL.md"))

    if not skill_files:
        findings.append(Finding(
            "skills", "scan.skills.exists", weight=70, score=0,
            detail_key="scan.skills.exists.none",
        ))
        return findings

    # Skill presence — fact only; "quality" is for the coach skill to judge.
    findings.append(Finding(
        "skills", "scan.skills.exists", weight=70,
        score=_clamp(len(skill_files) * 20, 0, 70),
        detail_key="scan.skills.exists.have",
        detail_args={"n": len(skill_files)},
    ))

    frontmatter_ok = 0
    decor_violations = 0
    oversize_violations = 0
    for sf in skill_files:
        t = _read(sf)
        has_name = bool(re.search(r"^name:\s*\S", t, re.MULTILINE))
        has_desc = bool(re.search(r"^description:\s*\S", t, re.MULTILINE))
        if has_name and has_desc:
            frontmatter_ok += 1
        n_lines = t.count("\n") + 1
        if n_lines > SKILL_MD_HARD_LIMIT_LINES:
            oversize_violations += 1
        elif n_lines > SKILL_MD_SOFT_LIMIT_LINES:
            oversize_violations += 0.5
        if DECORATIVE_RE.search(t):
            decor_violations += 1

    n = len(skill_files)
    fm_ratio = frontmatter_ok / n
    lint_score = 30 * fm_ratio
    lint_score -= min(lint_score, decor_violations * 3 + oversize_violations * 4)
    lint_score = max(0, lint_score)
    suffixes = []
    if decor_violations:
        suffixes.append(["scan.skills.lint.decor_suffix", {"n": decor_violations}])
    if oversize_violations:
        suffixes.append(["scan.skills.lint.oversize_suffix", {"n": oversize_violations}])
    findings.append(Finding(
        "skills", "scan.skills.lint_hygiene", weight=30, score=lint_score,
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


# ----------------------------------------------------------------------------
# Aggregation
# ----------------------------------------------------------------------------

def score_target(path: Path, name: str, is_home: bool, home_seen: bool) -> TargetReport:
    rep = TargetReport(name=name, path=str(path), is_home=is_home)

    rep.findings += detect_claude_md(path, is_home)
    rep.findings += detect_skills(path, is_home)
    rep.findings += detect_mcp(path, is_home)
    rep.findings += detect_automation(path, is_home)
    rep.findings += detect_context_hygiene(path, is_home, home_seen)

    for dim in DIMENSION_KEYS:
        fs = [f for f in rep.findings if f.dimension == dim]
        got = sum(f.score for f in fs)
        cap = sum(f.weight for f in fs)
        rep.scores[dim] = round((got / cap * 100) if cap else 0, 1)

    # "overall" is the average across the five axes — a configured-coverage
    # number, NOT a maturity score. Kept in the JSON because tooling consumes
    # it, but the report HTML reframes it as "configured coverage".
    rep.overall = round(sum(rep.scores.values()) / len(rep.scores), 1)

    if rep.scores["mcp"] > 0 or rep.scores["skills"] > 0:
        rep.blind_spots.append({"key": "scan.blind.config_only", "args": {}})

    rep.findings = [asdict(f) for f in rep.findings]
    return rep


def main():
    ap = argparse.ArgumentParser(
        description="Claude Code configured-fingerprint scanner (0.2.0)")
    ap.add_argument("paths", nargs="+", help="Repo paths to scan (one or more)")
    ap.add_argument("--include-home", action="store_true",
                    help="Also scan user-space (~/.claude)")
    ap.add_argument("-o", "--output", default="-", help="Output JSON path (default stdout)")
    args = ap.parse_args()

    targets = []

    # ~/.claude existence is a *fact* we should always detect — it tells us
    # whether the user has a personal-prefs layer, regardless of whether we
    # also scan ~/.claude as its own target. ``--include-home`` only controls
    # the latter (deep-scan as a separate target row in the report).
    home_claude = Path.home() / ".claude"
    home_seen = _exists(home_claude)

    for p in args.paths:
        path = Path(p).expanduser().resolve()
        if not path.exists():
            print(f"[warn] path missing, skipped: {path}", file=sys.stderr)
            continue
        targets.append(score_target(path, path.name, is_home=False, home_seen=home_seen))

    if args.include_home and home_seen:
        targets.append(score_target(home_claude.parent, "~ (user-space)",
                                    is_home=True, home_seen=True))

    result = {
        "dimensions": DIMENSION_KEYS,
        "targets": [asdict(t) for t in targets],
    }

    out = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output == "-":
        print(out)
    else:
        Path(args.output).write_text(out, encoding="utf-8")
        print(f"[ok] wrote {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
