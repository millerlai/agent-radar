"""Unit tests for agent_radar.scanner."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


from agent_radar import scanner
from agent_radar.scanner import (
    DIMENSIONS,
    LEVELS,
    Finding,
    _clamp,
    _exists,
    _git_log_count,
    _read,
    detect_automation,
    detect_claude_md,
    detect_context_hygiene,
    detect_iteration,
    detect_mcp,
    detect_skills,
    score_target,
)


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _write(p: Path, content: str = "") -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# small utilities
# ---------------------------------------------------------------------------

class TestClamp:
    def test_within_range(self):
        assert _clamp(5, 0, 10) == 5

    def test_below_low(self):
        assert _clamp(-3, 0, 10) == 0

    def test_above_high(self):
        assert _clamp(99, 0, 10) == 10

    def test_no_hi(self):
        assert _clamp(1000) == 1000

    def test_float(self):
        assert _clamp(3.7, 0, 5) == 3.7


class TestRead:
    def test_reads_existing(self, tmp_path):
        f = _write(tmp_path / "a.txt", "hello")
        assert _read(f) == "hello"

    def test_missing_returns_empty(self, tmp_path):
        assert _read(tmp_path / "ghost.txt") == ""

    def test_respects_limit(self, tmp_path):
        f = _write(tmp_path / "big.txt", "x" * 1000)
        assert _read(f, limit=100) == "x" * 100


class TestExists:
    def test_existing(self, tmp_path):
        assert _exists(tmp_path) is True

    def test_missing(self, tmp_path):
        assert _exists(tmp_path / "no") is False


# ---------------------------------------------------------------------------
# Finding dataclass
# ---------------------------------------------------------------------------

class TestFinding:
    def test_ratio(self):
        f = Finding("x", "y", weight=10, score=3)
        assert f.ratio == 0.3

    def test_zero_weight(self):
        f = Finding("x", "y", weight=0, score=0)
        assert f.ratio == 0.0


# ---------------------------------------------------------------------------
# CLAUDE.md detection
# ---------------------------------------------------------------------------

class TestDetectClaudeMd:
    def test_missing_zero(self, tmp_path):
        findings = detect_claude_md(tmp_path, is_home=False)
        # all findings reported but only "存在" carries weight 25, all 0
        assert all(f.score == 0 for f in findings)
        assert any("未發現" in f.detail for f in findings)

    def test_minimal_present_gets_exists_credit(self, tmp_path):
        _write(tmp_path / "CLAUDE.md", "hi")
        findings = detect_claude_md(tmp_path, is_home=False)
        by_label = {f.label: f for f in findings}
        assert by_label["CLAUDE.md 存在"].score == 25

    def test_well_structured_md_scores_high(self, tmp_path):
        body = """# Build
## Test
## Code style
- Use small functions.
- Do not commit secrets.
- Never push without review.
- Always run tests.
@docs/style.md
@docs/conventions.md
""" * 1  # keep within "黃金區間" word count
        _write(tmp_path / "CLAUDE.md", body)
        findings = detect_claude_md(tmp_path, is_home=False)
        by = {f.label: f for f in findings}
        assert by["CLAUDE.md 存在"].score == 25
        assert by["結構化分區"].score > 0
        assert by["指令式語氣"].score > 0
        assert by["@import 引用"].score > 0
        # 小體積 → Lint 滿分
        assert by["Lint: 大小合理"].score == 15

    def test_huge_md_size_lint_zero(self, tmp_path):
        # > CLAUDE_MD_HARD_LIMIT_CHARS triggers size_score = 0
        big = "word " * 8000  # ~40 000 chars
        _write(tmp_path / "CLAUDE.md", big)
        findings = detect_claude_md(tmp_path, is_home=False)
        by = {f.label: f for f in findings}
        assert by["Lint: 大小合理"].score == 0
        # over 1200 words → concise = 5
        assert by["精簡度 (非散文堆疊)"].score == 5

    def test_nested_claude_md_recognised(self, tmp_path):
        _write(tmp_path / ".claude" / "CLAUDE.md", "# hi\nuse foo.")
        findings = detect_claude_md(tmp_path, is_home=False)
        by = {f.label: f for f in findings}
        assert by["CLAUDE.md 存在"].score == 25


# ---------------------------------------------------------------------------
# Skills detection
# ---------------------------------------------------------------------------

class TestDetectSkills:
    def test_no_skills(self, tmp_path):
        findings = detect_skills(tmp_path, is_home=False)
        assert all(f.score == 0 for f in findings)

    def test_skill_with_quality_description(self, tmp_path):
        skill_dir = tmp_path / ".claude" / "skills" / "browse"
        _write(
            skill_dir / "SKILL.md",
            "---\n"
            "name: browse\n"
            "description: Use this skill when the user asks to open a browser "
            "or trigger headless QA testing on a deployed URL.\n"
            "---\n"
            "# browse\nshort body\n",
        )
        _write(skill_dir / "helper.md", "more details")
        findings = detect_skills(tmp_path, is_home=False)
        by = {f.label: f for f in findings}
        assert by["Skills 存在"].score == 35
        # description has "use this" trigger and is long enough → > 0
        assert by["description 品質"].score > 0
        # SKILL.md is short AND sibling file present → full pd score
        assert by["Progressive disclosure"].score == 15
        # frontmatter (name + description) present
        assert by["Lint: frontmatter & token 衛生"].score > 0

    def test_decorative_ascii_art_penalises_lint(self, tmp_path):
        skill_dir = tmp_path / ".claude" / "skills" / "x"
        body = (
            "---\nname: x\ndescription: use when ...\n---\n"
            + "=" * 60 + "\n"  # decorative banner
            + "content\n"
        )
        _write(skill_dir / "SKILL.md", body)
        findings = detect_skills(tmp_path, is_home=False)
        by = {f.label: f for f in findings}
        # frontmatter OK but decorative violation deducts
        assert by["Lint: frontmatter & token 衛生"].score < 20


# ---------------------------------------------------------------------------
# MCP detection
# ---------------------------------------------------------------------------

class TestDetectMcp:
    def test_no_mcp(self, tmp_path):
        findings = detect_mcp(tmp_path, is_home=False)
        assert all(f.score == 0 for f in findings)

    def test_servers_from_mcp_json(self, tmp_path):
        servers = {
            "mcpServers": {
                "github": {"command": "npx"},
                "postgres": {"command": "npx"},
                "slack": {"command": "npx"},
            }
        }
        _write(tmp_path / ".mcp.json", json.dumps(servers))
        findings = detect_mcp(tmp_path, is_home=False)
        by = {f.label: f for f in findings}
        # 3 servers → 3*18=54 → clamp to 50
        assert by["MCP server 數量"].score == 50
        # github (saas), postgres (data), slack (saas) → 2 distinct categories
        assert "data" in by["MCP 類型廣度"].detail or "saas" in by["MCP 類型廣度"].detail

    def test_settings_json_also_recognised(self, tmp_path):
        _write(
            tmp_path / ".claude" / "settings.json",
            json.dumps({"mcpServers": {"sentry": {}}}),
        )
        findings = detect_mcp(tmp_path, is_home=False)
        by = {f.label: f for f in findings}
        assert by["MCP server 數量"].score > 0


# ---------------------------------------------------------------------------
# Automation detection
# ---------------------------------------------------------------------------

class TestDetectAutomation:
    def test_nothing(self, tmp_path):
        findings = detect_automation(tmp_path, is_home=False)
        assert all(f.score == 0 for f in findings)

    def test_hooks_via_settings(self, tmp_path):
        _write(
            tmp_path / ".claude" / "settings.json",
            json.dumps({"hooks": {"PreToolUse": []}}),
        )
        findings = detect_automation(tmp_path, is_home=False)
        by = {f.label: f for f in findings}
        assert by["Hooks"].score == 30

    def test_invalid_settings_json_flagged(self, tmp_path):
        _write(tmp_path / ".claude" / "settings.json", "{not json")
        findings = detect_automation(tmp_path, is_home=False)
        by = {f.label: f for f in findings}
        assert by["Hooks"].score == 0
        assert "Lint" in by["Hooks"].detail

    def test_subagents_and_commands_count(self, tmp_path):
        for n in ("a", "b"):
            _write(tmp_path / ".claude" / "agents" / f"{n}.md", "")
        for n in ("c", "d", "e"):
            _write(tmp_path / ".claude" / "commands" / f"{n}.md", "")
        findings = detect_automation(tmp_path, is_home=False)
        by = {f.label: f for f in findings}
        assert by["Subagents"].score == 30  # 2*15 capped at 30
        assert by["自訂 slash commands"].score == 25  # 3*9=27 capped

    def test_plugin_signal_via_settings_text(self, tmp_path):
        _write(
            tmp_path / ".claude" / "settings.json",
            json.dumps({"enabledPlugins": ["foo"]}),
        )
        findings = detect_automation(tmp_path, is_home=False)
        by = {f.label: f for f in findings}
        assert by["Plugins"].score == 15


# ---------------------------------------------------------------------------
# Context hygiene
# ---------------------------------------------------------------------------

class TestDetectContextHygiene:
    def test_no_split_no_gitignore(self, tmp_path):
        findings = detect_context_hygiene(tmp_path, is_home=False, home_seen=False)
        assert all(f.score == 0 for f in findings)

    def test_project_only_split(self, tmp_path):
        _write(tmp_path / "CLAUDE.md", "x")
        findings = detect_context_hygiene(tmp_path, is_home=False, home_seen=False)
        by = {f.label: f for f in findings}
        assert by["User/Project 分工"].score == 20

    def test_full_split(self, tmp_path):
        _write(tmp_path / "CLAUDE.md", "x\n@docs/a.md\n@docs/b.md")
        _write(tmp_path / ".gitignore", "node_modules\n.claude/settings.local.json")
        findings = detect_context_hygiene(tmp_path, is_home=False, home_seen=True)
        by = {f.label: f for f in findings}
        assert by["User/Project 分工"].score == 40
        assert by["共享/個人設定區分"].score == 30
        assert by["模組化引用"].score == 30


# ---------------------------------------------------------------------------
# Iteration detection
# ---------------------------------------------------------------------------

class TestDetectIteration:
    def test_non_git(self, tmp_path):
        findings = detect_iteration(tmp_path, is_home=False)
        assert all(f.score == 0 for f in findings)
        assert any("非 git repo" in f.detail for f in findings)

    def test_git_with_history(self, tmp_path):
        # init a real tiny git repo and commit CLAUDE.md a few times
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.email", "t@e"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
        for i in range(3):
            (tmp_path / "CLAUDE.md").write_text(f"v{i}\n", encoding="utf-8")
            subprocess.run(["git", "add", "CLAUDE.md"], cwd=tmp_path, check=True)
            subprocess.run(
                ["git", "commit", "-q", "-m", f"v{i}"],
                cwd=tmp_path, check=True,
            )
        findings = detect_iteration(tmp_path, is_home=False)
        by = {f.label: f for f in findings}
        assert by["設定檔 git 迭代"].score > 0
        assert by["設定檔多樣性"].score > 0


class TestGitLogCount:
    def test_non_git_returns_zero(self, tmp_path):
        assert _git_log_count(tmp_path, "anything") == 0


# ---------------------------------------------------------------------------
# end-to-end score_target
# ---------------------------------------------------------------------------

class TestScoreTarget:
    def test_empty_repo(self, tmp_path):
        rep = score_target(tmp_path, name="empty", is_home=False, home_seen=False)
        assert rep.name == "empty"
        assert set(rep.scores.keys()) == set(DIMENSIONS.keys())
        assert rep.overall == 0.0
        # very lowest level
        assert rep.level == LEVELS[0][1]
        # findings serialised as plain dicts
        assert all(isinstance(f, dict) for f in rep.findings)

    def test_overall_is_dimension_average(self, tmp_path):
        # half-decent setup so overall > 0
        _write(tmp_path / "CLAUDE.md",
               "# Build\n## Test\nuse foo.\n@docs/a.md")
        _write(tmp_path / ".mcp.json", json.dumps({"mcpServers": {"github": {}}}))
        rep = score_target(tmp_path, name="x", is_home=False, home_seen=False)
        # the overall must equal the mean of per-dim scores rounded to .1
        manual = round(sum(rep.scores.values()) / len(rep.scores), 1)
        assert rep.overall == manual

    def test_blind_spot_for_non_git(self, tmp_path):
        _write(tmp_path / "CLAUDE.md", "x")
        rep = score_target(tmp_path, name="x", is_home=False, home_seen=False)
        assert any("非 git repo" in b for b in rep.blind_spots)


# ---------------------------------------------------------------------------
# CLI smoke-test
# ---------------------------------------------------------------------------

class TestScannerMainCli:
    def test_main_writes_json(self, tmp_path, monkeypatch, capsys):
        # Drive scanner.main via argv
        out = tmp_path / "scan.json"
        target = tmp_path / "repo"
        _write(target / "CLAUDE.md", "x")
        monkeypatch.setattr(
            "sys.argv",
            ["scanner", str(target), "-o", str(out)],
        )
        scanner.main()
        data = json.loads(out.read_text(encoding="utf-8"))
        assert "dimensions" in data
        assert len(data["targets"]) == 1
