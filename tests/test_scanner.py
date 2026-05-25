"""Unit tests for agent_radar.scanner (0.2.0 — activation-gap framing)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


from agent_radar import scanner
from agent_radar.scanner import (
    DIMENSION_KEYS,
    Finding,
    _clamp,
    _exists,
    _git_log_count,
    _read,
    detect_automation,
    detect_claude_md,
    detect_context_hygiene,
    detect_mcp,
    detect_skills,
    score_target,
)


def _write(p: Path, content: str = "") -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _by_key(findings):
    """Index findings by label_key for terser asserts."""
    return {f.label_key: f for f in findings}


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


class TestFinding:
    def test_ratio(self):
        f = Finding("x", "y.key", weight=10, score=3)
        assert f.ratio == 0.3

    def test_zero_weight(self):
        f = Finding("x", "y.key", weight=0, score=0)
        assert f.ratio == 0.0


# ---------------------------------------------------------------------------
# CLAUDE.md detection (0.2.0: facts only, no quality heuristics)
# ---------------------------------------------------------------------------

class TestDetectClaudeMd:
    def test_missing_only_emits_exists_zero(self, tmp_path):
        findings = detect_claude_md(tmp_path, is_home=False)
        # 0.2.0: no placeholder fake-zero findings — only the exists.none
        assert len(findings) == 1
        assert findings[0].label_key == "scan.claude_md.exists"
        assert findings[0].score == 0
        assert findings[0].detail_key == "scan.claude_md.exists.none"

    def test_minimal_present_gets_exists_credit(self, tmp_path):
        _write(tmp_path / "CLAUDE.md", "hi")
        findings = detect_claude_md(tmp_path, is_home=False)
        by = _by_key(findings)
        assert by["scan.claude_md.exists"].score == 50

    def test_full_observable_facts(self, tmp_path):
        body = ("# Build\n"
                "## Test\n"
                "@docs/style.md\n"
                "@docs/conventions.md\n")
        _write(tmp_path / "CLAUDE.md", body)
        findings = detect_claude_md(tmp_path, is_home=False)
        by = _by_key(findings)
        assert by["scan.claude_md.exists"].score == 50
        assert by["scan.claude_md.import"].score > 0   # @ refs counted
        assert by["scan.claude_md.lint_size"].score == 15
        # iteration is a fact, may be 0 if not a git repo / no iteration markers
        assert "scan.claude_md.iteration" in by

    def test_iteration_content_signals(self, tmp_path):
        body = ("# Tips\n"
                "## Lessons Learned\n"
                "do not repeat the bug from [2025-04-15]\n"
                "when I corrected you about X, remember it\n")
        _write(tmp_path / "CLAUDE.md", body)
        findings = detect_claude_md(tmp_path, is_home=False)
        by = _by_key(findings)
        # Even without git, content regex picks up iteration signals
        assert by["scan.claude_md.iteration"].score > 0
        assert by["scan.claude_md.iteration"].detail_args["hits"] >= 3

    def test_huge_md_size_lint_zero(self, tmp_path):
        _write(tmp_path / "CLAUDE.md", "x" * 25_000)
        findings = detect_claude_md(tmp_path, is_home=False)
        by = _by_key(findings)
        assert by["scan.claude_md.lint_size"].score == 0

    def test_nested_claude_md_recognised(self, tmp_path):
        _write(tmp_path / ".claude" / "CLAUDE.md", "# hi")
        findings = detect_claude_md(tmp_path, is_home=False)
        by = _by_key(findings)
        assert by["scan.claude_md.exists"].score == 50


# ---------------------------------------------------------------------------
# Skills detection (0.2.0: count + lint only, no description quality grade)
# ---------------------------------------------------------------------------

class TestDetectSkills:
    def test_no_skills(self, tmp_path):
        findings = detect_skills(tmp_path, is_home=False)
        # 0.2.0: only exists.none, no placeholder fake-zero findings
        assert len(findings) == 1
        assert findings[0].label_key == "scan.skills.exists"
        assert findings[0].score == 0

    def test_skill_present_gets_count_credit(self, tmp_path):
        skill_dir = tmp_path / ".claude" / "skills" / "browse"
        _write(
            skill_dir / "SKILL.md",
            "---\nname: browse\ndescription: use when X\n---\n# browse\nbody\n",
        )
        findings = detect_skills(tmp_path, is_home=False)
        by = _by_key(findings)
        assert by["scan.skills.exists"].score > 0
        assert by["scan.skills.lint_hygiene"].score > 0

    def test_decorative_ascii_art_penalises_lint(self, tmp_path):
        skill_dir = tmp_path / ".claude" / "skills" / "x"
        body = ("---\nname: x\ndescription: use when ...\n---\n"
                + "=" * 60 + "\ncontent\n")
        _write(skill_dir / "SKILL.md", body)
        findings = detect_skills(tmp_path, is_home=False)
        by = _by_key(findings)
        suffixes = by["scan.skills.lint_hygiene"].detail_args.get("_suffixes", [])
        assert any(s[0] == "scan.skills.lint.decor_suffix" for s in suffixes)


# ---------------------------------------------------------------------------
# MCP detection (mostly unchanged from 0.1.x)
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
        by = _by_key(findings)
        assert by["scan.mcp.server_count"].score == 50
        assert by["scan.mcp.server_count"].detail_args["n"] == 3
        cats = by["scan.mcp.category_breadth"].detail_args.get("cats", "")
        assert "data" in cats or "saas" in cats

    def test_settings_json_also_recognised(self, tmp_path):
        _write(
            tmp_path / ".claude" / "settings.json",
            json.dumps({"mcpServers": {"sentry": {}}}),
        )
        findings = detect_mcp(tmp_path, is_home=False)
        by = _by_key(findings)
        assert by["scan.mcp.server_count"].score > 0


# ---------------------------------------------------------------------------
# Automation detection (mostly unchanged)
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
        by = _by_key(findings)
        assert by["scan.automation.hooks"].score == 30

    def test_invalid_settings_json_flagged(self, tmp_path):
        _write(tmp_path / ".claude" / "settings.json", "{not json")
        findings = detect_automation(tmp_path, is_home=False)
        by = _by_key(findings)
        assert by["scan.automation.hooks"].score == 0
        assert by["scan.automation.hooks"].detail_key == "scan.automation.hooks.invalid"

    def test_subagents_and_commands_count(self, tmp_path):
        for n in ("a", "b"):
            _write(tmp_path / ".claude" / "agents" / f"{n}.md", "")
        for n in ("c", "d", "e"):
            _write(tmp_path / ".claude" / "commands" / f"{n}.md", "")
        findings = detect_automation(tmp_path, is_home=False)
        by = _by_key(findings)
        assert by["scan.automation.subagents"].detail_args["n"] == 2
        assert by["scan.automation.commands"].detail_args["n"] == 3


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
        by = _by_key(findings)
        assert by["scan.context.split"].score == 20

    def test_full_split(self, tmp_path):
        _write(tmp_path / "CLAUDE.md", "x\n@docs/a.md\n@docs/b.md")
        _write(tmp_path / ".gitignore", "node_modules\n.claude/settings.local.json")
        findings = detect_context_hygiene(tmp_path, is_home=False, home_seen=True)
        by = _by_key(findings)
        assert by["scan.context.split"].score == 40
        assert by["scan.context.shared_personal"].score == 30
        assert by["scan.context.modular"].score == 30


# ---------------------------------------------------------------------------
# Iteration evidence (now folded into claude_md, no separate dimension)
# ---------------------------------------------------------------------------

class TestIterationInClaudeMd:
    def test_git_iteration_picked_up(self, tmp_path):
        _write(tmp_path / "CLAUDE.md", "# hi\nplain content\n")
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.email", "t@e"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
        for i in range(3):
            (tmp_path / "CLAUDE.md").write_text(f"# v{i}\n", encoding="utf-8")
            subprocess.run(["git", "add", "CLAUDE.md"], cwd=tmp_path, check=True)
            subprocess.run(["git", "commit", "-q", "-m", f"v{i}"],
                           cwd=tmp_path, check=True)
        findings = detect_claude_md(tmp_path, is_home=False)
        by = _by_key(findings)
        assert by["scan.claude_md.iteration"].detail_args["commits"] >= 3
        assert by["scan.claude_md.iteration"].score > 0


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
        # 0.2.0: five axes (iteration folded into claude_md)
        assert set(rep.scores.keys()) == set(DIMENSION_KEYS)
        assert "iteration" not in rep.scores
        assert rep.overall == 0.0
        # findings serialised as plain dicts
        assert all(isinstance(f, dict) for f in rep.findings)
        assert all("label_key" in f for f in rep.findings)

    def test_overall_is_dimension_average(self, tmp_path):
        _write(tmp_path / "CLAUDE.md", "# Build\n@docs/a.md")
        _write(tmp_path / ".mcp.json", json.dumps({"mcpServers": {"github": {}}}))
        rep = score_target(tmp_path, name="x", is_home=False, home_seen=False)
        manual = round(sum(rep.scores.values()) / len(rep.scores), 1)
        assert rep.overall == manual

    def test_dimensions_are_five(self, tmp_path):
        rep = score_target(tmp_path, name="x", is_home=False, home_seen=False)
        assert len(DIMENSION_KEYS) == 5
        assert DIMENSION_KEYS == [
            "claude_md", "skills", "mcp", "automation", "context_hygiene",
        ]
        # ``iteration`` axis must not leak back as an emitted score key
        assert set(rep.scores.keys()) == set(DIMENSION_KEYS)


# ---------------------------------------------------------------------------
# CLI smoke-test
# ---------------------------------------------------------------------------

class TestScannerMainCli:
    def test_main_writes_json(self, tmp_path, monkeypatch):
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
        assert data["dimensions"] == DIMENSION_KEYS
        # 0.2.0: no level_thresholds anymore
        assert "level_thresholds" not in data
        assert len(data["targets"]) == 1
